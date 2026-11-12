/**
 * d-split —— 把一个会话按切点拆成两个独立会话文件。
 *
 * 为什么要自己写文件而不是调 fork_branch：会话是树，fork_branch 只能切
 * 「根 → 某条」，切不出「切点之后」那一段。这里按 parentId 链自己拼两段：
 *   A 段 = 根 .. 切点
 *   B 段 = 切点之后 .. leaf（首条 parentId 改指向一条注入的 custom_message）
 * 两段各自写成新 .jsonl，原会话一个字节都不动。
 *
 * 不给 cutAt 时只返回时间轴，让模型先挑 2-3 个候选切点给用户确认。
 *
 * 环境变量：
 *   D_SPLIT_OFF=1         关闭
 *   PI_WEB_PORT           pi-web 端口（默认先试 30142，再试 30152）
 */

import type { ExtensionAPI, ExtensionToolContext } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { Type } from "typebox";

const AGENT_DIR = join(homedir(), ".pi", "agent");
const LOG_FILE = join(AGENT_DIR, "d-split.log");
const CANDIDATE_PORTS = [process.env.PI_WEB_PORT, "30142", "30152"].filter(
	(p): p is string => !!p,
);

const MAX_TIMELINE = Math.max(10, Number(process.env.SPLIT_TIMELINE_MAX ?? 200));

type Entry = Record<string, any> & {
	id?: string;
	parentId?: string | null;
	type?: string;
};

function log(line: string) {
	try {
		appendFileSync(LOG_FILE, `${new Date().toISOString()} ${line}\n`);
	} catch {
		// 日志失败不影响主流程
	}
}

function nowIso() {
	return new Date().toISOString();
}

function shortId(taken: Set<string>): string {
	for (;;) {
		const id = randomUUID().replace(/-/g, "").slice(0, 8);
		if (!taken.has(id)) return id;
	}
}

/** 读会话文件：首行 header，其余每个 id 条目。坏行直接跳过。 */
function loadSession(file: string): { header: any; entries: Entry[] } {
	const text = readFileSync(file, "utf8");
	let header: any = null;
	const entries: Entry[] = [];
	for (const raw of text.split("\n")) {
		const line = raw.trim();
		if (!line) continue;
		let obj: any;
		try {
			obj = JSON.parse(line);
		} catch {
			continue;
		}
		if (obj?.type === "session" && !header) {
			header = obj;
			continue;
		}
		if (obj && typeof obj.id === "string") entries.push(obj);
	}
	if (!header) throw new Error("会话文件缺少 header 行");
	return { header, entries };
}

/** 从 leaf 沿 parentId 回溯到根，返回正序链和 id 索引。 */
function chainToLeaf(entries: Entry[], leafId: string) {
	const map = new Map<string, Entry>();
	for (const e of entries) if (e.id) map.set(e.id, e);
	const chain: Entry[] = [];
	const seen = new Set<string>();
	let cur: string | null | undefined = leafId;
	while (cur && map.has(cur) && !seen.has(cur)) {
		seen.add(cur);
		const entry = map.get(cur)!;
		chain.push(entry);
		cur = entry.parentId ?? null;
	}
	return { chain: chain.reverse(), map };
}

function messageText(entry: Entry): string {
	if (entry.type === "custom_message") {
		const c = entry.content;
		return typeof c === "string"
			? c
			: Array.isArray(c)
				? c
						.filter((p: any) => p?.type === "text")
						.map((p: any) => String(p.text ?? ""))
						.join(" ")
				: "";
	}
	const content = entry.message?.content;
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return content
		.filter((p: any) => p?.type === "text")
		.map((p: any) => String(p.text ?? ""))
		.join(" ");
}

function oneLine(text: string, max = 80): string {
	const clean = text
		.replace(/```[\s\S]*?```/g, " ")
		.replace(/\[Image:[^\]]*\]/g, " ")
		.replace(/\s+/g, " ")
		.trim();
	return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

function resolveCut(chain: Entry[], cutAt: string): Entry {
	const needle = cutAt.trim();
	if (/^\d+$/.test(needle)) {
		const n = Number(needle);
		const users = chain.filter(
			(e) => e.type === "message" && (e as any).message?.role === "user",
		);
		const hit = users[n - 1];
		if (!hit) throw new Error(`当前分支只有 ${users.length} 条用户消息，第 ${n} 条不存在`);
		return hit;
	}
	const hit = chain.find((e) => e.id === needle);
	if (!hit) throw new Error(`entryId ${needle} 不在当前分支上`);
	return hit;
}

