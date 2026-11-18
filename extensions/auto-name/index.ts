/**
 * auto-name —— 会话聊到一定量就自动重新生成标题。
 *
 * 两层命名：
 *   1. agent 刚启动、会话还没有名字时，用第一条用户消息的前 N 字直接设名
 *      （零模型成本，通知/侧栏立刻可辨识）；
 *   2. 每轮 agent 彻底跑完后检查一次，距上次命名新增 ≥ AUTO_NAME_STEP 条
 *      用户消息就调 pi-web 的 POST /api/sessions/:id/auto-name 精修。
 * 只在 pi-web 里生效；CLI 下没有 PI_SESSION_ID，扩展自己跳过。
 *
 * 三条纪律（借鉴 DeepSeek Harness 的 session-title 设计）：
 *   - 钉住：用户手动改过名之后，本会话永久停止自动命名；
 *   - 锚定：新标题与旧标题高度相似时保留旧标题，避免同主题反复换措辞；
 *   - 单飞：同一会话同时只允许一次命名，不同会话互不阻塞。
 *
 * 环境变量：
 *   AUTO_NAME_STEP      新增多少条用户消息触发一次精修（默认 6）
 *   AUTO_NAME_DEBOUNCE  两次命名最小间隔秒数（默认 300）
 *   AUTO_NAME_KEEP_SIM  新旧标题相似度 ≥ 该值就保留旧标题（默认 0.7，0 关闭）
 *   AUTO_NAME_OFF=1     临时关闭
 *   PI_WEB_PORT         实例端口（默认先试 30142，再试 30152）
 *
 * 状态与日志：~/.pi/agent/auto-name-state.json / auto-name.log
 * 解钉：删掉状态文件里该 sessionId 的条目即可恢复自动命名。
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const AGENT_DIR = join(homedir(), ".pi", "agent");
const STATE_FILE = join(AGENT_DIR, "auto-name-state.json");
const LOG_FILE = join(AGENT_DIR, "auto-name.log");

const STEP = Math.max(1, Number(process.env.AUTO_NAME_STEP ?? 6));
const QUICK_NAME_MAX = Math.max(6, Number(process.env.AUTO_NAME_QUICK_MAX ?? 24));
const DEBOUNCE_MS = Math.max(0, Number(process.env.AUTO_NAME_DEBOUNCE ?? 300)) * 1000;
const KEEP_SIM = Math.min(1, Math.max(0, Number(process.env.AUTO_NAME_KEEP_SIM ?? 0.7)));
const CANDIDATE_PORTS = [
	process.env.PI_WEB_PORT,
	"30142",
	"30152",
].filter((p): p is string => !!p);

type SessionState = {
	/** 已计入的合格用户消息数（不是会话条目数） */
	count: number;
	/** 上次命名时间 */
	at: number;
	/** 扩展自己写进去的标题，用来识别用户手动改名 */
	name?: string;
	/** 用户手动改过名：本会话永久停止自动命名 */
	pinned?: boolean;
};
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

/** 按会话 id 加锁：A 会话在命名时，B 会话照常可以命名。 */
const inFlight = new Set<string>();

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

/** 只认有人类文本的 user/message：工具回灌、空消息、纯图片都不算。 */
function isCountableUser(entry: LooseEntry): boolean {
	if (entry?.type !== "message" || entry.message?.role !== "user") return false;
	return plainText(entry.message.content).trim().length > 0;
}

function countUserMessages(entries: LooseEntry[]): number {
	let n = 0;
	for (const entry of entries) if (isCountableUser(entry)) n += 1;
	return n;
}

