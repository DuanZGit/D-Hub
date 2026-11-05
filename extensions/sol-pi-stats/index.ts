/**
 * SoL-Pi 状态栏（常驻）+ /sol 明细
 *
 * NVIDIA 的 sol-pi 插件只在自己省下东西时闪 4 秒（src/sol-pi/tui.ts: STATUS_DURATION_MS=4000），
 * 之后把状态清掉。这里把 observation-pack 的 ledger 汇总成一条常驻状态：
 *
 *   ⚡SoL 省 36M tok · 22 包          （状态栏）
 *   /sol                              （明细：包数、累计避免量、金额区间、Top 包）
 *
 * 数据源：<sessionDir>/sol-pi/<sessionId>/observation-pack/ledger.jsonl
 *   event=placeholder 的行里 removedTokens = 该次请求少发的 token（同一个包每次请求各记一条）
 *
 * 约束（与 antigravity-quota 一致）：事件驱动、不设定时器；只在同步阶段读缓存，
 * 不 await，避免会话重载后 ctx stale；异常静默。
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const KEY = "sol-pi-stats";

type Pack = { tokens: number; sends: number };
type Stats = { avoided: number; packs: Map<string, Pack>; inputPrice: number; cacheReadPrice: number };

/** 同一份 ledger 只在 (size, mtime) 变化时重新解析。 */
const cache = new Map<string, { stamp: string; value: Stats | null }>();

export function shortTokens(value: number): string {
	const n = Math.max(0, Math.round(Number(value) || 0));
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
	if (n >= 10_000) return `${Math.round(n / 1000)}k`;
	if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
	return String(n);
}

export function collect(ctx: any): Stats | null {
	try {
		const dir = ctx?.sessionManager?.getSessionDir?.();
		const sid = ctx?.sessionManager?.getSessionId?.();
		if (!dir || !sid) return null;
		const ledger = join(dir, "sol-pi", sid, "observation-pack", "ledger.jsonl");

		const stat = statSync(ledger);
		const stamp = `${stat.size}:${stat.mtimeMs}`;
		const hit = cache.get(ledger);
		const inputPrice = Number(ctx?.model?.cost?.input) || 0;
		if (hit?.stamp === stamp) return hit.value;

		let avoided = 0;
		const packs = new Map<string, Pack>();
		for (const line of readFileSync(ledger, "utf8").split("\n")) {
			if (!line) continue;
			let entry: any;
			try {
				entry = JSON.parse(line);
			} catch {
				continue;
			}
			if (entry?.event !== "placeholder") continue;
			const removed = Math.max(0, Math.round(Number(entry.removedTokens) || 0));
			avoided += removed;
			if (typeof entry.id === "string") {
				const pack = packs.get(entry.id) ?? { tokens: 0, sends: 0 };
				pack.tokens += removed;
				pack.sends += 1;
				packs.set(entry.id, pack);
			}
		}
		const value: Stats | null = avoided > 0
			? { avoided, packs, inputPrice, cacheReadPrice: Number(ctx?.model?.cost?.cacheRead) || 0 }
			: null;
		cache.set(ledger, { stamp, value });
		return value;
	} catch {
		return null;
	}
}

export function statusText(stats: Stats | null): string {
	if (!stats) return "";
	// 2026-09-30：「· 」只做插件间分隔（OV / sol / cache 统一格式）；
	// 包数收括号，避免和分隔点撞车（原来 tok · N 包是插件内部格式）。
	return `· ⚡SoL 省 ${shortTokens(stats.avoided)} tok（${stats.packs.size} 包）`;
}

export function detailText(stats: Stats | null): string {
	if (!stats) return "SoL-Pi: 本会话还没有省量记录（observation-pack 未触发）";
	const money = (price: number) => `$${((stats.avoided / 1_000_000) * price).toFixed(2)}`;
	const lines = [
		"【SoL-Pi 本会话省量（observation-pack）】",
		`  观察包 ${stats.packs.size} 个 · 累计少发 ${stats.avoided.toLocaleString("en-US")} tokens`,
	];
	if (stats.inputPrice > 0) lines.push(`  换算金额 ≈${money(stats.inputPrice)}（按输入价 $${stats.inputPrice}/M）`);
	if (stats.cacheReadPrice > 0) lines.push(`               ≈${money(stats.cacheReadPrice)}（按缓存价 $${stats.cacheReadPrice}/M）`);
	lines.push("  说明：每条 placeholder 事件记一次，数字是「多次请求累计少发」。");
	const top = [...stats.packs.entries()].sort((a, b) => b[1].tokens - a[1].tokens).slice(0, 5);
	if (top.length) {
		lines.push("  最省的 5 个包：");
		for (const [id, p] of top) lines.push(`    ${id}  ${shortTokens(p.tokens)} tok / ${p.sends} 次`);
	}
	return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
	const render = (ctx: any) => {
		try {
			const text = statusText(collect(ctx));
			if (text) ctx.ui.setStatus(KEY, text);
		} catch {
			/* ctx stale 或读不到 ledger：下个事件再试 */
		}
	};

	pi.on("session_start", (_e: any, ctx: any) => render(ctx));
	pi.on("turn_start", (_e: any, ctx: any) => render(ctx));
	pi.on("turn_end", (_e: any, ctx: any) => render(ctx));

	pi.registerCommand("sol", {
		description: "查看 SoL-Pi 本会话省下的 token（observation-pack 汇总）",
		handler: (_a: any, ctx: any) => {
			try {
				ctx.ui.notify(detailText(collect(ctx)), "info");
			} catch {
				/* ctx 失效则静默 */
			}
		},
	});
}