function writeSessionFile(
	dir: string,
	cwd: string,
	entries: Entry[],
): { file: string; id: string } {
	const id = randomUUID();
	const stamp = nowIso().replace(/[:.]/g, "-");
	const file = join(dir, `${stamp}_${id}.jsonl`);
	const header = { type: "session", version: 3, id, timestamp: nowIso(), cwd };
	const body = [JSON.stringify(header), ...entries.map((e) => JSON.stringify(e))].join("\n");
	writeFileSync(file, `${body}\n`, "utf8");
	return { file, id };
}

/** 时间轴：只列会进上下文的东西，工具结果只留一行摘要。 */
function timeline(chain: Entry[]): string {
	const lines: string[] = [];
	let seq = 0;
	for (const e of chain) {
		if (e.type !== "message" && e.type !== "custom_message" && e.type !== "compaction")
			continue;
		seq += 1;
		let role: string;
		let text: string;
		if (e.type === "compaction") {
			role = "compaction";
			text = String(e.summary ?? "");
		} else if (e.type === "custom_message") {
			role = `note(${e.customType ?? ""})`;
			text = messageText(e);
		} else {
			const kind = String(e.message?.role ?? "?");
			text = messageText(e);
			if (kind === "toolResult") {
				role = `tool:${e.message?.toolName ?? "?"}`;
			} else if (kind === "assistant" && !text) {
				// 只有思考没有正文的回合，用思考首行顶上，否则整条是空的。
				const parts = Array.isArray(e.message?.content) ? e.message.content : [];
				const think = parts.find((p: any) => p?.type === "thinking");
				role = "assistant(think)";
				text = String(think?.thinking ?? "");
			} else {
				role = kind;
			}
		}
		lines.push(`#${seq} ${e.id} ${role} | ${oneLine(text)}`);
	}
	return lines.slice(-MAX_TIMELINE).join("\n");
}

async function resolvePort(sessionId: string): Promise<string | null> {
	for (const port of CANDIDATE_PORTS) {
		try {
			const res = await fetch(`http://127.0.0.1:${port}/api/sessions/${sessionId}`, {
				signal: AbortSignal.timeout(3000),
			});
			if (res.ok) return port;
		} catch {
			// 端口不在或不是 pi-web，试下一个
		}
	}
	return null;
}

/**
 * 唤醒一个会话并立刻发第一条 prompt。
 * pi-web 的 /api/agent/:id 在会话没在跑时会自己把它拉起来，正好用来起跑。
 */
async function wakeSession(port: string, sessionId: string, message: string) {
	const res = await fetch(`http://127.0.0.1:${port}/api/agent/${sessionId}`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ type: "prompt", message }),
		signal: AbortSignal.timeout(20000),
	});
	const text = await res.text();
	if (!res.ok) throw new Error(`wake ${sessionId} → ${res.status} ${oneLine(text, 160)}`);
	return text;
}

