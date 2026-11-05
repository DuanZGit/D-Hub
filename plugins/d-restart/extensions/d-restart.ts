/**
 * d-restart —— pi-web 安全重启与会话接力插件
 *
 * 功能：
 * 1. 斜杠命令：/d-restart（简写 /restart，旧名 /safe-restart）
 * 2. Agent 工具：d_restart
 * 3. 行为门禁：拦截裸的 `systemctl restart pi-web`，改写成安全接力
 *
 * 机制：重启前清点所有正在跑任务的会话；重启就绪后自动向这些会话注入指令接力继续跑，
 * 避免会话中断或丢失现场。
 */

import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as path from "node:path";
import process from "node:process";

// 安全导入 TypeBox；宿主模块解析受限时降级为标准 JSON Schema 字典
let Type: any;
try {
  Type = require("typebox").Type;
} catch {
  try {
    Type = require("@sinclair/typebox").Type;
  } catch {
    Type = {
      Object: (props: Record<string, unknown>) => ({ type: "object", properties: props }),
      Optional: (schema: unknown) => schema,
      Number: (opts?: Record<string, unknown>) => ({ type: "number", ...(opts || {}) }),
      String: (opts?: Record<string, unknown>) => ({ type: "string", ...(opts || {}) }),
    };
  }
}

const HOME = process.env.HOME || "/home/user";

// 守护脚本定位。pi 用 jiti 以 CJS 载入扩展，所以 __dirname 指向扩展所在目录；
// 不能用 import.meta（CJS 下是语法错误，会直接让扩展加载失败）。
declare const __dirname: string | undefined;

function resolveScript(): string {
  const rel = path.join("scripts", "d-restart.mjs");
  const candidates: string[] = [];
  try {
    if (typeof __dirname === "string") {
      candidates.push(path.resolve(__dirname, "..", rel));
    }
  } catch {}
  // 兜底：包安装目录的常见位置
  const agentDir = path.join(HOME, ".pi/agent");
  candidates.push(path.join(agentDir, "git/github.com/DuanZGit/d-restart", rel));
  candidates.push(path.join(agentDir, "npm/node_modules/d-restart", rel));
  // 再兜底：扫 ~/.pi/agent/git/*/*/scripts/d-restart.mjs
  try {
    const ghDir = path.join(agentDir, "git");
    for (const host of fs.readdirSync(ghDir)) {
      const hostDir = path.join(ghDir, host);
      if (!fs.statSync(hostDir).isDirectory()) continue;
      for (const owner of fs.readdirSync(hostDir)) {
        const guess = path.join(hostDir, owner, "d-restart", rel);
        if (fs.existsSync(guess)) candidates.push(guess);
      }
    }
  } catch {}
  candidates.push(path.join(agentDir, "bin/d-restart"));
  candidates.push(path.join(agentDir, "bin/piweb-safe-restart"));
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c;
    } catch {}
  }
  return candidates[0];
}

const RESTART_SCRIPT = resolveScript();

