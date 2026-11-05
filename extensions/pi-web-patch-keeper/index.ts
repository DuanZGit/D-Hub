/**
 * pi-web-patch-keeper —— pi-web 被升级冲掉的本地补丁，自动重放。
 *
 * 背景：pi-web 的「完成通知显示项目名 + 会话名」等改动只能改在编译产物里
 * （.next/server/chunks、.next/static、public/sw.js），npm 升级会整包覆盖。
 * 所有改动登记在 ~/.pi/agent/.cn-patches/patches.json，由 apply.py 重放。
 *
 * 本扩展只做一件事：扩展加载时跑一次 apply.py。它幂等——已应用的跳过，
 * 只有被升级冲掉的才会被写回。有重放就在下个 agent_start 提醒你重启 pi-web。
 *
 * 环境变量：
 *   PI_WEB_PATCH_OFF=1        关闭
 *   PI_WEB_PATCH_INTERVAL_H   两次检查最小间隔小时数（默认 6）
 *
 * 日志：~/.pi/agent/.cn-patches/keeper.log
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const PATCH_DIR = join(homedir(), ".pi", "agent", ".cn-patches");
const APPLY = join(PATCH_DIR, "apply.py");
const STATE_FILE = join(PATCH_DIR, "keeper-state.json");
const LOG_FILE = join(PATCH_DIR, "keeper.log");

const INTERVAL_MS = Math.max(0, Number(process.env.PI_WEB_PATCH_INTERVAL_H ?? 6)) * 3600_000;

let pendingNote: string | null = null;

function log(line: string) {
	try {
		appendFileSync(LOG_FILE, `${new Date().toISOString()} ${line}\n`);
	} catch {
		// 日志写不进去不影响主流程
	}
}

function runApply(): Promise<string> {
	return new Promise((resolve, reject) => {
		execFile("python3", [APPLY], { timeout: 60_000 }, (err, stdout, stderr) => {
			if (err) reject(new Error(`${err.message} ${stderr}`.trim()));
			else resolve(String(stdout));
		});
	});
}

function throttleElapsed(): boolean {
	try {
		const s = JSON.parse(readFileSync(STATE_FILE, "utf8"));
		return Date.now() - Number(s.at ?? 0) >= INTERVAL_MS;
	} catch {
		return true;
	}
}

async function checkAndReplay() {
	if (process.env.PI_WEB_PATCH_OFF === "1") return;
	if (!existsSync(APPLY)) return log("skip: apply.py 不存在");
	if (!throttleElapsed()) return log("skip: 节流中");

	try {
		writeFileSync(STATE_FILE, `${JSON.stringify({ at: Date.now() })}\n`, "utf8");
	} catch {
		// 状态写不了就退化成每次都检查，仍然幂等
	}

	const output = await runApply();
	const applied = Number(/(\d+) 处替换已处理/.exec(output)?.[1] ?? 0);
	const broken = Number(/(\d+) 处失效/.exec(output)?.[1] ?? 0);
	log(`applied=${applied} broken=${broken} :: ${output.trim().replace(/\n/g, " | ")}`);

	if (applied > 0) {
		pendingNote = `pi-web 补丁被升级冲掉 ${applied} 处，已自动重放。重启 pi-web 才生效：d_restart`;
	}
}

export default function (pi: ExtensionAPI) {
	void checkAndReplay().catch((err: Error) => log(`error ${err.message}`));

	pi.on("agent_start", (_event, ctx: ExtensionContext) => {
		if (!pendingNote) return;
		const message = pendingNote;
		pendingNote = null;
		try {
			ctx.ui.notify(message, "warning");
		} catch {
			// 没有 UI 就只留日志
		}
	});
}
