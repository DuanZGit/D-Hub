/**
 * skill-trigger — 技能触发兜底 + 硬门禁（pi 扩展）
 *
 * 问题：pi 的技能是「渐进披露」——系统提示里只有 name + description，
 * 正文要模型自己决定去 read。官方文档原话："models don't always do this;
 * use prompting or /skill:name to force it"。
 *
 * 2026-09-25 实测漏过一次：用户说「你去全网看一下」，助手直接调了内置
 * web_search / fetch_content，没走 d-reach（搜索与爬取统一路由）。
 * 后果：额度记账可能失真、免费通道一个没用、只有一轮没有追证轮。
 *
 * 两层防线：
 *   层1 软注入 before_agent_start —— 触发词命中就往本轮注入一条不显示的提醒
 *   层2 硬门禁 tool_call         —— 拦 web_search / fetch_content 两个内置工具，
 *                                  本会话没读过对应 SKILL.md 就不放行
 *
 * 层2 的三条边界（刻意做窄，别随手放宽）：
 *   1) **只拦这两个内置工具，不碰 bash**。日常 curl（sev.duanz.xin /
 *      api.siliconflow.cn）全走 bash，拦它才需要域名白名单那种易错设计；
 *      而这两个内置工具正是上次绕开 d-reach 的路径。
 *   2) **本地资源不拦**：输入里没有 http(s):// 就放行（file:// 、本地图片/视频）。
 *   3) **逃生舱**：任一输入字段带 `#d-reach:allow` 即放行（需先向用户说明理由）；
 *      或设环境变量 PI_SKILL_TRIGGER_GATE=off 整层关掉。
 *
 * 可扩展：往 RULES 里加一条即可覆盖新技能（软注入与硬门禁共用同一张表）。
 *
 * 修改本文件后需新开会话才生效。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

interface Rule {
	/** 技能名，用于排障 */
	name: string;
	/** SKILL.md 绝对路径 */
	path: string;
	/** 软注入的触发词；中英混合，忽略大小写 */
	patterns: RegExp;
	/** 软注入内容。用条件式措辞：误命中也无害（本地操作忽略本条即可） */
	hint: string;
}

/** 硬门禁盯死的内置工具：绕过 d-reach 路由表的那两个 */
const GATED_TOOLS = ["web_search", "fetch_content"] as const;

/** 逃生舱标记：出现在任一输入字段里就放行 */
const ALLOW_MARKER = /#\s*d-reach\s*:\s*allow/i;

/** 层2 总开关：PI_SKILL_TRIGGER_GATE=off/1/true/no 关闭 */
const GATE_OFF = /^(1|true|off|no|disabled)$/i.test(
	process.env.PI_SKILL_TRIGGER_GATE ?? "",
);

/** 每个技能每个会话最多软注入几次（防历史膨胀） */
const MAX_REMINDERS_PER_SESSION = 5;

const RULES: Rule[] = [
	{
		name: "d-reach",
		path: "/home/duanz/.agents/skills/d-reach/SKILL.md",
		patterns:
			/搜|搜索|检索|查一下|查查|查找|帮我搜|找个|找一下|看看有没有|有没有类似|类似项目|爬|抓取|抓一下|读一下|这个链接|打开看看|调研|全网|上网|search|look up|scrape/i,
		hint:
			"本次请求可能涉及「上网找信息」（搜索 / 爬取 / 读外部链接 / 调研）。" +
			"按纪律先 read /home/duanz/.agents/skills/d-reach/SKILL.md，" +
			"再用它的路由表选通道（免费免 Key 优先：cn.bing / gh CLI / OpenAlex / Crossref / HN Algolia），" +
			"限额通道调用前先跑 scripts/quota.py use <svc>，" +
			"不要直接调内置 web_search / fetch_content（那会绕开额度记账）。" +
			"若本次其实是查本地文件或自有服务（127.0.0.1 / *.duanz.xin），忽略本条。",
	},
];

/** 每个技能已软注入次数；session_start 时清空 */
const reminderCount = new Map<string, number>();

