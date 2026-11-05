/**
 * skill-search — 让模型按需检索本机全部技能（pi 扩展）
 *
 * 问题：pi 的技能目录常驻系统提示。本机 82 个技能，全部摊开约 21164 字符
 * （≈6500 tokens），每一轮都在烧，不管这次用不用得上。
 *
 * 现成的解法有两个，都不合适：
 *   1) 把低频技能设成 disable-model-invocation（省 token）——但那样模型
 *      **完全看不见**它们，除非用户记得打 /skill:名字。
 *   2) 把技能索引全量注入每轮上下文——省下的 token 又原样花回去。
 *
 * 本扩展补的是这个缝：技能目录不必常驻，只要「查询入口」常驻。
 * 一个工具 schema 约 120 tokens/轮，模型需要时自己来查。
 * 这跟 d-reach 把 9 个搜索通道收成 1 个入口是同一个模式。
 *
 * 三条设计约束（都来自实测结论，别随手放宽）：
 *   1) **只给路径，不返回正文**。arxiv 2603.22455 (SkillRouter) 在 80K 候选上
 *      实测：只暴露 name+description 会让路由准确率掉 37-44 个百分点，
 *      必须 body-aware。本机的做法是让模型拿到路径后用 read 读正文再定，
 *      所以 path 是必返回字段，不能省。
 *   2) **不做自动注入**。before_agent_start 里塞提示等于把省下的 token 花回去；
 *      工具躺在工具列表里，模型知道有它可用就够了。
 *   3) **不碰 frontmatter**。扩展只在 extensions 目录，uipro update /
 *      npx impeccable update 不会覆盖它——这是插件相对改 SKILL.md 的关键优势。
 *
 * 与 ask-me 技能的关系：ask-me 是给人的入口（显式 /skill:ask-me），
 * 本工具是给模型的入口。装了扩展后，ask-me 的扫描脚本可以退居备用
 * （Minis / DSH 等没有本扩展的环境仍用它）。
 *
 * 修改本文件后需重启 pi 才生效。
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** 描述截断长度：够模型判断，又不至于把上下文撑大 */
const DESC_MAX = 200;
/** 默认返回条数 */
const DEFAULT_LIMIT = 8;
/** 只读文件头这么多字节取 frontmatter，避免为解析元数据把全文读进来 */
const HEAD_BYTES = 8192;

interface Skill {
	name: string;
	/** auto = 模型可见并可能自动触发；explicit = 已从模型上下文中隐藏 */
	mode: "auto" | "explicit";
	description: string;
	path: string;
	/** 来源标签，用于输出时分组与排障 */
	source: string;
}

/** 扫描根：(来源标签, 路径)。与 ask-me/scripts/scan_skills.py 保持同一套根目录。 */
function scanRoots(cwd: string): Array<[string, string]> {
	const agentDir = process.env.PI_AGENT_DIR || join(homedir(), ".pi", "agent");
	const roots: Array<[string, string]> = [
		["user", join(agentDir, "skills")],
		["user", join(homedir(), ".agents", "skills")],
		["project", join(cwd, ".pi", "skills")],
		["project", join(cwd, ".agents", "skills")],
	];
	// pi 包自带的技能
	const npm = join(agentDir, "npm", "node_modules");
	if (existsSync(npm)) {
		for (const pkg of safeReaddir(npm)) {
			roots.push(["package", join(npm, pkg, "skills")]);
			const plugins = join(npm, pkg, "plugins");
			if (existsSync(plugins)) {
				for (const plugin of safeReaddir(plugins)) {
					roots.push(["package", join(plugins, plugin)]);
				}
			}
		}
	}
	return roots;
}

function safeReaddir(dir: string): string[] {
	try {
		return readdirSync(dir);
	} catch {
		return [];
	}
}

/**
 * 极简 frontmatter 解析：只取 name / description / disable-model-invocation。
 * 刻意不引 YAML 库——技能头部的结构是可预测的，而扩展应当零依赖好维护。
 * 能处理 `key: value`、`key:` 后换行缩进的块标量（`>` / `>-` / `|`）两种形态。
 */
