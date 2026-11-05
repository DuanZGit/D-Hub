/**
 * auto-name —— 会话消息涨到阈值就自动重新生成标题。
 *
 * 两层命名：
 *   1. agent 刚启动、会话还没有名字时，用第一条用户消息的前 N 字直接设名
 *      （零模型成本，通知/侧栏立刻可辨识）；
 *   2. 每轮 agent 彻底跑完后检查一次，距上次命名新增 ≥ AUTO_NAME_STEP 条
 *      会话条目就调 pi-web 的 POST /api/sessions/:id/auto-name 精修。
 * 只在 pi-web 里生效；CLI 下没有 PI_SESSION_ID，扩展自己跳过。
 *
 * 环境变量：
 *   AUTO_NAME_STEP      增量阈值（默认 20）
 *   AUTO_NAME_DEBOUNCE  两次命名最小间隔秒数（默认 300）
 *   AUTO_NAME_OFF=1     临时关闭
 *   PI_WEB_PORT         实例端口（默认先试 30142，再试 30152）
 *
 * 状态与日志：~/.pi/agent/auto-name-state.json / auto-name.log
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const AGENT_DIR = join(homedir(), ".pi", "agent");
const STATE_FILE = join(AGENT_DIR, "auto-name-state.json");
const LOG_FILE = join(AGENT_DIR, "auto-name.log");

const STEP = Math.max(1, Number(process.env.AUTO_NAME_STEP ?? 20));
const QUICK_NAME_MAX = Math.max(6, Number(process.env.AUTO_NAME_QUICK_MAX ?? 24));
const DEBOUNCE_MS = Math.max(0, Number(process.env.AUTO_NAME_DEBOUNCE ?? 300)) * 1000;
const CANDIDATE_PORTS = [
	process.env.PI_WEB_PORT,
	"30142",
	"30152",
].filter((p): p is string => !!p);

type SessionState = { count: number; at: number; name?: string };
type StateMap = Record<string, SessionState>;

function log(line: string) {
	try {
		const stamp = new Date().toISOString();
		appendFileSync(LOG_FILE, `${stamp} ${line}\n`);
	} catch {
		// 日志写不进去不影响主流程
	}
}

function loadState(): StateMap {
	try {
		return JSON.parse(readFileSync(STATE_FILE, "utf8")) as StateMap;
	} catch {
		return {};
	}
}

function saveState(state: StateMap) {
	try {
		writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
	} catch (error) {
		log(`state save failed: ${error instanceof Error ? error.message : String(error)}`);
	}
}

async function resolvePort(sessionId: string): Promise<string | null> {
	for (const port of CANDIDATE_PORTS) {
		try {
			const res = await fetch(`http://127.0.0.1:${port}/api/sessions/${sessionId}`, {
				signal: AbortSignal.timeout(3000),
			});
			if (res.ok) return port;
		} catch {
			// 端口不在或不是 pi-web，继续试下一个
		}
	}
	return null;
}

let inFlight = false;

type LooseEntry = { type?: string; message?: { role?: string; content?: unknown } };

function plainText(content: unknown): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return content
		.map((part) =>
			part && typeof part === "object" && (part as { type?: string }).type === "text"
				? String((part as { text?: string }).text ?? "")
				: "",
		)
		.filter(Boolean)
		.join(" ");
}

/** 用第一条用户消息当临时标题：去图片标记、代码块和 Markdown 符号，截前 N 字。 */
function quickName(entries: LooseEntry[]): string {
	for (const entry of entries) {
		if (entry?.type !== "message" || entry.message?.role !== "user") continue;
		const raw = plainText(entry.message.content)
			.replace(/\[Image:[^\]]*\]/g, " ")
			.replace(/```[\s\S]*?```/g, " ")
			.replace(/\s+/g, " ")
			.trim();
		if (!raw) continue;
		if (raw.startsWith("/") && raw.length < 12) continue;
		return raw.length > QUICK_NAME_MAX
			? `${raw.slice(0, QUICK_NAME_MAX).trimEnd()}…`
			: raw;
	}
	return "";
}

export default function autoName(pi: ExtensionAPI) {
	if (process.env.AUTO_NAME_OFF === "1") return;

	// 首条消息就把会话名定下来，短会话的通知标题才不会是“任务完成”。
	pi.on("agent_start", (_event, ctx) => {
		try {
			if (ctx.sessionManager.getSessionName()) return;
			const name = quickName(ctx.sessionManager.getEntries() as LooseEntry[]);
			if (name) pi.setSessionName(name);
		} catch (error) {
			log(`quick name failed: ${error instanceof Error ? error.message : String(error)}`);
		}
	});

	pi.on("agent_settled", async (_event, ctx: ExtensionContext) => {
		const sessionId = process.env.PI_SESSION_ID ?? ctx.sessionManager.getSessionId();
		if (!sessionId) return;
		if (inFlight) return;

		const count = ctx.sessionManager.getEntries().length;
		const state = loadState();
		const last = state[sessionId];

		// 首次：等攒够 STEP 条再命名一次，避免每条新会话都烧一次模型
		const baseline = last?.count ?? 0;
		if (count - baseline < STEP) return;
		if (last && Date.now() - last.at < DEBOUNCE_MS) return;

		inFlight = true;
		try {
			const port = await resolvePort(sessionId);
			if (!port) {
				log(`skip ${sessionId}: no pi-web answered`);
				return;
			}

			const res = await fetch(`http://127.0.0.1:${port}/api/sessions/${sessionId}/auto-name`, {
				method: "POST",
				signal: AbortSignal.timeout(95_000),
			});
			const body = (await res.json().catch(() => ({}))) as { title?: string; error?: string };

			if (!res.ok || !body.title) {
				log(`fail ${sessionId}: HTTP ${res.status} ${body.error ?? ""}`);
				// 命名失败不推进基线，下一轮再试；但记时间防止刷屏重试
				state[sessionId] = { count: baseline, at: Date.now(), name: last?.name };
				saveState(state);
				return;
			}

			const title = body.title.trim();
			state[sessionId] = { count, at: Date.now(), name: title };
			saveState(state);
			log(`ok ${sessionId}: ${baseline} -> ${count} "${title}"`);
		} catch (error) {
			log(`error ${sessionId}: ${error instanceof Error ? error.message : String(error)}`);
		} finally {
			inFlight = false;
		}
	});
}
