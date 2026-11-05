#!/usr/bin/env node
/**
 * piweb-safe-restart —— 安全重启守护进程
 *
 * 流程：
 *   1. 通过 pi-web 本地 HTTP API 清点正在跑任务的会话
 *   2. 把会话快照写入 state 文件
 *   3. 延迟若干秒（让调用方的 HTTP 响应先落地）
 *   4. 重启服务（默认 `systemctl --user restart pi-web.service`）
 *   5. 轮询等待端口就绪
 *   6. 向每个快照会话下发「继续」指令
 *
 * 环境变量：
 *   PI_WEB_PORT          pi-web 端口（默认自动探测 ~/.pi/agent/pi-web-run，再退回 30142）
 *   PI_WEB_SERVICE       systemd 服务名（默认 pi-web.service）
 *   PI_WEB_RESTART_CMD   自定义重启命令，设置后优先于 systemctl
 *   PI_SAFE_RESTART_STATE 快照文件路径
 *   PI_SAFE_RESTART_LOG   日志文件路径（默认 /tmp/piweb-safe-restart.log）
 */

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execSync, spawn } from "node:child_process";

const HOME = process.env.HOME || "/home/user";
const STATE_FILE = process.env.PI_SAFE_RESTART_STATE || path.join(HOME, ".pi/agent/state/piweb-restarting-sessions.json");
const LOG_FILE = process.env.PI_SAFE_RESTART_LOG || "/tmp/piweb-safe-restart.log";
const SERVICE = process.env.PI_WEB_SERVICE || "pi-web.service";

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch {}
  process.stdout.write(line);
}

// 自动探测 pi-web 运行端口
function detectPort() {
  if (process.env.PI_WEB_PORT) return Number(process.env.PI_WEB_PORT);
  const runDir = path.join(HOME, ".pi/agent/pi-web-run");
  if (fs.existsSync(runDir)) {
    try {
      const files = fs.readdirSync(runDir).filter((f) => f.endsWith(".json"));
      if (files.length > 0) {
        const info = JSON.parse(fs.readFileSync(path.join(runDir, files[0]), "utf8"));
        if (info.port) return Number(info.port);
      }
    } catch {}
  }
  return 30142;
}

// 若会话文件尾部有未闭合的 toolCall，补一条合成的 toolResult，避免重放时模型报 400
function fixDanglingToolCall(sessionFile) {
  if (!sessionFile || !fs.existsSync(sessionFile)) return;
  try {
    const lines = fs.readFileSync(sessionFile, "utf8").trim().split("\n");
    if (lines.length === 0) return;
    const lastEntry = JSON.parse(lines[lines.length - 1]);
    const msg = lastEntry.message;
    if (msg?.role === "assistant" && Array.isArray(msg.content)) {
      const toolCalls = msg.content.filter((c) => c.type === "toolCall");
      if (toolCalls.length > 0) {
        log(`发现未闭合的 toolCall (${toolCalls.length} 个)，正在为 ${path.basename(sessionFile)} 注入中断保护...`);
        for (const tc of toolCalls) {
          const syntheticResult = {
            type: "message",
            id: crypto.randomBytes(4).toString("hex"),
            parentId: lastEntry.id,
            timestamp: new Date().toISOString(),
            message: {
              role: "toolResult",
              toolCallId: tc.id,
              toolName: tc.name || "unknown",
              content: [
                {
                  type: "text",
                  text: "[System]: Operation interrupted due to pi-web server upgrade/restart. Context preserved.",
                },
              ],
              isError: true,
              timestamp: Date.now(),
            },
          };
          fs.appendFileSync(sessionFile, JSON.stringify(syntheticResult) + "\n");
        }
      }
    }
  } catch (err) {
    log(`检查 dangling toolCall 失败: ${err.message}`);
  }
}

function restartService() {
  const custom = process.env.PI_WEB_RESTART_CMD;
  if (custom) {
    log(`正在执行自定义重启命令: ${custom}`);
    execSync(custom, { stdio: "ignore", shell: "/bin/bash" });
    return;
  }
  log(`正在执行 systemctl --user restart ${SERVICE} ...`);
  execSync(`systemctl --user restart ${SERVICE}`, { stdio: "ignore" });
}