function parseFrontmatter(head: string): Record<string, string> {
	const out: Record<string, string> = {};
	if (!head.startsWith("---")) return out;
	const end = head.indexOf("\n---", 3);
	if (end === -1) return out;
	const lines = head.slice(3, end).split("\n");

	let currentKey: string | null = null;
	let buffer: string[] = [];

	const flush = () => {
		if (currentKey) {
			out[currentKey] = buffer.join(" ").trim().replace(/\s+/g, " ");
		}
		currentKey = null;
		buffer = [];
	};

	for (const line of lines) {
		const m = /^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/.exec(line);
		if (m) {
			flush();
			const [, key, value] = m;
			if (value === "" || /^[>|][-+]?$/.test(value)) {
				// 块标量：值在后续缩进行里
				currentKey = key;
			} else {
				out[key] = value.trim().replace(/^["']|["']$/g, "");
			}
			continue;
		}
		// 缩进行属于上一个 key 的块标量
		if (currentKey && /^\s+\S/.test(line)) {
			buffer.push(line.trim());
		}
	}
	flush();
	return out;
}

function collectSkills(cwd: string): Skill[] {
	const skills: Skill[] = [];
	const seen = new Set<string>();

	for (const [source, root] of scanRoots(cwd)) {
		if (!existsSync(root)) continue;

		// root 自身也可能是技能目录（pi 包把 plugins/<name>/ 直接当技能）
		const candidates: string[] = [];
		if (existsSync(join(root, "SKILL.md"))) candidates.push(join(root, "SKILL.md"));
		for (const entry of safeReaddir(root)) {
			const p = join(root, entry, "SKILL.md");
			if (existsSync(p)) candidates.push(p);
		}

		for (const file of candidates) {
			const real = (() => {
				try {
					return statSync(file).ino + ":" + file;
				} catch {
					return file;
				}
			})();
			if (seen.has(real)) continue;
			seen.add(real);

			let head: string;
			try {
				head = readFileSync(file, "utf8").slice(0, HEAD_BYTES);
			} catch {
				continue;
			}
			const meta = parseFrontmatter(head);
			if (!meta.name) continue;

			skills.push({
				name: meta.name,
				mode: /^true$/i.test(meta["disable-model-invocation"] ?? "") ? "explicit" : "auto",
				description: (meta.description ?? "").replace(/\s+/g, " ").trim(),
				path: file,
				source,
			});
		}
	}
	return skills;
}

/**
 * 把查询切成检索词：英文按 3+ 字符单词，中文按 2-gram。
 * 中文没有空格，整串匹配太脆——「设计一个落地页」不该只匹配字面包含的。
 */
function queryTerms(query: string): string[] {
	const terms = new Set<string>();
	for (const w of query.toLowerCase().match(/[a-z0-9_-]{3,}/g) ?? []) terms.add(w);
	for (const run of query.replace(/[^\u4e00-\u9fff]+/g, " ").split(/\s+/)) {
		for (let i = 0; i + 1 < run.length; i++) terms.add(run.slice(i, i + 2));
	}
	return [...terms];
}

/** 名称命中权重远高于描述：技能名是人挑过的，信号更干净。 */
const W_NAME = 8;
const W_DESC = 1.5;

/**
 * 词在技能库里的文档频率。
 *
 * 必须有这个才能压住「长描述偏置」：d-reach 的描述 849 字符，几乎含全了
 * 各类技术词，不加权它会把每次查询都捞进来。df 越大 = 越不值钱。
 */
function documentFrequencies(skills: Skill[], terms: string[]): Map<string, number> {
	const df = new Map<string, number>();
	for (const t of terms) {
		let n = 0;
		for (const s of skills) {
			if (s.name.toLowerCase().includes(t) || s.description.toLowerCase().includes(t)) n++;
		}
		df.set(t, n);
	}
	return df;
}

function inverseDocumentFrequency(term: string, df: Map<string, number>, total: number): number {
	return Math.log(1 + total / (1 + (df.get(term) ?? 0)));
}

/**
 * BM25 的文档长度归一化。
 *
 * 光有 IDF 不够：长描述天然覆盖更多词，反而靠“命中数量”堆分。实测发现
 * d-reach（描述 849 字符）会篱占每一次查询结果，把真正相关的短描述技能挤掉。
 * 按长度打折后，短描述的技能不再吃亏。
 */
function lengthPenalty(descriptionLength: number, avgLength: number): number {
	const K1 = 1.2;
	const B = 0.75;
	const dl = Math.max(1, descriptionLength);
	const avg = Math.max(1, avgLength);
	return (K1 + 1) / (K1 * (1 - B + (B * dl) / avg) + 1);
}

/** 描述命中只取 IDF 最高的这么多个：再多就是堆数量，不是相关性 */
const TOP_DESC_HITS = 4;

function scoreSkill(
	skill: Skill,
	terms: string[],
	raw: string,
	df: Map<string, number>,
	total: number,
	avgLength: number,
): number {
	const name = skill.name.toLowerCase();
	const desc = skill.description.toLowerCase();
	let score = 0;

	const lowered = raw.toLowerCase();
	if (lowered && name === lowered) score += 40;
	else if (lowered && name.includes(lowered)) score += 15;

	// 名称命中不吃长度惩罚：技能名是人挑过的，长度不意味着稀释
	const descHits: number[] = [];
	for (const t of terms) {
		const w = inverseDocumentFrequency(t, df, total);
		if (name.includes(t)) score += W_NAME * w;
		else if (desc.includes(t)) descHits.push(w);
	}

	descHits.sort((a, b) => b - a);
	const descScore = descHits.slice(0, TOP_DESC_HITS).reduce((a, b) => a + b, 0);
	score += W_DESC * lengthPenalty(skill.description.length, avgLength) * descScore;

	return score;
}

export default function (pi: ExtensionAPI) {
	pi.registerTool({
		name: "skill_search",
		label: "搜索技能",
		description:
			"检索本机已安装的全部 agent 技能（包括已被隐藏、未出现在你上下文中的那些），" +
			"按任务返回最匹配的几个及各自 SKILL.md 的绝对路径。当你拿不准该用哪个技能、" +
			"或任务看起来需要一套专门流程而不只是内置工具时调用。不带 query 调用可列出全部技能名。" +
			"拿到路径后用 read 读正文再动手——只凭描述下结论会选错。",
		promptSnippet: "按任务检索本机技能库，返回匹配技能及其 SKILL.md 路径",
		promptGuidelines: [
			"不确定该用哪个技能时先调 skill_search，不要凭技能名猜。",
			"skill_search 返回的路径要用 read 读正文确认后再执行；描述只够初筛。",
			"想看本机装了哪些技能时，调 skill_search 且不带 query，会列出全部技能名。",
		],
		parameters: Type.Object({
			query: Type.Optional(
				Type.String({
					description:
						"任务描述或关键词，用自然语言写清要做什么；省略则列出全部技能名",
				}),
			),
			limit: Type.Optional(
				Type.Number({ description: `返回条数，默认 ${DEFAULT_LIMIT}` }),
			),
		}),
		async execute(_toolCallId, params) {
			const query = String(params.query ?? "").trim();
			const limit = Math.max(1, Math.min(30, Number(params.limit) || DEFAULT_LIMIT));
			const cwd = process.cwd();

			const all = collectSkills(cwd);
			if (all.length === 0) {
				return {
					content: [
						{ type: "text", text: "没有扫到任何技能目录，请检查 ~/.agents/skills 是否存在。" },
					],
					details: { scanned: 0, matched: 0 },
				};
			}

			const terms = queryTerms(query);

			// 不带 query：列出全部技能名，让模型自己认领。这是「检索落空」的兜底
			// ——词法匹配对「写代码时少写点」→ ponytail 这类语义跳跃本来就无能为力，
			// 与其给错候选，不如把名册摊开。
			if (!query) {
				const bySource = new Map<string, Skill[]>();
				for (const s of all) {
					const list = bySource.get(s.source) ?? [];
					list.push(s);
					bySource.set(s.source, list);
				}
				const label: Record<string, string> = {
					user: "用户级",
					project: "项目级",
					package: "pi 包内",
				};
				const lines = [`本机共 ${all.length} 个技能（* = 已隐藏，不在你上下文里）：`, ""];
				for (const [source, list] of bySource) {
					lines.push(`【${label[source] ?? source}】${list.length} 个`);
					for (const s of list) {
						lines.push(`  ${s.mode === "explicit" ? "*" : " "} ${s.name}`);
					}
					lines.push("");
				}
				lines.push("需要某个技能的正文时，带 query 再查一次拿路径，或直接 read 它的 SKILL.md。");
				return {
					content: [{ type: "text", text: lines.join("\n") }],
					details: { scanned: all.length, matched: all.length, listed: true },
				};
			}

			const df = documentFrequencies(all, terms);
			const avgLength =
				all.reduce((sum, s) => sum + s.description.length, 0) / Math.max(1, all.length);
			const ranked = all
				.map((s) => ({
					skill: s,
					score: scoreSkill(s, terms, query, df, all.length, avgLength),
				}))
				.filter((r) => r.score > 0)
				.sort((a, b) => b.score - a.score)
				.slice(0, limit);

			// 一条都没匹配上时，退回「全量名单」的极简形态，让模型自己挑，
			// 这比返回空结果再让模型瞎猜要好。
			const picked = ranked.length > 0 ? ranked.map((r) => r.skill) : all;

			const lines: string[] = [];
			if (ranked.length > 0) {
				lines.push(`匹配 ${picked.length} 个（本机共 ${all.length} 个技能）：`, "");
			} else {
				lines.push(
					`没有技能命中「${query}」。与其硬凑，先把名册摊开，`,
					`下面是本机全部 ${all.length} 个技能；挑中哪个再 read 它的 SKILL.md：`,
					"",
				);
			}

			for (const s of picked) {
				const tag = s.mode === "explicit" ? "已隐藏" : "可见";
				if (ranked.length === 0) {
					lines.push(`- ${s.name} [${tag}]  ${s.path}`);
					continue;
				}
				const desc =
					s.description.length > DESC_MAX
						? `${s.description.slice(0, DESC_MAX)}…`
						: s.description;
				lines.push(`- ${s.name} [${tag}]${desc ? `  ${desc}` : ""}`);
				lines.push(`  路径: ${s.path}`);
			}

			if (ranked.length > 0) {
				lines.push("", "选之前请先 read 正文核对——描述只够初筛，选错会白跑一轮。");
				// 只有真的捞回了隐藏技能才提，否则是噪音（实测踩过：没隐藏技能也照打）
				if (picked.some((s) => s.mode === "explicit")) {
					lines.push("标 [已隐藏] 的技能不在你的上下文里，只有读它的 SKILL.md 才能用上。");
				}
				lines.push("没找到想要的？不带 query 再调一次可看全量技能名。");
			}

			return {
				content: [{ type: "text", text: lines.join("\n") }],
				details: {
					scanned: all.length,
					matched: ranked.length,
					top: picked.slice(0, limit).map((s) => s.name),
				},
			};
		},
	});
}