/** 本会话已经读过哪些 SKILL.md（由 tool_execution_start 观察得到） */
const skillRead = new Set<string>();

/** 从工具输入里取全部字符串值，用于路径/标记匹配 */
function inputStrings(input: unknown): string {
	if (input == null) return "";
	if (typeof input === "string") return input;
	try {
		return JSON.stringify(input);
	} catch {
		return "";
	}
}

export default function (pi: ExtensionAPI) {
	pi.on("session_start", () => {
		reminderCount.clear();
		skillRead.clear();
	});

	// 观察所有工具调用：一旦读到某个 SKILL.md，就认为该技能已加载
	pi.on("tool_execution_start", async (event) => {
		const raw = inputStrings(event?.input);
		if (!raw) return;
		for (const rule of RULES) {
			if (raw.includes(rule.path)) skillRead.add(rule.name);
		}
	});

	// ── 层 2：硬门禁 ───────────────────────────────────────────
	pi.on("tool_call", async (event) => {
		if (GATE_OFF) return undefined;

		const toolName = event?.toolName;
		if (typeof toolName !== "string") return undefined;
		if (!(GATED_TOOLS as readonly string[]).includes(toolName)) return undefined;

		const raw = inputStrings(event.input);

		// 本地资源豁免只对 fetch_content 成立：它的 url 可能指向 file:// 或本地
		// 图片/视频。web_search 的 query 本来就不含 URL，若也套这条规则，门禁
		// 会对自己最该管的工具失效（实测踩过：query="siliconflow jev" 被放行）。
		const localOnly =
			toolName === "fetch_content" && !/https?:\/\//i.test(raw);
		if (localOnly) return undefined;

		// 逃生舱：调用方显式声明要走直连
		if (ALLOW_MARKER.test(raw)) return undefined;

		// 本会话已读过任一受管技能 → 放行
		for (const rule of RULES) {
			if (skillRead.has(rule.name)) return undefined;
		}

		const rule = RULES[0];
		const reason =
			`【skill-trigger 门禁】本会话还没有读过 ${rule.name} 技能，` +
			`按纪律先 read ${rule.path}，用它的路由表选通道` +
			`（免费免 Key 优先：cn.bing / gh CLI / OpenAlex / Crossref / HN Algolia；` +
			`限额通道调用前先跑 scripts/quota.py use <svc>）。` +
			`内置 ${toolName} 会绕开额度记账与免费优先原则，所以先被拦下。` +
			`若你确认要直连（例如用户给了明确 URL、或只要一条事实且两个免费源都拿不到），` +
			`在任一输入字段里带上 \`#d-reach:allow\` 再调一次，并先向用户说明理由。`;

		return { block: true, reason };
	});

	// ── 层 1：软注入 ───────────────────────────────────────────
	pi.on("before_agent_start", async (event) => {
		const prompt = typeof event?.prompt === "string" ? event.prompt : "";
		if (!prompt) return;

		for (const rule of RULES) {
			if (!rule.patterns.test(prompt)) continue;

			// 该技能已经在系统提示里加载过（如项目技能），不必再提醒
			let alreadyLoaded = false;
			try {
				const skills = event.systemPromptOptions?.skills;
				if (Array.isArray(skills)) {
					alreadyLoaded = skills.some((s) =>
						JSON.stringify(s ?? "").includes(rule.name),
					);
				}
			} catch {
				/* 形状不符就当没加载，继续提醒 */
			}
			if (alreadyLoaded) continue;

			// 会话内上限：同一个会话里同一个技能最多提醒 N 次
			const used = reminderCount.get(rule.name) ?? 0;
			if (used >= MAX_REMINDERS_PER_SESSION) continue;
			reminderCount.set(rule.name, used + 1);

			return {
				message: {
					customType: "skill-trigger",
					content: `[skill-trigger] ${rule.hint}`,
					// 不显示在对话里：这是给模型的提示，不是给用户看的通知
					display: false,
				},
			};
		}

		return;
	});
}
