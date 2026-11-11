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
import { openSync, readSync, closeSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";

const PORT = 18999;
const MIN_SEG = 200; // 至少这么多字才允许按句号切（每段改写 ~2s，切太碎会刷屏）
const MAX_SEG = 500; // 硬上限，超过无条件切
const MAX_LINES = 3;
const MAX_PENDING = 4; // 队列上限，超了就丢新段，保证实时性
const REWRITE_TIMEOUT = 25000; // 单次改写硬超时（段变长后模型更慢）

// ── 判档回显：tail magpie routing jsonl，把 rule.pick（判档结果）推给对应会话的浮层条 ──
const ROUTING_DIR = "/home/duanz/.config/magpie/routing";
const ROUTING_TAIL_MS = 2000; // 轮询间隔
const ROUTING_MAX_BYTES = 256 * 1024; // 每次最多读文件尾这么多，routing 行单条几十 KB 也够

function todayRoutingFile(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return join(ROUTING_DIR, `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}.jsonl`);
}

function startEffortWatcher(emitFn: (p: Record<string, unknown>) => void) {
  let offset = 0; // 上次读到的字节位置
  let lastSize = -1;
  const timer = setInterval(() => {
    try {
      const file = todayRoutingFile();
      if (!existsSync(file)) return;
      const size = statSync(file).size;
      if (size === lastSize) return;
      // 文件被截断/轮转就从头部重读
      const start = size < offset ? 0 : offset;
      const len = Math.min(size - start, ROUTING_MAX_BYTES);
      if (len <= 0) { offset = size; lastSize = size; return; }
      const buf = Buffer.alloc(len);
      const fd = openSync(file, "r");
      try {
        readSync(fd, buf, 0, len, start);
      } finally {
        closeSync(fd);
      }
      offset = start + len;
      lastSize = size;
      for (const line of buf.toString("utf8").split("\n")) {
        if (!line.includes('"pick"')) continue;
        try {
          const rec = JSON.parse(line);
          const rule = rec.rule || {};
          const pick = rule.pick;
          if (!pick || typeof pick !== "string") continue;
          const sid = String(rec.session || "");
          if (!sid) continue;
          emitFn({
            kind: "effort",
            sid,
            pick,
            sent: rec.effort || "",
            degraded: Boolean(rule.classified && rule.classified.degraded) || /DEGRADED/.test(line),
          });
        } catch {}
      }
    } catch {}
  }, ROUTING_TAIL_MS);
  if (typeof timer.unref === "function") timer.unref();
}

const SYS = `把下面这段思考，改写成给用户看的进度解说：正在做什么、为什么要这么做、做完会怎样。

规则：
- 说人话，像朋友在旁边随口讲一句，带点画面感，可以用「先翻翻」「挨个对一遍」「这就去」「稳了」这类口语；
- 不用第一人称，不出现"我"；用无主语或"正在/已经/接下来/这就"开头；
- 每句 16~24 字，把前因后果说完整：先说要做什么或看到什么，再说为什么这么选；
- 最多 ${MAX_LINES} 句，每句一行；每句开头放 1 个贴切的 emoji，句尾必须有标点（…… / 。 / ！）；
- 一轮里只围绕一个目标往前推，几句连起来要像同一条线：第二句起用「接着」「于是」「这下」「所以」「接下来」「顺手」这类词承接上一句，别忽然跳到无关的事，也别重复前面说过的内容；
- 输入里若给了「前面已经说过」，就从那儿接着往下说，把新的发现和下一步接上，不要另起炉灶；
- emoji 别重复；句子要生动，避免「正在处理」「进行分析」这类空话；
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
  // 丢掉重定向目标：>/dev/null 会被当成文件名，播出去就成了「看 null 里的内容」
  const DEVNULL = /^(?:\/dev\/(?:null|stdout|stderr|zero|fd\/\d+)|\/proc\/self\/fd\/\d+)$/i;
  const JUNKNAME = /^(?:null|undefined|nil|true|false|nan|\d+)$/i;
  const rest = args.filter((w) => !/^[-+]/.test(w) && !DEVNULL.test(w));

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
    const f = rest
      .filter((w) => !/^\/dev\//.test(w))
      .filter((w) => w.includes("/") || /\.[a-z]{2,4}$/i.test(w))
      .pop();
    const n = f ? baseName(f) : "";
    return n && !JUNKNAME.test(n) ? `看 ${n} 里的内容` : "看文件内容";
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
用一句中文说出这条命令的**意图**：它想达成什么、想确认什么、想找出什么。说意图，不说手段，说得口语、有画面感。
规则：16 字以内；句首放 1 个贴切的 emoji，句尾加标点（…… 或 。）；不要出现命令名、文件名、路径、参数、端口、缩写字母；不要引号和编号。
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

const SUMMARY_SYS = `用一句中文向用户交代：这一轮到底干了什么、成没成。
规则：30 字以内；说结果，不说过程；口语一点，别用「已完成」「进行处理」这类空话；不出现文件名、路径、命令、缩写字母；不加引号编号；句首 1 个 emoji，句尾加标点。
只输出这一句话。`;

/** 一轮跑完给一句结论。模型超时或说得不像就用规则句兜底，永远不空着。 */
async function roundSummary(
  ctx: any,
  info: { ms: number; steps: number; fails: number; names: string[] },
): Promise<string> {
  const sec = info.ms > 0 ? Math.round(info.ms / 1000) : 0;
  const fallback = `🎯 这一轮想完了，${sec}s、${info.steps} 步${info.fails ? `，有 ${info.fails} 处没成` : "，都顺"}。`;
  const model = pickModel(ctx);
  if (!model || info.steps === 0) return fallback;
  const kinds = [...new Set(info.names)].slice(0, 6).join("、");
  try {
    const res: any = await Promise.race([
      ctx.modelRegistry.complete(
        model,
        {
          systemPrompt: SUMMARY_SYS,
          messages: [
            {
              role: "user",
              content: [
                {
                  type: "text",
                  text: `这一轮做了 ${info.steps} 步（${kinds}），其中失败 ${info.fails} 次，共 ${sec} 秒。`,
                },
              ],
              timestamp: Date.now(),
            },
          ],
        },
        { cacheRetention: "none" },
      ),
      new Promise((r) => setTimeout(() => r(null), 15000)),
    ]);
    const out = (res?.content || [])
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text)
      .join("")
      .trim();
    const one =
      out
        .split("\n")
        .map((x: string) =>
          x
            .replace(/^[-•*\d.、)\s]+/, "")
            .replace(/^["「『]|["」』]$/g, "")
            .trim(),
        )
        .filter(Boolean)[0] || "";
    if (!one || one.length > 40) return fallback;
    return one;
  } catch {
    return fallback;
  }
}

type Sess = {
  seg: string;
  ctx: any;
  chain: Promise<void>;
  pending: number;
  /** 本轮开始时间，用来算总耗时 */
  t0: number;
  /** 本轮工具步数与失败数 */
  tools: number;
  fails: number;
  names: string[];
  /** 本轮已经播过的短句，喂给下一次改写，让前后能接上 */
  history: string[];
};

// pi-web 会为每个会话各加载一份扩展。模块级变量在不同实例之间不共享，
// 只有抢到端口的那个实例能收到浏览器连接 —— 用 globalThis 把状态提到进程级，
// 否则表现为“只有第一个开着的会话有条子”。
const SHARED: any =
  (globalThis as any).__dliveShared ||
  ((globalThis as any).__dliveShared = {
    sessions: new Map<string, Sess>(),
    clients: new Set<ServerResponse>(),
    clientSids: new Map<ServerResponse, string>(),
    pings: [] as string[],
    recent: [] as string[],
    listening: false,
  });

const sessions: Map<string, Sess> = SHARED.sessions;
const clients: Set<ServerResponse> = SHARED.clients;
/** 每个 SSE 连接上报的会话 id，仅用于诊断串会话问题 */
const clientSids: Map<ServerResponse, string> = SHARED.clientSids;
/** 前端启动阶段上报，用来判断脚本跑到哪一步 */
const pings: string[] = SHARED.pings;
const recent: string[] = SHARED.recent;
let enabled = true;

const lastSidDebug: Record<string, string> = {};

// 工具事件的 ctx 不一定带 sessionManager，记住最近一次真实会话，别让推送退化成 default 被过滤掉
let lastRealSid = "";

function sidOf(ctx: any): string {
  try {
    const sm = ctx?.sessionManager;
    const byApi = String(sm?.getSessionId?.() || "");
    const file = String(sm?.getSessionFile?.() || sm?.getSessionPath?.() || "");
    const m = file.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$/);
    lastSidDebug.api = byApi;
    lastSidDebug.file = file;
    lastSidDebug.picked = m ? m[1] : byApi;
    const real = m ? m[1] : byApi;
    if (real) {
      lastRealSid = real;
      return real;
    }
  } catch {}
  return lastRealSid || "default";
}

const INSTANCE = Math.random().toString(36).slice(2, 8);

/**
 * 同一会话只让一份扩展实例处理事件。
 * pi-web 会为同一个会话加载多份扩展，不去重的话模型改写、工具意图都会重复跑两遍。
 */
function claim(sid: string): boolean {
  if (!SHARED.owner) SHARED.owner = new Map<string, string>();
  const cur = SHARED.owner.get(sid);
  if (!cur) {
    SHARED.owner.set(sid, INSTANCE);
    return true;
  }
  return cur === INSTANCE;
}

function sess(ctx: any): Sess {
  const sid = sidOf(ctx);
  let s = sessions.get(sid);
  if (!s) {
    s = { seg: "", ctx, chain: Promise.resolve(), pending: 0, t0: 0, tools: 0, fails: 0, names: [], history: [] };
    sessions.set(sid, s);
  }
  s.ctx = ctx;
  return s;
}

function emit(payload: Record<string, unknown>) {
  try {
    // pi-web 同一个会话可能加载两份扩展（重启接力时），两份 handler 都连着共享的 clients，
    // 不去重的话每条推送会发两次。
    const key = `${String(payload.sid || "")}|${String(payload.kind)}|${String(payload.tid || "")}|${String(payload.text || "")}`;
    const now = Date.now();
    const last = SHARED.lastEmit;
    if (last && last.k === key && now - last.t < 150) return;
    SHARED.lastEmit = { k: key, t: now };
    const t = new Date().toTimeString().slice(0, 8);
    recent.push(`${t} ${String(payload.kind)} sid=${String(payload.sid || "-").slice(0, 8)}`);
    if (recent.length > 40) recent.splice(0, recent.length - 40);
  } catch {}
  const line = `data: ${JSON.stringify(payload)}\n\n`;
  const sid = typeof payload.sid === "string" ? payload.sid : "";
  const unknown = !sid || sid === "default";
  for (const c of clients) {
    // 只推给「报了号且号对得上」的页面：空号连接（旧版页面）一律不推，
    // 否则一个页面会收到所有会话的播报，串到别的会话里。
    const want = clientSids.get(c) || "";
    if (!want) continue;
    if (!unknown && want !== sid) continue;
    try {
      c.write(line);
    } catch {
      clients.delete(c);
      clientSids.delete(c);
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

// 系统注入的上下文（压缩块、记忆注入）长得像“思考”，但不是，不能播给用户
const NOISE =
  /(CONTEXT BREAKDOWN|COMPRESSED BLOCKS|openviking-context|OpenViking context|\[ACP\]|Compressed m\d|<acp\b|viking:\/\/|User said \(m\d)/i;
function isNoise(text: string): boolean {
  return NOISE.test(text);
}

function flushSeg(s: Sess, sid: string) {
  const text = s.seg.trim();
  s.seg = "";
  if (text.length < 8) return;
  if (isNoise(text)) return; // 系统注入的上下文不是思考，直接丢
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
      const prior = s.history.slice(-4);
      const lead = prior.length
        ? "前面已经说过（接着往下讲，别重复）：\n" + prior.join("\n") + "\n\n这一段新的思考：\n"
        : "";
      try {
        const res: any = await Promise.race([
          ctx.modelRegistry.complete(
            model,
            {
              systemPrompt: SYS,
              messages: [
                {
                  role: "user",
                  content: [{ type: "text", text: lead + text }],
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
              line.length >= 8 &&
              line.length <= 40 &&
              !isNoise(line) &&
              !/[|[\]{}%#=<>_\\]/.test(line) &&
              !/\b(?:acp|api|json|sse|css|html|ctx|sid|pid|url|http|localhost|status|result|delta|token)\b/i.test(line) &&
              !/\d{3,}/.test(line),
          )
          .slice(0, MAX_LINES);
        if (lines.length) {
          emit({ kind: "lines", sid, lines });
          s.history = s.history.concat(lines).slice(-8);
        }
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
      pings.push(
        `${new Date().toISOString().slice(11, 19)} ${qq?.get("step") || "?"} p=${qq?.get("pid") || "?"} sid=${(qq?.get("sid") || "-").slice(0, 8)}`,
      );
      if (pings.length > 40) pings.shift();
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
          sidDebug: lastSidDebug,
          serverSids: [...sessions.keys()],
          recent,
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end();
  });
  // pi-web 每个会话都会加载一份扩展；端口只能被第一份占到。
  // 重复绑定是正常的，不能让它打断这个会话里后面的 pi.on(...) 注册。
  server.on("error", (e: any) => {
    if (e?.code === "EADDRINUSE") return;
  });
  if (!SHARED.listening) {
    SHARED.listening = true;
    try {
      server.listen(PORT, "127.0.0.1");
    } catch {
      SHARED.listening = false;
    }
  }
  // 心跳只挂一份：每个会话都会加载一份扩展，无条件起定时器会变成 N 份重复推送
  if (!SHARED.beat) {
    const timer = setInterval(() => {
      for (const c of clients) {
        try {
          // 不只是保活：前端把这条当心跳，收不到就自己重连
          c.write('data: {"kind":"beat"}\n\n');
        } catch {
          clients.delete(c);
          clientSids.delete(c);
        }
      }
    }, 15000);
    if (typeof timer.unref === "function") timer.unref();
    SHARED.beat = timer;
  }
}

export default function piWebLive(pi: ExtensionAPI) {
  startServer();
  startEffortWatcher(emit);

  pi.on("message_update", async (event: any, ctx: any) => {
    if (!enabled) return;
    const ev = event?.assistantMessageEvent;
    if (!ev) return;
    const sid = sidOf(ctx);
    if (!claim(sid)) return;
    const s = sess(ctx);
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
    if (!claim(sid)) return;
    const name = event?.toolName || "";
    const tid = String(event?.toolCallId || "");
    const s = sess(ctx);
    s.tools++;
    if (name) s.names.push(name);
    if (name === "bash") {
      // 先用规则版即时占位（零延迟），模型算出真正的意图后再把那一行改写掉
      const cmd = event?.args?.command;
      const key = tid || `t${Date.now()}`;
      const placeholder = bashIntent(cmd);
      emit({ kind: "tool", sid, tid: key, text: placeholder });
      const leak = s.seg || "";
      cmdIntent(ctx, cmd, leak)
        .then((said) => {
          if (said && said !== placeholder) emit({ kind: "tool-intent", sid, tid: key, text: said });
        })
        .catch(() => {});
      return;
    }
    emit({ kind: "tool", sid, tid: tid || null, text: describeTool(name, event?.args) });
  });

  // 工具跑完了：告诉前端这一行的成败与耗时（成败和耗时都由 pi 自己测，不用前端算）
  pi.on("tool_execution_end", async (event: any, ctx: any) => {
    if (!enabled) return;
    const tid = String(event?.toolCallId || "");
    if (!tid) return;
    const sid = sidOf(ctx);
    if (!claim(sid)) return;
    const isErr = !!event?.isError;
    if (isErr) {
      const s = sessions.get(sid);
      if (s) s.fails++;
    }
    emit({
      kind: "tool-end",
      sid,
      tid,
      ok: !isErr,
      ms:
        typeof event?.durationMs === "number" && event.durationMs >= 0
          ? Math.round(event.durationMs)
          : null,
    });
  });

  pi.on("agent_start", async (_event: any, ctx: any) => {
    const s = sess(ctx);
    s.seg = "";
    s.t0 = Date.now();
    s.tools = 0;
    s.fails = 0;
    s.names = [];
    s.history = []; // 新一轮重新起一条线，别接着上一轮的尾巴
    emit({ kind: "start", sid: sidOf(ctx) });
  });

  pi.on("agent_end", async (_event: any, ctx: any) => {
    const s = sess(ctx);
    const sid = sidOf(ctx);
    // 收尾不让 claim 挡：两份实例都可能收到 agent_end，靠下面的幂等去重
    SHARED.recent.push(`${new Date().toTimeString().slice(0, 8)} agent_end-enter sid=${sid.slice(0, 8)} inst=${INSTANCE}`);
    if (SHARED.recent.length > 40) SHARED.recent.shift();
    flushSeg(s, sid);
    const info = {
      ms: s.t0 ? Date.now() - s.t0 : 0,
      steps: s.tools,
      fails: s.fails,
      names: s.names.slice(0, 20),
    };
    s.t0 = 0;
    s.tools = 0;
    s.fails = 0;
    s.names = [];
    emit({ kind: "end", sid });
    // 一轮只发一条结论：两份实例都跑 agent_end 时只留第一条
    const nowS = Date.now();
    if (SHARED.lastSummary && SHARED.lastSummary.sid === sid && nowS - SHARED.lastSummary.t < 15000) return;
    SHARED.lastSummary = { sid, t: nowS };
    // 结论异步补发：先让条子切到“收尾”，模型慢也不堵这一轮
    roundSummary(ctx, info)
      .then((text) => {
        if (text) emit({ kind: "summary", sid, text, ms: info.ms, steps: info.steps, fails: info.fails });
      })
      .catch(() => {});
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