async function runDaemon(port, callerSessionId, delaySeconds) {
  log(`=== 安全重启守护进程启动 (port=${port}, caller=${callerSessionId || "none"}, delay=${delaySeconds}s) ===`);

  const base = `http://127.0.0.1:${port}`;
  const activeSessions = [];

  // 1. 清点正在执行的会话
  try {
    const res = await fetch(`${base}/api/agent/running`, { signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      const { runningSessionIds = [] } = await res.json();
      for (const id of runningSessionIds) {
        try {
          const sRes = await fetch(`${base}/api/agent/${id}?systemPrompt=0`, { signal: AbortSignal.timeout(2000) });
          if (sRes.ok) {
            const { state } = await sRes.json();
            if (state?.isPromptRunning) {
              activeSessions.push({
                id,
                sessionFile: state.sessionFile,
                isCaller: id === callerSessionId,
              });
            }
          }
        } catch {}
      }
    }
  } catch (err) {
    log(`扫描运行中会话出错 (可能服务已断开): ${err.message}`);
  }

  log(`共扫描到 ${activeSessions.length} 个正在忙碌的会话: ${activeSessions.map((s) => s.id.slice(0, 8)).join(", ") || "无"}`);

  // 2. 保存快照
  const dir = path.dirname(STATE_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    STATE_FILE,
    JSON.stringify({ timestamp: Date.now(), port, callerSessionId, sessions: activeSessions }, null, 2),
  );

  // 3. 延迟等待调用方完成响应
  if (delaySeconds > 0) {
    log(`等待 ${delaySeconds} 秒以便调用方结束当前 HTTP 响应...`);
    await new Promise((r) => setTimeout(r, delaySeconds * 1000));
  }

  // 4. 执行重启
  try {
    restartService();
    log("重启指令已发出");
  } catch (err) {
    log(`执行重启失败: ${err.message}`);
  }

  // 5. 轮询等待端口就绪
  log(`等待服务重新就绪 (${base})...`);
  const startTime = Date.now();
  let ready = false;
  while (Date.now() - startTime < 60000) {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      const res = await fetch(`${base}/api/agent/running`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        ready = true;
        break;
      }
    } catch {}
  }

  if (!ready) {
    log("超时 60s 未能探测到 pi-web 恢复就绪，终止接力流程。");
    return;
  }

  log("pi-web 已重新就绪，等待 3 秒缓冲以确保插件与模型池初始化完成...");
  await new Promise((r) => setTimeout(r, 3000));

  // 6. 恢复所有会话
  let snapshot;
  try {
    snapshot = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch {
    snapshot = { sessions: activeSessions };
  }

  for (const s of snapshot.sessions || []) {
    log(`正在恢复会话 ${s.id} (caller: ${s.isCaller})...`);
    if (s.sessionFile) fixDanglingToolCall(s.sessionFile);

    const message = s.isCaller
      ? "【系统通知】pi-web 服务已安全重启成功，新插件与配置已生效！后台受影响的其他任务已自动接续。"
      : "【系统恢复】后台插件升级已完成，pi-web 服务已平稳重启。你刚才的任务现场已自动接续，请检查并继续执行未完成的工作。";

    try {
      const postRes = await fetch(`${base}/api/agent/${s.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "prompt", message }),
        signal: AbortSignal.timeout(10000),
      });
      const data = await postRes.json().catch(() => ({}));
      log(`会话 ${s.id} 恢复下发结果: status=${postRes.status}, data=${JSON.stringify(data)}`);
    } catch (err) {
      log(`恢复会话 ${s.id} 失败: ${err.message}`);
    }
  }

  // 7. 清理快照
  try {
    fs.unlinkSync(STATE_FILE);
  } catch {}
  log("=== 安全重启接力完成 ===");
}

async function main() {
  const args = process.argv.slice(2);
  const isDaemon = args.includes("--daemon");
  const dryRun = args.includes("--dry-run");

  let delay = 3;
  const delayIdx = args.indexOf("--delay");
  if (delayIdx !== -1 && args[delayIdx + 1]) delay = Number(args[delayIdx + 1]);

  let caller = "";
  const callerIdx = args.indexOf("--caller");
  if (callerIdx !== -1 && args[callerIdx + 1]) caller = args[callerIdx + 1];

  const port = detectPort();

  if (dryRun) {
    console.log(`[Dry-Run] 端口: ${port}`);
    console.log(`[Dry-Run] 服务: ${SERVICE}`);
    const res = await fetch(`http://127.0.0.1:${port}/api/agent/running`);
    const data = await res.json();
    console.log(`[Dry-Run] 活跃会话数: ${data.runningSessionIds?.length || 0}`);
    process.exit(0);
  }

  if (isDaemon) {
    await runDaemon(port, caller, delay);
    process.exit(0);
  }

  // 非 daemon 模式：用 systemd-run --user 把守护进程挪出 pi-web.service 的 CGroup，
  // 否则重启 pi-web 会把守护进程一起掐死。
  console.log("[Safe-Restart] 正在通过 systemd-run 脱机启动接力守护进程...");
  const unitName = `piweb-safe-resume-${Date.now()}`;
  const daemonArgs = [
    process.execPath,
    process.argv[1],
    "--daemon",
    "--delay",
    String(delay),
    ...(caller ? ["--caller", caller] : []),
  ];

  try {
    execSync(`systemd-run --user --unit=${unitName} ${daemonArgs.map((a) => `'${a}'`).join(" ")}`, { stdio: "ignore" });
    console.log(
      `[Safe-Restart] 已派发至独立单元 ${unitName}.service，服务将在 ${delay} 秒后重启并自动接续所有会话。`,
    );
    process.exit(0);
  } catch (err) {
    console.warn(`[Safe-Restart] systemd-run 派发失败，回退到普通 detached 进程: ${err.message}`);
    const child = spawn(process.execPath, daemonArgs.slice(1), { detached: true, stdio: "ignore" });
    child.unref();
    console.log(`[Safe-Restart] 普通后台守护已调起 (PID: ${child.pid})。`);
    process.exit(0);
  }
}

main().catch((err) => {
  console.error("执行出错:", err);
  process.exit(1);
});