function shellQuote(s: string): string {
  return `'${s.replace(/'/g, `'\\''`)}'`;
}

function restartCommand(callerSessionId: string, delaySeconds: number): string {
  const parts = [shellQuote(process.execPath), shellQuote(RESTART_SCRIPT), "--delay", String(delaySeconds)];
  if (callerSessionId) parts.push("--caller", shellQuote(callerSessionId));
  return parts.join(" ");
}

function sessionIdOf(sessionFile: string | undefined): string {
  if (!sessionFile) return "";
  const base = path.basename(sessionFile).replace(/\.jsonl$/, "");
  const tail = base.split("_").pop();
  return tail || base;
}

function triggerSafeRestart(
  callerSessionId: string,
  delaySeconds = 3,
): { success: boolean; error?: string } {
  try {
    const { execSync } = require("node:child_process");
    execSync(restartCommand(callerSessionId, delaySeconds), { stdio: "ignore" });
    return { success: true };
  } catch (err: unknown) {
    return { success: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export default function safeRestartExtension(pi: ExtensionAPI) {
  // 1. 心智注入：会话开始前提醒模型不要裸重启
  pi.on("before_agent_start", (event) => {
    const restartRule = `

## 服务与插件重启准则
当你修改了 pi 插件代码、配置或更新了 npm 包需要重启 pi-web 使其生效时：
- **禁止**直接使用 systemctl 或 bash sleep 粗暴重启，这会掐断其他正在运行的会话！
- **必须**调用专属的 \`d_restart\` 工具（或在终端运行 \`d-restart\`）。它会自动将当前和后台所有忙碌中的会话保存快照，并在重启就绪后自动注入指令继续执行，实现无缝续跑。`;
    return { systemPrompt: `${event.systemPrompt}${restartRule}` };
  });

  // 2. 行为门禁：把裸 systemctl restart pi-web 改写成安全接力
  pi.on("tool_call", (event, ctx) => {
    if (event.toolName === "bash" && event.input && typeof event.input.command === "string") {
      const cmd: string = event.input.command;
      const dangerous = /systemctl\s+(--user\s+)?restart\s+pi-web(\.service)?/i;
      if (dangerous.test(cmd)) {
        const sessionId = sessionIdOf(ctx.sessionFile);
        ctx.ui.notify("检测到粗暴重启命令，已自动重定向为 safe-restart 安全接力，保护其他会话不被中断...", "info");
        event.input.command = cmd.replace(dangerous, restartCommand(sessionId, 3));
      }
    }
  });

  // 3. 斜杠命令 /safe-restart 与 /restart
  const commandHandler = async (_args: string, ctx: ExtensionCommandContext) => {
    const sessionId = sessionIdOf(ctx.sessionFile);
    ctx.ui.notify("正在准备安全重启：锁定运行中会话，3 秒后平稳重启并自动接续...", "info");
    const res = triggerSafeRestart(sessionId, 3);
    if (!res.success) ctx.ui.notify(`触发安全重启失败: ${res.error}`, "error");
  };

  pi.registerCommand("d-restart", {
    description: "安全重启 pi-web，自动保存当前活跃会话并在重启后接续执行",
    handler: commandHandler,
  });

  pi.registerCommand("restart", {
    description: "/d-restart 的简写",
    handler: commandHandler,
  });

  pi.registerCommand("safe-restart", {
    description: "/d-restart 的旧名兼容别名",
    handler: commandHandler,
  });

  // 4. Agent 工具 d_restart
  pi.registerTool({
    name: "d_restart",
    label: "D-Restart",
    description:
      "安全重启 pi-web 服务以使插件、模型配置或系统更新生效。会自动快照所有正在执行任务的会话，在服务重新就绪后下发继续指令，杜绝中断丢失现场。",
    parameters: Type.Object({
      delaySeconds: Type.Optional(Type.Number({ description: "重启前的缓冲秒数，默认 3 秒", default: 3 })),
      reason: Type.Optional(Type.String({ description: "触发重启的原因说明" })),
    }),
    async execute(
      _toolCallId: string,
      params: { delaySeconds?: number; reason?: string },
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ExtensionContext,
    ) {
      const delay = params.delaySeconds ?? 3;
      const reason = params.reason || "更新生效";
      const sessionId = sessionIdOf(ctx.sessionFile);

      const res = triggerSafeRestart(sessionId, delay);
      if (!res.success) {
        return {
          content: [{ type: "text", text: `触发安全重启失败: ${res.error}` }],
          details: { success: false },
        };
      }

      return {
        content: [
          {
            type: "text",
            text: `已安排安全重启（原因: ${reason}）。\n- 缓冲时间: ${delay} 秒\n- 接力策略: 当前所有忙碌中的会话已加入恢复队列，重启完成后自动被唤醒继续执行。`,
          },
        ],
        details: { success: true, delay },
      };
    },
  });
}
