/**
 * pi-web-live —— 把模型思考与工具调用实时改写成「内心独白」，推给 pi-web 顶部浮层条。
 *
 * 数据流：
 *   pi agent 事件（thinking_delta / tool_execution_start）
 *     → 本扩展按句切段
 *     → ctx.modelRegistry.complete() 用当前会话模型改写成短句
 *     → 本地 SSE 服务（127.0.0.1:18999/live）推给浏览器
 *     → 注入到 pi-web 页面的浮层条按节奏播放
 *
 * 前端脚本在 cn-assets/pi-web-live.js，经 patches.json 的 inline 注入 sw.js。
 * 多会话隔离：每条推送带 sid，前端只播当前会话的。
 *
 * 开关：/d-live on | off | status（/live 为兼容别名）
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createServer, type ServerResponse } from "node:http";

const PORT = 18999;
const MIN_SEG = 70; // 至少这么多字才允许按句号切（实测每段改写 ~2s，太短会把队列打满）
const MAX_SEG = 300; // 硬上限，超过无条件切
const MAX_LINES = 6;
const MAX_PENDING = 4; // 队列上限，超了就丢新段，保证实时性
const REWRITE_TIMEOUT = 12000; // 单次改写硬超时

const SYS = `把下面这段思考，改写成给用户看的进度播报：这个项目正在做什么改造、推进到哪一步、下一步往哪走。

规则：
- 不用第一人称，不出现"我"；用无主语或"正在/已经/接下来"开头；
- 每句要有信息量：说清在改什么、进展到哪、下一步是什么，让人看懂这件事往哪推进；
- 每句 14 字以内，最多 ${MAX_LINES} 句；每句结尾加省略号；
- 一半左右的句子带 emoji，别堆满；
- 不写文件名、函数名、端口、路径、命令、缩写字母（JS/CSS/SSE/API 这类），一律换成日常说法；
- 不加引号和编号，不模仿用户语气；
- 必须真的改写：禁止照抄原文里的任何句子、列表、表格、日志；原文里的工具输出直接跳过不写；
- 想不出内容就少写几句，不要凑数。
只输出这些短句，每句一行。`;

// 工具名 → 人话。不调模型，零延迟。
const TOOL_LABEL: Record<string, string> = {
  read: "看一眼",
  write: "写个文件",
  edit: "改几行",
  bash: "跑一条命令",
  grep: "在文件里找",
  find: "找文件",
  ls: "看目录",
  web_search: "上网搜",
  fetch_content: "打开网页",
  source_check: "核对说法",
  get_search_content: "翻搜索结果",
  d_reach: "上网查一下",
  d_reach_fetch: "打开链接",
  d_reach_social: "刷社交平台",
  d_reach_decide: "看证据下判断",
  d_reach_quota: "看还剩多少额度",
  codemode: "连着做几步",
  Agent: "派人去干",
  get_subagent_result: "收手下结果",
  steer_subagent: "给手下补话",
  TaskCreate: "记个待办",
  TaskUpdate: "更新待办",
  TaskList: "看待办",
  TaskGet: "读待办",
  TaskClaim: "领一件事",
  LoopCreate: "挂个定时",
  LoopList: "看定时",
  LoopUpdate: "改定时",
  LoopDelete: "停定时",
  MonitorCreate: "放后台跑",
  MonitorList: "看后台进度",
  MonitorStop: "停后台",
  safe_restart: "重启服务",
  d_restart: "重启服务",
  skill_search: "找有没有现成的办法",
  openviking_find: "翻记忆",
  openviking_search: "搜记忆",
  openviking_read: "读记忆",
  openviking_remember: "记下来",
  openviking_write: "写进记忆",
  openviking_edit: "改记忆",
  openviking_add_resource: "存份资料",
  openviking_health: "看记忆好不好使",
  visual_explainer: "画个解释页",
  diagram: "画张图",
  plan_mode_question: "问你怎么选",
  plan_mode_complete: "交份计划",
  request_secret: "跟你要个密钥",
  WorkflowCreate: "搭条流程",
  WorkflowTransition: "往下推一步",
  WorkflowRevise: "改流程",
};

const TOOL_ARG: Record<string, string[]> = {
  read: ["path"],
  write: ["path"],
  edit: ["path"],
  ls: ["path"],
  grep: ["pattern"],
  find: ["pattern"],
  web_search: ["query"],
  fetch_content: ["url"],
  d_reach: ["query"],
  d_reach_fetch: ["url"],
  d_reach_social: ["query"],
  skill_search: ["query"],
  openviking_search: ["query"],
  openviking_find: ["query"],
  openviking_read: ["uris"],
  openviking_write: ["uri"],
  openviking_edit: ["uri"],
  Agent: ["description"],
  TaskCreate: ["subject"],
  MonitorCreate: ["description"],
  visual_explainer: ["topic"],
};

// bash 的命令翻成人话：这个命令是干嘛的，不是命令长什么样
const CMD_RULES: Array<[RegExp, string]> = [
  [/\bsystemctl\s+(restart|reload|try-restart)\b/, "重启服务"],
  [/\bsystemctl\s+(start|stop|enable|disable)\b/, "起停服务"],
  [/\bsystemctl\s+status\b/, "查服务状态"],
  [/\bsystemctl\s+(cat|show)\b/, "看服务配置"],
  [/\bjournalctl\b/, "翻服务日志"],
  [/\b(docker|podman)\b/, "动容器"],
  [/\b(npm|pnpm|yarn|bun)\s+(i|install|add|update)\b/, "装依赖"],
  [/\bgit\s+(commit|push|pull|checkout|merge|rebase|add)\b/, "动版本记录"],
  [/\bgit\s+(log|diff|status|show)\b/, "看改了什么"],
  [/\b(curl|wget|aria2c)\b/, "访问接口"],
  [/\b(python3?|node|deno|bash|sh)\b\s+[^\s]*\.(py|js|mjs|ts|sh)\b/, "跑脚本"],
  [/\b(sed\s+-n|head|tail|less|more|cat)\b/, "看文件内容"],
  [/\b(grep|rg|ag|ack)\b/, "在文件里搜"],
  [/\b(find|fd)\b/, "找文件"],
  [/\b(ls|tree|eza|dir)\b/, "看目录"],
  [/\b(cp|mv|rsync|scp)\b/, "搬文件"],
  [/\brm\b/, "删东西"],
  [/\b(chmod|chown|chgrp)\b/, "改权限"],
  [/\b(ps|top|htop|ss|netstat|lsof|pgrep)\b/, "看进程和端口"],
  [/\b(df|du|ncdu)\b/, "看磁盘"],
  [/\bmkdir\b/, "建目录"],
  [/\b(ssh|scp)\b/, "连远程机器"],
  [/\b(pip|pip3|apt|apt-get|brew)\b/, "装软件"],
];
const CMD_WORDS = new Set([
  "sudo", "systemctl", "journalctl", "docker", "podman", "curl", "wget", "aria2c",
  "python3", "python", "node", "deno", "bash", "sh", "sed", "head", "tail", "less",
  "more", "cat", "grep", "rg", "ag", "ack", "find", "fd", "ls", "tree", "eza", "dir",
  "cp", "mv", "rsync", "scp", "rm", "chmod", "chown", "chgrp", "ps", "top", "htop",
  "ss", "netstat", "lsof", "pgrep", "df", "du", "ncdu", "mkdir", "ssh", "pip", "pip3",
  "apt", "apt-get", "brew", "git", "npm", "pnpm", "yarn", "bun", "echo", "test", "expr",
  "restart", "reload", "start", "stop", "status", "install", "commit", "push", "pull",
]);

function baseName(x: string): string {
  const b = x.split("/").filter(Boolean).pop() || x;
  return b.replace(/\.(ts|tsx|js|jsx|mjs|cjs|json|md|py|css|html|ya?ml|sh|log|txt|db)$/i, "");
}

/** 从一条 bash 命令说出「在干什么、在找什么」，不显示命令原文。 */
export function bashIntent(cmd: unknown): string {
  const c = String(cmd || "").trim();
  if (!c) return "跑一条命令";
  const args = c.split(/[\s|;&<>()]+/).filter(Boolean);
  const rest = args.filter((w) => !/^[-+]/.test(w));

  // 搜内容：在 X 里找 Y
  if (/\b(grep|rg|ag|ack)\b/.test(c)) {
    const pat = rest.find((w) => /^["'].*["']$/.test(w)) || rest.find((w) => !/^(grep|rg|ag|ack)$/.test(w) && !w.includes("/"));
    const file = rest.filter((w) => /\.[a-z]{2,4}$/i.test(w) && w.includes("."));
    let p = pat ? pat.replace(/^["']|["']$/g, "") : "";
    // 正则里带元字符的，别把符号本身当"要找的东西"
    if (/[\\^$*+?\[\](){}|]/.test(p)) p = "";
    const f = file.length ? baseName(file[file.length - 1]) : "";
    if (p && f) return `在 ${f} 里找「${p}」`;
    if (p) return `找「${p}」`;
    if (f) return `在 ${f} 里翻`;
    return "在文件里搜";
  }
  // 访问接口：看路径语义
  if (/\bcurl\b/.test(c)) {
    if (/health|ping|status/.test(c)) return "看看服务还活着没";
    if (/\/live\b/.test(c)) return "接一段实时推送";
    if (/\/api\//.test(c)) return "试一下接口通不通";
    if (/login|auth|token/.test(c)) return "试登录";
    return "访问一个接口";
  }
  // 跑脚本：说清是哪个脚本
  const script = rest.find((w) => /\.(py|js|mjs|ts|sh)$/i.test(w));
  if (script && /\b(python3?|node|bash|sh|deno)\b/.test(c)) return `跑 ${baseName(script)} 脚本`;
  // 看文件内容：说清哪个文件
  if (/\b(sed\s+-n|head|tail|less|more|cat)\b/.test(c)) {
    const f = rest.filter((w) => w.includes("/") || /\.[a-z]{2,4}$/i.test(w)).pop();
    return f ? `看 ${baseName(f)} 里的内容` : "看文件内容";
  }
  // 日志：说清哪个服务
  if (/\bjournalctl\b/.test(c)) {
    const svc = rest.filter((w) => /^[a-z][a-z0-9-]{2,}$/i.test(w) && !CMD_WORDS.has(w.toLowerCase())).pop();
    return svc ? `翻 ${svc} 最近的日志` : "翻服务日志";
  }

  let label = "";
  for (const [re, l] of CMD_RULES) {
    if (re.test(c)) {
      label = l;
      break;
    }
  }
  if (!label) return "跑一条命令";
  const target = rest
    .filter((w) => /^[a-z][a-z0-9-]{3,}$/i.test(w) && !CMD_WORDS.has(w.toLowerCase()))
    .pop();
  return target ? `${label} · ${target}` : label;
}

const CMD_SYS = `你看到的是 AI 助手刚刚执行的一条命令，以及它执行前在想什么。
用一句中文说出这条命令的**意图**：它想达成什么、想确认什么、想找出什么。说意图，不说手段。
规则：16 字以内；不要出现命令名、文件名、路径、参数、端口、缩写字母；不要引号和编号。
只输出这一句话。`;

/** 让模型说清这条命令到底想干嘛；超时或失败返回空串，由 bashIntent 规则兜底。 */
async function cmdIntent(ctx: any, cmd: string, hint = ""): Promise<string> {
  const model = pickModel(ctx);
  if (!model) return "";
  const text = String(cmd || "").trim();
  if (!text) return "";
  try {
    const res: any = await Promise.race([
      ctx.modelRegistry.complete(
        model,
        {
          systemPrompt: CMD_SYS,
          messages: [
            {
              role: "user",
              content: [
                { type: "text", text: (hint ? `他刚才在想：${hint.slice(-300)}\n\n` : "") + `执行的命令：${text.slice(0, 800)}` },
              ],
              timestamp: Date.now(),
            },
          ],
        },
        { cacheRetention: "none" },
      ),
      new Promise((r) => setTimeout(() => r(null), 5000)),
    ]);
    if (!res) return "";
    const out = (res.content || [])
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text)
      .join("")
      .trim();
    return out.split("\n")[0].replace(/^[-•*\d.、)\s]+/, "").replace(/[""'']/g, "").slice(0, 40);
  } catch {
    return "";
  }
}

type Sess = {
  seg: string;
  ctx: any;
  chain: Promise<void>;
  pending: number;
};

const sessions = new Map<string, Sess>();
const clients = new Set<ServerResponse>();
/** 每个 SSE 连接上报的会话 id，仅用于诊断串会话问题 */
const clientSids = new Map<ServerResponse, string>();
/** 前端启动阶段上报，用来判断脚本跑到哪一步 */
const pings: string[] = [];
let enabled = true;

function sidOf(ctx: any): string {
  try {
    return ctx?.sessionManager?.getSessionId?.() || "default";
  } catch {
    return "default";
  }
}

function sess(ctx: any): Sess {
  const sid = sidOf(ctx);
  let s = sessions.get(sid);
  if (!s) {
    s = { seg: "", ctx, chain: Promise.resolve(), pending: 0 };
    sessions.set(sid, s);
  }
  s.ctx = ctx;
  return s;
}

function emit(payload: Record<string, unknown>) {
  const line = `data: ${JSON.stringify(payload)}\n\n`;
  for (const c of clients) {
    try {
      c.write(line);
    } catch {
      clients.delete(c);
    }
  }
}

function shortName(p: unknown): string {
  if (typeof p !== "string" || !p) return "";
  const stripped = p.replace(/^https?:\/\/[^/]+\//, "");
  const parts = stripped.split("/").filter(Boolean);
  const base = parts.slice(-1)[0] || stripped;
  // 去掉扩展名，少一个技术符号
  return base.replace(/\.(ts|tsx|js|jsx|mjs|cjs|json|md|py|css|html|ya?ml|sh|db|log)$/i, "");
}

function describeTool(name: string, args: any): string {
  if (name === "bash") return bashIntent(args?.command);
  const label = TOOL_LABEL[name] || name;
  const keys = TOOL_ARG[name] || [];
  for (const k of keys) {
    let v = args?.[k];
    if (v === undefined || v === null) continue;
    if (k === "path" || k === "url" || k === "uris") v = shortName(String(Array.isArray(v) ? v[0] : v));
    let s = String(v).replace(/\s+/g, " ").trim();
    if (s.length > 28) s = s.slice(0, 27) + "…";
    return s ? `${label} ${s}` : label;
  }
  return label;
}

function shouldCut(s: string): boolean {
  if (s.length >= MAX_SEG) return true;
  if (s.length >= MIN_SEG && /[。！？!?\n]\s*$/.test(s)) return true;
  return false;
}

function flushSeg(s: Sess, sid: string) {
  const text = s.seg.trim();
  s.seg = "";
  if (text.length < 8) return;
  rewrite(s, sid, text);
}

/** 改写用的模型：虚拟路由模型（如 group/df-jev）每轮都要先判档，实测 4–6 秒；
 *  优先换同 provider 下的物理模型直连。用 PI_WEB_LIVE_MODEL=<provider>/<id> 可显式指定。 */
function pickModel(ctx: any) {
  const cur = ctx?.model;
  if (!cur) return null;
  const reg = ctx?.modelRegistry;
  const env = process.env.PI_WEB_LIVE_MODEL;
  if (env && reg?.find) {
    const i = env.indexOf("/");
    const p = i > 0 ? env.slice(0, i) : cur.provider;
    const id = i > 0 ? env.slice(i + 1) : env;
    try {
      const found = reg.find(p, id);
      if (found) return found;
    } catch {}
  }
  if (reg?.find && typeof cur.id === "string" && cur.id.startsWith("group/")) {
    for (const cand of ["auto/dfmodel", cur.id.replace(/^group\//, "")]) {
      try {
        const found = reg.find(cur.provider, cand);
        if (found) return found;
      } catch {}
    }
  }
  return cur;
}

function rewrite(s: Sess, sid: string, text: string) {
  if (s.pending >= MAX_PENDING) return; // 追不上就丢，别积压
  s.pending++;
  s.chain = s.chain
    .then(async () => {
      if (!enabled) return;
      const ctx = s.ctx;
      const model = pickModel(ctx);
      if (!model) return;
      try {
        const res: any = await Promise.race([
          ctx.modelRegistry.complete(
            model,
            {
              systemPrompt: SYS,
              messages: [
                {
                  role: "user",
                  content: [{ type: "text", text }],
                  timestamp: Date.now(),
                },
              ],
            },
            { cacheRetention: "none" },
          ),
          new Promise((_, rej) => {
            const t = setTimeout(() => rej(new Error("rewrite timeout")), REWRITE_TIMEOUT);
            if (typeof (t as any).unref === "function") (t as any).unref();
          }),
        ]);
        const out = (res?.content || [])
          .filter((c: any) => c.type === "text")
          .map((c: any) => c.text)
          .join("");
        const lines = out
          .split("\n")
          .map((line: string) =>
            line
              .replace(/^[-•*\d.、)\s]+/, "")
              .replace(/^["「『]|["」』]$/g, "")
              .trim(),
          )
          // 过滤照抄的噪声：带代码/表格符号、英文术语、长数字的行一律不要
          .filter(
            (line: string) =>
              line.length > 0 &&
              line.length <= 18 &&
              !/[|[\]{}%#=<>_\\]/.test(line) &&
              !/\b(?:acp|api|json|sse|css|html|ctx|sid|pid|url|http|localhost|status|result|delta|token)\b/i.test(line) &&
              !/\d{3,}/.test(line),
          )
          .slice(0, MAX_LINES);
        if (lines.length) emit({ kind: "lines", sid, lines });
      } catch (e: any) {
        const name = String(e?.name || "");
        if (name !== "AbortError") {
          emit({ kind: "warn", sid, message: String(e?.message || e).slice(0, 160) });
        }
      }
    })
    .finally(() => {
      s.pending--;
    });
}

function startServer() {
  const server = createServer((req, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "content-type");
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }
    const url = req.url || "";
    const q = url.includes("?") ? new URLSearchParams(url.slice(url.indexOf("?") + 1)) : null;
    const askedSid = q?.get("sid") || "";
    if (url.startsWith("/live")) {
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });
      res.write(`data: ${JSON.stringify({ kind: "hello", enabled })}\n\n`);
      clients.add(res);
      clientSids.set(res, askedSid);
      req.on("close", () => {
        clients.delete(res);
        clientSids.delete(res);
      });
      return;
    }
    if (url.startsWith("/ping")) {
      const qq = url.includes("?") ? new URLSearchParams(url.slice(url.indexOf("?") + 1)) : null;
      pings.push(`${new Date().toISOString().slice(11, 19)} ${qq?.get("step") || "?"} sid=${qq?.get("sid") || "-"}`);
      if (pings.length > 20) pings.shift();
      res.writeHead(204);
      res.end();
      return;
    }
    if (url.startsWith("/health")) {
      let pending = 0;
      for (const s of sessions.values()) pending += s.pending;
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          ok: true,
          enabled,
          clients: clients.size,
          sessions: sessions.size,
          pending,
          clientSids: [...clientSids.values()],
          pings,
          serverSids: [...sessions.keys()],
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end();
  });
  server.on("error", () => {
    /* 端口被占就静默放弃，不影响 agent */
  });
  server.listen(PORT, "127.0.0.1");
  const timer = setInterval(() => {
    for (const c of clients) {
      try {
        c.write(": ping\n\n");
      } catch {
        clients.delete(c);
      }
    }
  }, 20000);
  if (typeof timer.unref === "function") timer.unref();
}

export default function piWebLive(pi: ExtensionAPI) {
  startServer();

  pi.on("message_update", async (event: any, ctx: any) => {
    if (!enabled) return;
    const ev = event?.assistantMessageEvent;
    if (!ev) return;
    const s = sess(ctx);
    const sid = sidOf(ctx);
    if (ev.type === "thinking_delta" && typeof ev.delta === "string") {
      s.seg += ev.delta;
      if (shouldCut(s.seg)) flushSeg(s, sid);
      return;
    }
    if (ev.type === "thinking_end") {
      if (typeof ev.content === "string" && ev.content.trim().length > s.seg.trim().length) {
        s.seg = ev.content;
      }
      flushSeg(s, sid);
    }
  });

  pi.on("tool_execution_start", async (event: any, ctx: any) => {
    if (!enabled) return;
    const sid = sidOf(ctx);
    const name = event?.toolName || "";
    if (name === "bash") {
      // 先用规则版即时占位（零延迟），模型算出真正的意图后再把那一行改写掉
      const cmd = event?.args?.command;
      const tid = event?.toolCallId || `t${Date.now()}`;
      const placeholder = bashIntent(cmd);
      emit({ kind: "tool", sid, tid, text: placeholder });
      const leak = sessions.get(sid)?.seg || "";
      cmdIntent(ctx, cmd, leak)
        .then((said) => {
          if (said && said !== placeholder) emit({ kind: "tool-intent", sid, tid, text: said });
        })
        .catch(() => {});
      return;
    }
    emit({ kind: "tool", sid, text: describeTool(name, event?.args) });
  });

  pi.on("agent_start", async (_event: any, ctx: any) => {
    const s = sess(ctx);
    s.seg = "";
    emit({ kind: "start", sid: sidOf(ctx) });
  });

  pi.on("agent_end", async (_event: any, ctx: any) => {
    const s = sess(ctx);
    flushSeg(s, sidOf(ctx));
    emit({ kind: "end", sid: sidOf(ctx) });
  });

  const liveCmd = {
    description: "开关 pi-web 内心独白浮层条（on / off / status）",
    handler: async (args: string, ctx: any) => {
      const a = (args || "").trim().toLowerCase();
      if (a === "off") {
        enabled = false;
        emit({ kind: "off" });
        ctx.ui?.notify?.("内心独白已关闭", "info");
        return;
      }
      if (a === "on") {
        enabled = true;
        emit({ kind: "hello", enabled });
        ctx.ui?.notify?.("内心独白已开启", "info");
        return;
      }
      let pending = 0;
      for (const s of sessions.values()) pending += s.pending;
      ctx.ui?.notify?.(
        `内心独白：${enabled ? "开" : "关"}｜连接 ${clients.size}｜会话 ${sessions.size}｜待改写 ${pending}`,
        "info",
      );
    },
  };
  pi.registerCommand("d-live", liveCmd);
  pi.registerCommand("live", liveCmd);
}
