/**
 * goal-guard —— 把「本会话目标」钉进系统提示，防止聊着聊着跑偏。
 *
 *   /goal 用一句话写清这次要达成什么     设置
 *   /goal                                查看
 *   /goal clear                          清除
 *
 * 也可以用环境变量 GOAL 给初始值（自动化场景）。
 *
 * 为什么这么做：AGENTS.md 里的「记得回顾目标」在长会话里会被稀释，
 * 而 systemPrompt 每轮都在。目标只占几十个 token，换的是不会跑偏。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const RULE = `新请求若偏离上面这个目标，先用一句话确认再动手（「这偏离了 X：插队做，还是先记成待办？」），不要默默换题。
每完成一段工作，回头看一眼目标，说清「离目标还差什么」。`;

let goal = process.env.GOAL?.trim() ?? "";

export default function goalGuard(pi: ExtensionAPI) {
	pi.registerCommand("goal", {
		description: "设置/查看本会话目标（会钉进系统提示，防止跑偏）",
		handler: async (args, ctx) => {
			const text = args.trim();

			if (!text) {
				ctx.ui.notify(
					goal
						? `当前目标：${goal}`
						: "还没设目标。用法：/goal 用一句话写清这次要达成什么",
					"info",
				);
				return;
			}

			if (text === "clear" || text === "清除") {
				goal = "";
				ctx.ui.notify("已清除目标", "info");
				return;
			}

			goal = text;
			ctx.ui.notify(`目标已钉住：${goal}`, "info");
		},
	});

	pi.on("before_agent_start", (event) => {
		if (!goal) return;
		return {
			systemPrompt: `${event.systemPrompt}\n\n## 本会话目标\n${goal}\n\n${RULE}`,
		};
	});
}