export default function dSplit(pi: ExtensionAPI) {
	if (process.env.D_SPLIT_OFF === "1") return;

	pi.registerTool({
		name: "d_split",
		label: "拆分会话",
		description:
			"把一个会话按切点拆成两个独立会话文件（原会话不动）。" +
			"不带 cutAt 时返回当前分支的时间轴（序号 / entryId / 角色 / 摘要），用来挑候选切点；" +
			"带 cutAt 时真正执行拆分：切点及之前成为 A 会话，切点之后成为 B 会话。" +
			"用户说「聊偏了」「这段想单独开一个会话」「把这个话题拆出去」时用。",
		promptSnippet: "按切点把一个会话拆成两个独立会话，原会话不动",
		promptGuidelines: [
			"拆分前先不带 cutAt 调一次，把时间轴摊开、给出 2-3 个候选切点让用户确认，不要自己拍板。",
			"切点选在「新话题第一条用户消息」的前一条，A 段才不会夹带新话题。",
			"拆完必须告诉用户新会话的标题和 id，并说明原会话没有改动。",
		],
		parameters: Type.Object({
			cutAt: Type.Optional(
				Type.String({
					description:
						"切点：当前分支上的 entryId，或第 N 条用户消息（1 起）。省略则只返回时间轴。",
				}),
			),
			nameA: Type.Optional(
				Type.String({ description: "A 会话标题（切点及之前那段）" }),
			),
			nameB: Type.Optional(Type.String({ description: "B 会话标题（切点之后那段）" })),
			noteB: Type.Optional(
				Type.String({
					description: "插到 B 会话开头的说明（默认自动生成一条：本段由拆分而来、已完成别重做）",
				}),
			),
			wake: Type.Optional(
				Type.String({
					description:
						"拆完要不要自动起跑：'both'（默认，两边各发一句开场白）| 'b'（只给 B 发）| 'none'",
					}),
			),
			nameOriginal: Type.Optional(
				Type.String({
					description:
						"拆完给原会话改的新标题（原会话大段内容被抽走后旧标题往往名不符实）",
					}),
			),
			moveTo: Type.Optional(
				Type.String({
					description:
						"把 B 会话归到另一个工作目录（绝对路径）：文件写到该目录的 sessions 文件夹并改写 header cwd，pi-web 侧栏按它分组",
					}),
			),
		}),
		async execute(
			_toolCallId: string,
			params: any,
			_signal: AbortSignal | undefined,
			_onUpdate: unknown,
			ctx: ExtensionToolContext,
		) {
			const file = ctx.sessionManager.getSessionFile();
			const leaf = ctx.sessionManager.getLeafId();
			if (!file) {
				throw new Error("当前会话没有落盘文件（CLI 或未持久化会话不支持拆分）");
			}
			if (!leaf) throw new Error("当前会话没有 leaf，无法确定分支");

			const { header, entries } = loadSession(file);
			const { chain } = chainToLeaf(entries, leaf);
			if (chain.length === 0) throw new Error("当前分支是空的，没有可拆的内容");

			const cutAt = String(params.cutAt ?? "").trim();
			if (!cutAt) {
				return {
					content: [
						{
							type: "text",
							text:
								`当前分支时间轴（共 ${chain.length} 个条目，最后 ${MAX_TIMELINE} 条）：\n\n` +
								`${timeline(chain)}\n\n` +
								"挑 2-3 个候选切点报给用户，等确认后再带 cutAt 调一次真正拆分。" +
								"切点应落在「新话题第一条用户消息」的前一条。" +
								"拆出的大段要归到别的文件夹时带 moveTo（绝对路径），原会话要改标题时带 nameOriginal。",
						},
					],
					details: { mode: "timeline", entries: chain.length },
				};
			}

			const cut = resolveCut(chain, cutAt);
			const idx = chain.findIndex((e) => e.id === cut.id);
			if (idx < 0) throw new Error("切点不在当前分支上");

			const partA = chain.slice(0, idx + 1);
			const partB = chain.slice(idx + 1);
			if (partB.length === 0) {
				throw new Error("切点已经在分支末尾，后面没有内容可拆成 B 会话");
			}

			const dir = dirname(file);
			const cwd = String(header.cwd ?? ctx.cwd);
			const taken = new Set(entries.map((e) => String(e.id)));

			// moveTo：B 会话归到另一个 cwd。pi-web 按会话文件 header 里的 cwd 分组，
			// 所以目录和 header 都要跟着改，拆完不用再手动挪文件。
			let bDir = dir;
			let bCwd = cwd;
			const moveTo = String(params.moveTo ?? "").trim();
			if (moveTo) {
				if (!moveTo.startsWith("/")) throw new Error(`moveTo 要绝对路径，收到：${moveTo}`);
				const encoded = `--${moveTo.replace(/^\//, "").replaceAll("/", "-")}--`;
				bDir = join(AGENT_DIR, "sessions", encoded);
				mkdirSync(bDir, { recursive: true });
				bCwd = moveTo;
			}

			// A 段：原样复制，头部挂一条可见标记，末尾补会话名。
			const titleA = String(params.nameA ?? "").trim();
			const aNoteId = shortId(taken);
			taken.add(aNoteId);
			const aHead = partA[0];
			const aBody = partA.map((e) =>
				e === aHead ? { ...e, parentId: aNoteId } : { ...e },
			);
			const aNote: Entry = {
				type: "custom_message",
				customType: "d-split",
				content:
					`新的会话在这里 —— 这是「${titleA || "前半段"}」的前半段` +
					"（原会话切点之前，内容完整，已完成的事不必重做）。",
				display: true,
				id: aNoteId,
				parentId: null,
				timestamp: nowIso(),
			};
			const aEntries: Entry[] = [aNote, ...aBody];
			if (titleA) {
				aEntries.push({
					type: "session_info",
					id: shortId(taken),
					parentId: partA[partA.length - 1]?.id ?? aNoteId,
					timestamp: nowIso(),
					name: titleA,
				});
			}
			const A = writeSessionFile(dir, cwd, aEntries);

			// B 段：头部挂一条可见标记，说明「你是拆出来的后半段」。
			const titleB = String(params.nameB ?? "").trim();
			const noteId = shortId(taken);
			taken.add(noteId);
			const noteText =
				String(params.noteB ?? "").trim() ||
				`新的会话在这里 —— 这是「${titleB || "后半段"}」的后半段` +
					"（从另一个会话拆出，前半段属于另一个话题、已单独存放）。" +
					"这段历史里已经做完的事不要重做，接着最后一条继续。";
			const note: Entry = {
				type: "custom_message",
				customType: "d-split",
				content: noteText,
				display: true,
				id: noteId,
				parentId: null,
				timestamp: nowIso(),
			};
			const bHead = partB[0];
			const bBody = partB.map((e) =>
				e === bHead ? { ...e, parentId: noteId } : { ...e },
			);
			const bIds = new Set<string>([noteId, ...bBody.map((e) => String(e.id))]);
			// 压缩条目的回指可能落在 A 段，指过去就是悬空引用，改挂到注入节点上。
			for (const e of bBody) {
				if (
					e.type === "compaction" &&
					typeof e.firstKeptEntryId === "string" &&
					!bIds.has(e.firstKeptEntryId)
				) {
					e.firstKeptEntryId = noteId;
				}
			}
			const bEntries = [note, ...bBody];
			if (titleB) {
				bEntries.push({
					type: "session_info",
					id: shortId(new Set(taken)),
					parentId: bBody[bBody.length - 1]?.id ?? noteId,
					timestamp: nowIso(),
					name: titleB,
				});
			}
			const B = writeSessionFile(bDir, bCwd, bEntries);

			// 原会话改名：大段内容被抽走后旧标题往往名不符实，补一条 session_info。
			const nameOriginal = String(params.nameOriginal ?? "").trim();
			let renamed = false;
			const failures: string[] = [];
			if (nameOriginal) {
				try {
					appendFileSync(
						file,
						`${JSON.stringify({
							type: "session_info",
							id: shortId(taken),
							parentId: leaf,
							timestamp: nowIso(),
							name: nameOriginal,
						})}\n`,
					);
					renamed = true;
				} catch (error) {
					failures.push(
						`原会话改名失败：${error instanceof Error ? error.message : String(error)}`,
					);
				}
			}

			const wakeMode = String(params.wake ?? "both").toLowerCase();
			const started: string[] = [];
			if (wakeMode !== "none") {
				const port = await resolvePort(A.id);
				if (!port) {
					failures.push("没找到 pi-web 端口，跳过自动起跑（两个会话都已建好，手动打开即可）");
				} else {
					const targets: Array<[string, string, string]> = [];
					if (wakeMode === "both") {
						targets.push([
							A.id,
							`A ${titleA || "前半段"}`,
							`这是新的「${titleA || "前半段"}」会话，从原会话拆出的前半段，内容完整，不需要重做已完成的工作。`,
						]);
					}
					targets.push([
						B.id,
						`B ${titleB || "后半段"}`,
						noteText,
					]);
					for (const [sid, label, msg] of targets) {
						try {
							await wakeSession(port, sid, msg);
							started.push(label);
						} catch (error) {
							failures.push(
								`${label} 起跑失败：${error instanceof Error ? error.message : String(error)}`,
							);
						}
					}
				}
			}

			log(
				`d-split ${file} cut=${cut.id} A=${A.id} B=${B.id} wake=${wakeMode} started=${started.length}`,
			);

			const share = Math.round((partA.length / chain.length) * 100);
			const lines = [
				"拆分完成，原会话没有改动。",
				"",
				`A 会话（切点及之前）：${titleA || "未命名"}`,
				`  id     ${A.id}`,
				`  file   ${A.file}`,
				"",
				`B 会话（切点之后）：${titleB || "未命名"}${moveTo ? `（已归到 ${moveTo}）` : ""}`,
				`  id     ${B.id}`,
				`  file   ${B.file}`,
				"",
				`A 段 ${partA.length} 个条目（占原会话 ${share}%），B 段 ${partB.length} 个条目。`,
			];
			if (renamed) lines.push(`原会话已改名为「${nameOriginal}」。`);
			if (share < 25 && partB.length > partA.length) {
				lines.push(
					`注意：切点很靠后，原会话只剩 ${share}% 内容。` +
						"如果留下的小段才是主线，考虑反向拆分：把大段拆出去、小段留原会话。",
				);
			}
			if (started.length) lines.push(`已自动起跑：${started.join("、")}`);
			if (failures.length) lines.push(`未完成：${failures.join("；")}`);
			lines.push("pi-web 侧栏可能要刷新一次才看得到新会话。");

			return {
				content: [{ type: "text", text: lines.join("\n") }],
				details: {
					mode: "split",
					cutEntryId: cut.id,
					a: { id: A.id, file: A.file, entries: partA.length, title: titleA },
					b: { id: B.id, file: B.file, entries: partB.length, title: titleB, movedTo: moveTo || undefined },
					renamedOriginal: renamed ? nameOriginal : undefined,
					started,
					failures,
				},
			};
		},
	});

	pi.registerCommand("d-split", {
		description: "列出当前会话分支的时间轴，用来挑拆分切点",
		handler: async (_args, ctx) => {
			const file = ctx.sessionManager.getSessionFile();
			const leaf = ctx.sessionManager.getLeafId();
			if (!file || !leaf) return;
			const { entries } = loadSession(file);
			const { chain } = chainToLeaf(entries, leaf);
			const report = timeline(chain);
			try {
				ctx.ui.notify(report || "当前分支没有可拆内容", "info");
			} catch {
				log(`timeline notify failed for ${file}`);
			}
		},
	});
}
