/**
 * webshare —— 把当前会话变成公网临时链接（自建 share.duanz.xin，不走 GitHub）。
 *
 *   /webshare                  分享当前会话（转换成可读 HTML）
 *   /webshare <文件路径>       原样分享任意文件（图片/PDF/压缩包，不限大小）
 *   /webshare --list           列出所有还在的分享
 *   /webshare --rm <token>     删除某个分享（token 或完整链接都行）
 *
 * 内置 /share 走 gist/Radius，本机没有 gh CLI，所以用独立命令名。
 * 实际转换/存储由 ~/.pi/agent/bin/share 完成，这里只做命令入口与结果回显。
 */

import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const SCRIPT = join(homedir(), ".pi", "agent", "bin", "share");

export default function webshare(pi: ExtensionAPI) {
	const handler = async (args: string, ctx: import("@earendil-works/pi-coding-agent").ExtensionCommandContext) => {
		const parts = args.trim().split(/\s+/).filter(Boolean);
		let argv: string[];

		if (parts.length === 0) {
			const sessionFile = ctx.sessionManager.getSessionFile();
			if (!sessionFile) {
				ctx.ui.notify("还没找到当前会话文件，先聊几句再试", "warning");
				return;
			}
			argv = [sessionFile];
		} else {
			argv = parts;
		}

		try {
			const out = execFileSync(SCRIPT, argv, { encoding: "utf8", timeout: 30000 });
			const text = out.trim();
			const linkMatch = text.match(/https:\/\/share\.duanz\.xin:1218\/\S+/);
			if (linkMatch) {
				ctx.ui.notify(`分享链接：${linkMatch[0]}`, "info");
				await pi.sendMessage({
					customType: "webshare-link",
					content: `分享链接（公网可访问，用完请 /webshare --rm 删掉）：\n\n${linkMatch[0]}\n\n已分享内容：${argv[0]}`,
					display: true,
				});
			} else {
				ctx.ui.notify(text || "分享完成", "info");
			}
		} catch (err) {
			const msg = err instanceof Error ? (err as { stderr?: string }).stderr?.trim() || err.message : String(err);
			ctx.ui.notify(`分享失败：${msg}`, "error");
		}
	};

	pi.registerCommand("webshare", {
		description: "把当前会话/文件分享成公网临时链接（自建，不限大小）",
		handler,
	});
	pi.registerCommand("pshare", {
		description: "webshare 的别名：分享当前会话到公网",
		handler,
	});
}