/** 用第一条用户消息当临时标题：去图片标记、代码块和 Markdown 符号，截前 N 字。 */
function quickName(entries: LooseEntry[]): string {
	for (const entry of entries) {
		if (!isCountableUser(entry)) continue;
		const raw = plainText(entry.message?.content)
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

/** 归一化：小写，去掉空白、标点和符号，只留字母数字与汉字。 */
function normalizeTitle(title: string): string {
	return title.toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, "");
}

/** 字符二元组 Dice 系数：0 = 完全不同，1 = 完全一致。中英文通用。 */
function similarity(a: string, b: string): number {
	const left = normalizeTitle(a);
	const right = normalizeTitle(b);
	if (!left || !right) return 0;
	if (left === right) return 1;

	const grams = (text: string) => {
		const map = new Map<string, number>();
		for (let i = 0; i < text.length - 1; i += 1) {
			const gram = text.slice(i, i + 2);
			map.set(gram, (map.get(gram) ?? 0) + 1);
		}
		return map;
	};
	const a2 = grams(left);
	const b2 = grams(right);
	let overlap = 0;
	for (const [gram, count] of a2) overlap += Math.min(count, b2.get(gram) ?? 0);
	const total = left.length - 1 + (right.length - 1);
	return total <= 0 ? 0 : (2 * overlap) / total;
}

export default function autoName(pi: ExtensionAPI) {
	if (process.env.AUTO_NAME_OFF === "1") return;

	// 首条消息就把会话名定下来，短会话的通知标题才不会是“任务完成”。
	pi.on("agent_start", (_event, ctx) => {
		try {
			if (ctx.sessionManager.getSessionName()) return;
			const name = quickName(ctx.sessionManager.getEntries() as LooseEntry[]);
			if (!name) return;
			pi.setSessionName(name);
			const sessionId = ctx.sessionManager.getSessionId();
			if (!sessionId) return;
			const state = loadState();
			const last = state[sessionId];
			state[sessionId] = {
				count: last?.count ?? 0,
				at: last?.at ?? 0,
				name,
				pinned: last?.pinned,
			};
			saveState(state);
		} catch (error) {
			log(`quick name failed: ${error instanceof Error ? error.message : String(error)}`);
		}
	});

	pi.on("agent_settled", async (_event, ctx: ExtensionContext) => {
		const sessionId = process.env.PI_SESSION_ID ?? ctx.sessionManager.getSessionId();
		if (!sessionId) return;
		if (inFlight.has(sessionId)) return;

		const state = loadState();
		const last = state[sessionId];

		// 钉住：用户手动改过名，本会话不再自动命名。
		if (last?.pinned) return;

		const currentName = ctx.sessionManager.getSessionName() ?? "";
		if (last?.name && currentName && currentName !== last.name) {
			state[sessionId] = { ...last, pinned: true };
			saveState(state);
			log(`pinned ${sessionId}: user renamed "${last.name}" -> "${currentName}"`);
			return;
		}

		const count = countUserMessages(ctx.sessionManager.getEntries() as LooseEntry[]);
		const baseline = last?.count ?? 0;
		if (count - baseline < STEP) return;
		if (last && Date.now() - last.at < DEBOUNCE_MS) return;

		inFlight.add(sessionId);
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
				state[sessionId] = { count: baseline, at: Date.now(), name: last?.name, pinned: last?.pinned };
				saveState(state);
				return;
			}

			const title = body.title.trim();

			// 锚定：新标题与旧标题高度相似就保留旧的，避免同主题反复换措辞。
			if (last?.name && KEEP_SIM > 0) {
				const score = similarity(last.name, title);
				if (score >= KEEP_SIM) {
					if (currentName !== last.name) pi.setSessionName(last.name);
					state[sessionId] = { count, at: Date.now(), name: last.name, pinned: last?.pinned };
					saveState(state);
					log(`keep ${sessionId}: ${baseline} -> ${count} sim=${score.toFixed(2)} "${last.name}" (新候选 "${title}")`);
					return;
				}
			}

			state[sessionId] = { count, at: Date.now(), name: title, pinned: last?.pinned };
			saveState(state);
			log(`ok ${sessionId}: ${baseline} -> ${count} "${title}"`);
		} catch (error) {
			log(`error ${sessionId}: ${error instanceof Error ? error.message : String(error)}`);
		} finally {
			inFlight.delete(sessionId);
		}
	});
}
