#!/usr/bin/env python3
"""生成 D-Hub 每个包的中英文 README（README.md / README.en.md）。

单一真源：改这里再跑 `python3 scripts/gen-readme.py`。
包级元数据（description / version / pi.image）由 scripts/gen-packages.mjs 负责。
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "https://raw.githubusercontent.com/DuanZGit/D-Hub/master/docs/covers"
REPO = "https://github.com/DuanZGit/D-Hub"


def head(slug: str, zh: bool, tagline: str, sub: str) -> str:
    lang = '<p align="center"><a href="./README.en.md">English</a> | <strong>中文</strong></p>' if zh else '<p align="center"><strong>English</strong> | <a href="./README.md">中文</a></p>'
    badges = "\n".join(
        [
            f'<a href="https://www.npmjs.com/package/@duanz/pi-{slug}"><img src="https://img.shields.io/npm/v/@duanz%2Fpi-{slug}.svg?style=flat-square" alt="npm"></a>',
            f'<a href="{REPO}/blob/master/LICENSE"><img src="https://img.shields.io/npm/l/@duanz%2Fpi-{slug}.svg?style=flat-square" alt="license"></a>',
            f'<a href="{REPO}"><img src="https://img.shields.io/badge/GitHub-DuanZGit%2FD--Hub-181717?style=flat-square&logo=github" alt="GitHub"></a>',
            '<img src="https://img.shields.io/badge/pi-extension-34d399?style=flat-square" alt="pi extension">',
        ]
    )
    return f"""# {slug}

{lang}

<p align="center"><img src="{RAW}/{slug}.png" alt="{slug} cover" width="880"></p>

<p align="center"><strong>{tagline}</strong><br><sub>{sub}</sub></p>

<p align="center">
{badges}
</p>

<p align="center">
<code>pi install npm:@duanz/pi-{slug}</code>
</p>
"""


FOOT = """
## License

MIT © DuanZ
"""

PKGS: dict[str, dict] = {}

# ---------------------------------------------------------------- auto-name
PKGS["auto-name"] = {
    "zh": {
        "tagline": "会话聊到一定量，标题自己换成能看懂的那句",
        "sub": "两层命名 · 首条消息秒命名 · 每 20 条会话条目精修一次",
        "body": """
## 它解决什么

新会话的标题要么是空的，要么是第一条消息硬截断的十几个字。侧栏里并排二十个会话，长得都一样，回头找的时候全靠运气。手动改名？改一次忘一次。

这个扩展让标题自己长出来，分两层：

1. **零成本起名**：agent 刚启动、会话还没有名字时，直接把第一条用户消息的前 24 个字设成标题。侧栏和完成通知立刻可辨识。
2. **模型精修**：每轮彻底跑完后检查一次，距上次命名新增 ≥ 20 条会话条目，就调 pi-web 的 `POST /api/sessions/:id/auto-name` 重新生成一次标题。

两层之间用状态文件隔开，不会每轮都去调模型。

## 用法

装完无需配置，在 pi-web 里自动生效：`/reload` 或重启一次即可。

CLI 模式下没有 `PI_SESSION_ID`，扩展自己跳过，不会报错。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `AUTO_NAME_STEP` | `20` | 新增多少条会话条目触发一次精修 |
| `AUTO_NAME_DEBOUNCE` | `300` | 两次命名的最小间隔（秒） |
| `AUTO_NAME_QUICK_MAX` | `24` | 首层截断的最大字数 |
| `AUTO_NAME_OFF` | 空 | 设为 `1` 临时关闭 |
| `PI_WEB_PORT` | 自动探测 | 先试 `30142`，再试 `30152` |

## 状态与日志

- `~/.pi/agent/auto-name-state.json`：按 sessionId 记录条目数与上次命名时间
- `~/.pi/agent/auto-name.log`：每次命名的时间、触发原因、结果

## 限制

- 需要 pi-web 的 auto-name 接口，纯 CLI 环境不生效。
- 精修会消耗当前模型的 token，所以有 20 条 + 300 秒双阈值挡着。
""",
    },
    "en": {
            "tagline": "Session titles rename themselves once a conversation grows",
            "sub": "Two-tier naming · instant title from the first message · refine every 20 entries",
            "body": """
## Why

A new session title is either empty or the first message cut off mid-sentence. Twenty sessions in the sidebar look identical, and you rename them by hand exactly once.

This extension grows titles on its own, in two tiers:

1. **Free naming** — when the agent starts and the session has no title, take the first 24 characters of the first user message. The sidebar and completion notifications become readable immediately.
2. **Model refinement** — after each completed turn, if at least 20 new session entries appeared since the last naming, call pi-web's `POST /api/sessions/:id/auto-name` to regenerate.

State the last naming per session, so it never calls a model every turn.

## Usage

Nothing to configure. Works inside pi-web after `/reload` or a restart.

In CLI mode there is no `PI_SESSION_ID`, so the extension skips itself silently.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `AUTO_NAME_STEP` | `20` | New entries required before a refinement |
| `AUTO_NAME_DEBOUNCE` | `300` | Minimum seconds between renames |
| `AUTO_NAME_QUICK_MAX` | `24` | Max characters for the instant title |
| `AUTO_NAME_OFF` | empty | Set to `1` to disable |
| `PI_WEB_PORT` | auto | Tries `30142`, then `30152` |

## State and logs

- `~/.pi/agent/auto-name-state.json` — entry count and last rename per session
- `~/.pi/agent/auto-name.log` — one line per rename with trigger and result

## Limits

- Requires pi-web's auto-name endpoint; no effect in pure CLI.
- Refinement costs tokens from the current model, hence the 20-entry / 300-second gates.
""",
    },
}

# ---------------------------------------------------------------- d-live
PKGS["d-live"] = {
    "zh": {
        "tagline": "把模型的思考和工具调用，实时改写成页面顶部的进度播报",
        "sub": "本地 SSE · 按句切段 · 多会话隔离 · 不占终端",
        "body": """
## 它解决什么

长任务里，屏幕上只有一个转圈的 spinner 和一串英文工具名。用户在等，却不知道这件事推进到哪了、下一步往哪走。

d-live 把 agent 事件（`thinking_delta`、`tool_execution_start`）按句切段，用**当前会话的模型**改写成 3–6 句日常话，推到 pi-web 页面顶部的浮层条里播。

## 数据流

```
pi agent 事件 → 按句切段 → ctx.modelRegistry.complete() 改写 → 本地 SSE(127.0.0.1:18999/live) → 前端浮层
```

- 切段：至少 70 字才允许按句号切，硬上限 300 字；队列上限 4 段，超了丢新段，保证实时性
- 改写：单次硬超时 12 秒；不写文件名、函数名、端口、路径
- 隔离：每条推送带 `sid`，前端只播当前会话的
- 工具名走零延迟映射表（`read` → 「看一眼」），不调模型

## 用法

```
/d-live on        # 开启（/live 是兼容别名）
/d-live off       # 关闭
/d-live status    # 看当前状态
```

本地端点：`GET /live`（SSE）、`GET /health`、`GET /ping`。

## 前置条件

浮层是前端代码，需要 pi-web 侧注入：`cn-assets/pi-web-live.js` 由 `patches.json` 以 inline 方式注进 `public/sw.js`，由 [pi-web-patch-keeper](https://github.com/DuanZGit/D-Hub/tree/master/extensions/pi-web-patch-keeper) 在 pi-web 升级后重放。

没有这层注入时，扩展的 SSE 服务照常工作，只是页面上看不到浮层。

## 限制

- 每段改写都消耗当前模型 token（实测每段约 2 秒），任务极多时可 `/d-live off`。
- 只面向 pi-web；纯 CLI 没有注入点。
""",
    },
    "en": {
        "tagline": "Turns the model's thinking and tool calls into a live progress strip in pi-web",
        "sub": "Local SSE · sentence-level batching · per-session isolation",
        "body": """
## Why

During a long task the screen shows a spinner and a list of English tool names. The user waits without knowing where the work is going.

d-live takes agent events (`thinking_delta`, `tool_execution_start`), batches them at sentence boundaries, rewrites them with **the current session model** into 3–6 plain sentences, and pushes them to a floating strip at the top of pi-web.

## Data flow

```
pi agent events → sentence batching → ctx.modelRegistry.complete() rewrite → local SSE (127.0.0.1:18999/live) → front-end strip
```

- Batching: at least 70 characters before a sentence break, hard cap 300; queue cap of 4 segments drops new ones to stay live
- Rewrite: 12-second hard timeout; no file names, function names, ports, or paths
- Isolation: every push carries a `sid`; the front end plays only the current session
- Tool names use a zero-latency label map (`read` → "take a look"), no model call

## Usage

```
/d-live on        # enable (/live is an alias)
/d-live off       # disable
/d-live status    # current state
```

Local endpoints: `GET /live` (SSE), `GET /health`, `GET /ping`.

## Prerequisite

The strip is front-end code and needs a pi-web injection: `cn-assets/pi-web-live.js` is inlined into `public/sw.js` through `patches.json`, replayed after pi-web upgrades by [pi-web-patch-keeper](https://github.com/DuanZGit/D-Hub/tree/master/extensions/pi-web-patch-keeper).

Without that injection the SSE server still runs; nothing shows in the page.

## Limits

- Each rewrite costs tokens from the current model (about 2 seconds per segment); `/d-live off` on token-heavy sessions.
- pi-web only — pure CLI has no injection point.
""",
    },
}

# ---------------------------------------------------------------- d-split
PKGS["d-split"] = {
    "zh": {
        "tagline": "聊偏了，按一条消息把会话切成两个独立会话",
        "sub": "原会话一个字节不动 · 不给切点先给时间轴",
        "body": """
## 它解决什么

一个会话聊了很久，中途开了个新话题。继续聊下去两边互相污染上下文；从头开新会话，之前那段又带不走。

d-split 按切点把会话拆成两个独立的 `.jsonl`：切点及之前是 A 段，切点之后是 B 段。**原会话文件保持原样**，两个新会话各自可以继续。

## 为什么自己写文件

会话是一棵树。`fork_branch` 只能切出「根 → 某条路径」，切不出「切点之后」那一段。所以这里按 `parentId` 链自己拼两段：

- A 段 = 根 .. 切点
- B 段 = 切点之后 .. leaf，首条的 `parentId` 改指向一条注入的 `custom_message`（说明「本段由拆分而来，已完成的部分不要重做」）

## 用法

模型调用 `d_split` 工具：

| 参数 | 说明 |
| --- | --- |
| 不传 `cutAt` | 只返回时间轴（序号 / entryId / 角色 / 摘要），用来挑切点 |
| `cutAt` | entryId，或第 N 条用户消息（1 起） |
| `nameA` / `nameB` | 两侧会话标题 |
| `noteB` | 插到 B 开头的说明，省略则自动生成 |
| `wake` | `both`（默认）/ `b` / `none`，拆完要不要自动起跑 |

典型流程：先不带 `cutAt` 跑一次，拿到时间轴后挑 2–3 个候选切点给用户确认，再真拆。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `D_SPLIT_OFF` | 空 | 设为 `1` 关闭 |
| `PI_WEB_PORT` | 自动探测 | `30142` → `30152` |
| `SPLIT_TIMELINE_MAX` | `200` | 时间轴最多返回多少条 |

日志：`~/.pi/agent/d-split.log`

## 限制

- 只处理当前分支，不复制其他分支。
- 拆分后 A/B 是两个新文件，原会话仍在列表里（不删）。
""",
    },
    "en": {
        "tagline": "Split a drifted conversation into two independent sessions at a cut point",
        "sub": "The original session stays byte-for-byte intact",
        "body": """
## Why

A session runs long and drifts to a new topic. Continuing mixes both contexts; starting fresh loses the earlier thread.

d-split cuts a session into two independent `.jsonl` files at a cut point: everything up to the cut becomes session A, everything after becomes session B. **The original file is untouched**, and both new sessions can continue.

## Why it writes files itself

A session is a tree. `fork_branch` can only produce "root → some path"; it cannot extract "everything after a cut point". So this extension rebuilds both halves along the `parentId` chain:

- A = root .. cut point
- B = after cut point .. leaf, with the first entry's `parentId` pointing at an injected `custom_message` ("this segment was split off — do not redo completed work")

## Usage

The model calls the `d_split` tool:

| Parameter | Meaning |
| --- | --- |
| no `cutAt` | Return only the timeline (index / entryId / role / summary) so a cut point can be chosen |
| `cutAt` | entryId, or the Nth user message (1-based) |
| `nameA` / `nameB` | Titles for both sessions |
| `noteB` | Note prepended to B; auto-generated when omitted |
| `wake` | `both` (default) / `b` / `none` — whether to start them right away |

Typical flow: run once without `cutAt`, offer 2–3 candidate cut points, then split.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `D_SPLIT_OFF` | empty | Set to `1` to disable |
| `PI_WEB_PORT` | auto | `30142` → `30152` |
| `SPLIT_TIMELINE_MAX` | `200` | Max timeline entries returned |

Log: `~/.pi/agent/d-split.log`

## Limits

- Works on the current branch only; other branches are not copied.
- After splitting, the original session is still listed (not deleted).
""",
    },
}

# ---------------------------------------------------------------- goal-guard
PKGS["goal-guard"] = {
    "zh": {
        "tagline": "把本次要达成的事钉进系统提示，长会话不跑偏",
        "sub": "一行目标 · 两条守则 · 只占几十个 token",
        "body": """
## 它解决什么

长会话最大的问题是目标自己蒸发。用户因为一个小问题提了个修改，助手埋头做完，原始目标就没了，全程没人提醒。

写进 `AGENTS.md` 也不够：那段文字在长上下文里会被稀释，而且它说的是「记得回顾目标」这种抽象要求。

goal-guard 把**这一次要达成什么**钉进每一轮的系统提示。目标只有一行，加上两条守则，总共几十个 token，换来的是每轮都被看见。

## 用法

```
/goal 把登录流程改成邮箱验证码       # 设置（后面的话就是目标）
/goal                                # 查看当前目标
/goal clear                          # 清除（也接受「清除」）
```

自动化场景可以用环境变量给初始值：

```bash
GOAL="把 d-reach 的额度计数改成按天" pi
```

## 原理

```ts
pi.on("before_agent_start", (event) => goal ? {
  systemPrompt: `${event.systemPrompt}\\n\\n## 本会话目标\\n${goal}\\n\\n${RULE}`,
} : undefined);
```

注入的守则两条：

1. 新请求若偏离目标，先用一句话确认再动手（「这偏离了 X：插队做，还是先记成待办？」）
2. 每完成一段工作，回头看一眼目标，说清「离目标还差什么」

## 限制

- 目标保存在扩展的进程内变量里，pi 重启后需要重新 `/goal`；想持久化就用 `GOAL` 环境变量。
- 它只负责「让目标每轮可见」，不负责判定目标是否完成。
""",
    },
    "en": {
        "tagline": "Pins the goal of this session into every system prompt",
        "sub": "One line of goal · two rules · a few dozen tokens",
        "body": """
## Why

The main failure of a long session is that the goal evaporates. The user asks for a small fix, the assistant dives in, and the original objective is silently gone with nobody noticing.

Putting it in `AGENTS.md` is not enough: that text gets diluted in a long context, and it only says "remember to revisit the goal" — an abstraction.

goal-guard pins **what this session must achieve** into the system prompt of every turn. One line of goal plus two rules, a few dozen tokens, seen every turn.

## Usage

```
/goal Migrate the login flow to email codes   # set (rest of the line is the goal)
/goal                                        # show current goal
/goal clear                                  # clear
```

For automation, seed it from the environment:

```bash
GOAL="Make d-reach quota counting daily" pi
```

## How

```ts
pi.on("before_agent_start", (event) => goal ? {
  systemPrompt: `${event.systemPrompt}\\n\\n## Session goal\\n${goal}\\n\\n${RULE}`,
} : undefined);
```

The two injected rules:

1. If a new request drifts from the goal, confirm in one sentence before acting ("this diverges from X: do it now, or record it as a todo?")
2. After each chunk of work, look back at the goal and state what is still missing

## Limits

- The goal lives in a process variable; after a pi restart you must set it again unless you use `GOAL`.
- It makes the goal visible every turn; it does not judge whether the goal is met.
""",
    },
}

# ---------------------------------------------------------------- pi-cmd-guard
PKGS["pi-cmd-guard"] = {
    "zh": {
        "tagline": "会打印明文密钥的命令，根本发不出去",
        "sub": "tool_call 阶段拦截 · 命令不执行 · 给替代写法",
        "body": """
## 它解决什么

2026-11-05 的事故：一次 `sudo systemctl cat caddy` 把 unit 里的 `Environment=ALI_ACCESS_KEY_SECRET=...` 整行打进了上下文。命令成功执行，密钥随后进了对话记录。

事后遮蔽没有意义——值已经发出去了。所以要拦在**执行之前**。

## 拦截清单

| 规则 | 为什么危险 | 替代写法 |
| --- | --- | --- |
| `systemctl restart/stop/kill pi-web` | 掐断其他正在跑的会话，in-flight 轮次全丢 | `d_restart` 工具或 `d-restart` 命令 |
| `systemctl cat` | unit 里的 `Environment=` 整行带明文 | `systemctl show <unit> -p EnvironmentFiles,ExecStart,User` |
| `systemctl show ... Environment` | 直接 dump 变量值 | `systemctl show <unit> -p EnvironmentFiles` |
| 裸 `env` / `printenv` | dump 当前进程全部环境变量 | 只查确定的变量名 |
| `printenv <敏感名>` | 打印该变量明文 | 用 `safe_inspect` 类工具看存在/长度/哈希 |
| `cat <密钥文件>` | 文件内容就是明文密钥 | 看权限与哈希，不看值 |
| 读 `/proc/*/environ` | 进程环境块原始字节 | 同上 |
| `grep` 全环境 | 命中行把值一起打出来 | 按字段名白名单过滤 |

## 用法

装完即生效，无需配置。

- 关闭：`PI_CMD_GUARD=off`
- 用户自己敲的命令（`!` 开头）不经过这里，仍然可以执行

## 实现

在 `tool_call` 钩子里匹配 bash 命令，返回 `{ block: true, reason, alternative }`，命令根本不会执行。规则表 `RULES` 是一条正则 + 一句原因 + 一个替代写法，加新规则只加一条。

## 限制

- 只覆盖 `bash` 工具；其他执行路径（用户 `!` 命令、外部脚本）不在范围内。
- 规则是正则，刻意的变形写法可能绕过——这是防误触，不是防攻击。
""",
    },
    "en": {
        "tagline": "Commands that would print plaintext secrets never run",
        "sub": "Blocked at tool_call · with an alternative that works",
        "body": """
## Why

The incident: one `sudo systemctl cat caddy` printed the unit's `Environment=ALI_ACCESS_KEY_SECRET=...` line straight into context. The command succeeded, and the secret went into the transcript.

Masking afterwards is pointless — the value already left. This blocks **before execution**.

## Rules

| Rule | Why it is dangerous | Instead |
| --- | --- | --- |
| `systemctl restart/stop/kill pi-web` | Kills other running sessions and in-flight turns | `d_restart` tool or `d-restart` |
| `systemctl cat` | Prints `Environment=` with plaintext values | `systemctl show <unit> -p EnvironmentFiles,ExecStart,User` |
| `systemctl show ... Environment` | Dumps variable values | `systemctl show <unit> -p EnvironmentFiles` |
| bare `env` / `printenv` | Dumps the whole process environment | Ask for one variable by name |
| `printenv <secret>` | Prints that value | Inspect existence / length / hash |
| `cat <secret file>` | The file *is* the secret | Check permissions and hash |
| Reading `/proc/*/environ` | Raw process environment bytes | Same as above |
| `grep` over the environment | Matching lines carry the values | Filter by allowlisted field names |

## Usage

Enabled on install, nothing to configure.

- Disable: `PI_CMD_GUARD=off`
- Commands the user types (`!` prefix) bypass this hook and still work

## How

A `tool_call` hook matches bash commands and returns `{ block: true, reason, alternative }`, so the command never runs. `RULES` is one regex + one reason + one alternative per entry — adding a rule is one object.

## Limits

- Covers the `bash` tool only; user `!` commands and external scripts are out of scope.
- Patterns are regexes; deliberate obfuscation can slip through. This is anti-accident, not anti-attacker.
""",
    },
}

# ---------------------------------------------------------------- patch-keeper
PKGS["pi-web-patch-keeper"] = {
    "zh": {
        "tagline": "pi-web 升级会整包覆盖，本地补丁在下次加载时自动重放",
        "sub": "加载即检查 · 幂等 · 被冲掉才写回",
        "body": """
## 它解决什么

pi-web 的本地改动（完成通知显示项目名与会话名、界面文案等）只能改在编译产物里：`.next/server/chunks`、`.next/static`、`public/sw.js`。`npm update` 或重新安装会把这些文件整包覆盖，补丁全丢，而且没人提醒。

## 它做什么

只做一件事：扩展加载时跑一次 `apply.py`。

- 所有改动登记在 `~/.pi/agent/.cn-patches/patches.json`
- `apply.py` 负责重放，**幂等**：已应用的跳过，只有被升级冲掉的才写回
- 有重放发生时，在下一次 `agent_start` 提醒你重启 pi-web

## 用法

1. 建立补丁目录：

```
~/.pi/agent/.cn-patches/
├── patches.json     # 补丁登记表
└── apply.py         # 重放脚本
```

2. 装扩展，重启 pi-web。

扩展本身不判断补丁怎么写，只决定**什么时候跑**。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PI_WEB_PATCH_OFF` | 空 | 设为 `1` 关闭 |
| `PI_WEB_PATCH_INTERVAL_H` | `6` | 两次检查的最小间隔（小时） |

## 状态与日志

- `~/.pi/agent/.cn-patches/keeper-state.json`：上次检查时间
- `~/.pi/agent/.cn-patches/keeper.log`：每次运行、重放了哪些补丁

## 限制

- 需要你自己准备 `patches.json` 与 `apply.py`；这是通用外壳，不含具体补丁内容。
- 有重放后仍需重启 pi-web 才生效（扩展只提醒，不重启）。
""",
    },
    "en": {
        "tagline": "Local pi-web patches survive upgrades by replaying themselves on load",
        "sub": "Checked on load · idempotent · rewrites only what the upgrade wiped",
        "body": """
## Why

Local pi-web changes (project and session names in completion notifications, UI copy) can only live in build artifacts: `.next/server/chunks`, `.next/static`, `public/sw.js`. An `npm update` or reinstall replaces those files wholesale, the patches vanish, and nothing warns you.

## What it does

One thing: run `apply.py` when the extension loads.

- All changes are registered in `~/.pi/agent/.cn-patches/patches.json`
- `apply.py` replays them and is **idempotent**: applied patches are skipped; only ones wiped by an upgrade are written back
- When a replay happens, the next `agent_start` reminds you to restart pi-web

## Usage

1. Create the patch directory:

```
~/.pi/agent/.cn-patches/
├── patches.json     # patch registry
└── apply.py         # replay script
```

2. Install the extension and restart pi-web.

The extension does not know how patches are written — only when to run them.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PI_WEB_PATCH_OFF` | empty | Set to `1` to disable |
| `PI_WEB_PATCH_INTERVAL_H` | `6` | Minimum hours between checks |

## State and logs

- `~/.pi/agent/.cn-patches/keeper-state.json` — last check time
- `~/.pi/agent/.cn-patches/keeper.log` — each run and what it replayed

## Limits

- You supply `patches.json` and `apply.py`; this is the shell, not the patches.
- A replay still needs a pi-web restart to take effect (the extension only reminds).
""",
    },
}

# ---------------------------------------------------------------- skill-search
PKGS["skill-search"] = {
    "zh": {
        "tagline": "技能目录不必常驻系统提示，留一个查询入口就够",
        "sub": "按需检索 · 只返回路径 · 不自动注入",
        "body": """
## 它解决什么

pi 的技能目录常驻系统提示。本机 82 个技能全部摊开约 21,164 字符（≈6,500 tokens），**每一轮都在烧**，不管这次用不用得上。

两个现成解法都不合适：

1. 把低频技能设成 `disable-model-invocation` —— 省了 token，但模型**完全看不见**它们，除非用户记得打 `/skill:名字`
2. 把技能索引全量注入每轮上下文 —— 省下的 token 原样花回去

本扩展补的是这条缝：技能目录不必常驻，**只要查询入口常驻**。一个工具 schema 约 120 tokens/轮。

## 用法

模型调用 `skill_search`：

| 参数 | 说明 |
| --- | --- |
| `query` | 任务描述或关键词；省略则列出全部技能名 |
| `limit` | 返回条数，默认 8 |

返回 `name` / `description` / SKILL.md 绝对路径。模型拿到路径后用 `read` 读正文再决定，所以路径是必返回字段。

## 三条设计约束

1. **只给路径，不给正文**。论文 SkillRouter 在 80K 候选上实测：只暴露 name + description 会让路由准确率掉 37–44 个百分点，必须 body-aware。
2. **不自动注入**。在 `before_agent_start` 塞提示等于把省下的 token 花回去；工具躺在工具列表里就够。
3. **不碰 frontmatter**。扩展只占 extensions 目录，`uipro update` / `npx impeccable update` 不会覆盖它。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PI_AGENT_DIR` | `~/.pi/agent` | 技能根目录 |
| `DESC_MAX` | `200` | 描述截断长度 |

## 与 ask-me 技能的关系

`ask-me` 是给人的入口（显式 `/skill:ask-me`），`skill_search` 是给模型的入口。装了本扩展后，`ask-me` 的扫描脚本可以退居备用（Minis / DSH 等没有本扩展的环境仍用它）。
""",
    },
    "en": {
        "tagline": "Skill catalogs do not need to sit in the system prompt — one lookup tool is enough",
        "sub": "On-demand retrieval · paths only · no auto-injection",
        "body": """
## Why

pi keeps the skill catalog in the system prompt. On this machine 82 skills take about 21,164 characters (≈6,500 tokens) **every turn**, whether or not any of them is used.

Both off-the-shelf answers fall short:

1. Marking low-frequency skills `disable-model-invocation` saves tokens but makes them **invisible** to the model unless the user remembers `/skill:name`
2. Injecting the full index each turn spends the savings right back

This extension fills the gap: the catalog does not need to be resident, only the **lookup entry** does. One tool schema is about 120 tokens per turn.

## Usage

The model calls `skill_search`:

| Parameter | Meaning |
| --- | --- |
| `query` | Task description or keywords; omit to list every skill name |
| `limit` | Results to return, default 8 |

Returns `name` / `description` / absolute SKILL.md path. The model reads the body with `read` before deciding, so `path` is mandatory.

## Three design constraints

1. **Paths, not bodies.** SkillRouter measured on 80K candidates: exposing only name + description drops routing accuracy by 37–44 points. Retrieval must be body-aware.
2. **No auto-injection.** Stuffing a hint into `before_agent_start` spends the savings again; a tool in the list is enough.
3. **No frontmatter edits.** The extension lives in the extensions directory, so `uipro update` / `npx impeccable update` never clobber it.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PI_AGENT_DIR` | `~/.pi/agent` | Skill root |
| `DESC_MAX` | `200` | Description truncation length |

## Relation to ask-me

`ask-me` is the human entry point (`/skill:ask-me`); `skill_search` is the model's. With this extension installed, the `ask-me` scan script becomes a fallback for environments without it (Minis, DSH).
""",
    },
}

# ---------------------------------------------------------------- skill-trigger
PKGS["skill-trigger"] = {
    "zh": {
        "tagline": "该走统一路由的时候，别让模型绕过去",
        "sub": "触发词软注入 · 内置工具硬门禁 · 逃生舱保留",
        "body": """
## 它解决什么

pi 的技能是渐进披露：系统提示里只有 name + description，正文要模型自己决定去 `read`。官方文档原话是 "models don't always do this; use prompting or /skill:name to force it"。

2026-09-25 实测漏过一次：用户说「你去全网看一下」，助手直接调了内置 `web_search` / `fetch_content`，没走 d-reach。后果是额度记账失真、免费通道一个没用、只跑了一轮没有追证轮。

## 两层防线

**层 1 — 软注入**：`before_agent_start` 里检测触发词，命中就往本轮注入一条不显示的提醒（「这个任务该走 d-reach，先读 SKILL.md」）。

**层 2 — 硬门禁**：`tool_call` 里拦住内置 `web_search` / `fetch_content`。本会话没读过对应 SKILL.md 就不放行，并给出该读哪个文件。

## 层 2 刻意做窄

1. **只拦这两个内置工具，不碰 bash**。日常 `curl` 全走 bash，拦它需要域名白名单那种易错设计。
2. **本地资源不拦**：输入里没有 `http(s)://` 就放行（`file://`、本地图片/视频）。
3. **逃生舱**：任一输入字段带 `#d-reach:allow` 即放行（需先向用户说明理由）；或 `PI_SKILL_TRIGGER_GATE=off` 整层关掉。

## 扩展新技能

往 `RULES` 加一条即可，软注入与硬门禁共用同一张表：

```ts
{
  name: "d-reach",
  path: "/home/you/.pi/agent/skills/d-reach/SKILL.md",
  patterns: /搜一下|全网|search|看看有没有/i,
  hint: "这次要联网查东西，先读 d-reach 的 SKILL.md 再做。",
}
```

## 限制

- 规则是正则，措辞变化可能漏命中——它是兜底，不是保险。
- 硬门禁只对内置工具生效；模型如果改用 bash 里的 `curl`，本扩展不会拦（这是有意的）。
""",
    },
    "en": {
        "tagline": "When a task should route through one skill, do not let the model bypass it",
        "sub": "Soft trigger injection · hard gate on built-in tools · escape hatch kept",
        "body": """
## Why

pi skills are progressively disclosed: the system prompt carries only name + description, and the model decides whether to `read` the body. The docs say it plainly: "models don't always do this; use prompting or /skill:name to force it".

A real miss: the user said "go look this up across the web", and the assistant called the built-in `web_search` / `fetch_content` instead of the unified search router. Quota accounting drifted, no free channels were used, and there was no follow-up verification round.

## Two layers

**Layer 1 — soft injection**: `before_agent_start` matches trigger phrases and injects an invisible reminder for this turn ("this task should go through d-reach; read its SKILL.md first").

**Layer 2 — hard gate**: `tool_call` blocks the built-in `web_search` / `fetch_content` until the matching SKILL.md has been read in this session, and names the file to read.

## Layer 2 is deliberately narrow

1. **Only those two built-in tools; bash untouched.** Daily `curl` runs through bash, and gating it would need an error-prone domain allowlist.
2. **Local resources pass**: input without `http(s)://` is allowed (`file://`, local images and videos).
3. **Escape hatch**: any input field containing `#d-reach:allow` passes (explain to the user first); or `PI_SKILL_TRIGGER_GATE=off` disables the layer.

## Adding a skill

Add one entry to `RULES`; both layers read the same table:

```ts
{
  name: "d-reach",
  path: "/home/you/.pi/agent/skills/d-reach/SKILL.md",
  patterns: /search|look up|find out/i,
  hint: "This task needs the web: read d-reach's SKILL.md first.",
}
```

## Limits

- Patterns are regexes; rewording can miss. It is a safety net, not a guarantee.
- The hard gate covers built-in tools only. If the model uses `curl` in bash, this extension stays out of the way (intentionally).
""",
    },
}

# ---------------------------------------------------------------- sol-pi-stats
PKGS["sol-pi-stats"] = {
    "zh": {
        "tagline": "observation-pack 省下的上下文，常驻显示在状态栏",
        "sub": "事件驱动 · 不设定时器 · 异常静默",
        "body": """
## 它解决什么

sol-pi 的 observation-pack 会把大块工具输出折成占位符，省下大量上下文。但它自己只在「省到东西」时闪 4 秒，之后把状态清掉——省下的量到底累计了多少，事后完全看不到。

这个扩展把 ledger 汇总成一条常驻状态：

```
⚡SoL 省 36M tok · 22 包
```

想看明细就用 `/sol`：包数、累计避免量、金额区间、Top 包。

## 数据源

```
<sessionDir>/sol-pi/<sessionId>/observation-pack/ledger.jsonl
```

`event=placeholder` 的行里 `removedTokens` 是该次请求少发的 token（同一个包每次请求各记一条）。

## 实现要点

- **事件驱动，不设定时器**：跟着会话事件刷新，避免空转
- **只在同步阶段读缓存**：不 `await`，防止会话重载后 `ctx` 失效
- **（size, mtime）缓存**：ledger 没变就不重新解析
- **异常静默**：统计失败不影响会话

## 用法

装完即生效。状态栏常驻；`/sol` 看明细。

## 限制

- 需要 sol-pi / observation-pack 真的在产生 `ledger.jsonl`，否则状态栏不会出现数字。
- 金额是区间估算（按输入价与缓存价推算），不是账单。
""",
    },
    "en": {
        "tagline": "Context saved by observation-pack, always visible in the status bar",
        "sub": "Event-driven · no timers · silent on failure",
        "body": """
## Why

sol-pi's observation-pack folds large tool outputs into placeholders and saves a lot of context. But it only flashes for 4 seconds when it saves something, then clears the status — the cumulative amount is invisible afterwards.

This extension aggregates the ledger into one always-on status line:

```
⚡SoL saved 36M tok · 22 packs
```

`/sol` shows details: pack count, cumulative savings, cost range, top packs.

## Data source

```
<sessionDir>/sol-pi/<sessionId>/observation-pack/ledger.jsonl
```

In rows with `event=placeholder`, `removedTokens` is what that request avoided sending (one row per pack per request).

## Implementation notes

- **Event-driven, no timers** — refreshes on session events, never idles
- **Reads cache only in sync phases** — no `await`, so a reloaded session cannot leave a stale `ctx`
- **(size, mtime) cache** — an unchanged ledger is not re-parsed
- **Silent on failure** — stats never break a session

## Usage

Enabled on install. Status line is permanent; `/sol` for details.

## Limits

- Requires sol-pi / observation-pack to actually write `ledger.jsonl`; otherwise no numbers appear.
- Cost figures are estimates from input and cache prices, not a bill.
""",
    },
}

# ---------------------------------------------------------------- d-restart
PKGS["d-restart"] = {
    "zh": {
        "tagline": "重启前先记下谁在干活，重启完再把它们叫醒",
        "sub": "忙碌会话快照 · 就绪后自动接力 · 补回被打断的工具调用",
        "body": """
## 它解决什么

直接 `systemctl restart pi-web` 会掐断所有正在跑的会话——对话断在半路，工具调用悬空，回来还得自己解释「刚才做到哪了」。

d-restart 把这件事变成一次无损交接：**重启前快照，重启后接力。**

## 它做了什么

1. 调 pi-web 本地 API 列出所有正在跑任务的会话（`/api/agent/running`）
2. 把会话清单写进快照文件
3. 等几秒，让触发重启的那个回复先落到磁盘
4. 重启服务
5. 轮询端口直到服务真的起来
6. 给每个会话发一条「继续」指令，让它自己往下跑
7. 补回被打断的 `toolCall`（补一条 `isError` 的 `toolResult`），避免重放时模型报 400

守护进程用 `systemd-run --user` 派发到独立 unit，否则重启 pi-web 会把它自己一起掐死。

## 用法

三种触发方式，效果一样：

| 方式 | 用法 |
| --- | --- |
| Agent 工具 | 模型自己调 `d_restart`（改完插件让它重启时） |
| 斜杠命令 | `/d-restart`（简写 `/restart`） |
| 命令行 | `d-restart`，或 `node <包目录>/scripts/d-restart.mjs` |

命令行参数：

```bash
d-restart.mjs --delay 3 --caller <sessionId>
d-restart.mjs --dry-run        # 只看当前有几个忙碌会话，不重启
```

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PI_WEB_PORT` | 自动探测 | 探测 `~/.pi/agent/pi-web-run/*.json`，失败退回 `30142` |
| `PI_WEB_SERVICE` | `pi-web.service` | systemd user unit 名 |
| `PI_WEB_RESTART_CMD` | 空 | 自定义重启命令，设置后优先于 systemctl |
| `PI_SAFE_RESTART_STATE` | `~/.pi/agent/state/piweb-restarting-sessions.json` | 快照文件 |
| `PI_SAFE_RESTART_LOG` | `/tmp/piweb-safe-restart.log` | 日志 |

非 systemd 环境（docker / pm2）：

```bash
export PI_WEB_RESTART_CMD="docker restart pi-web"
export PI_WEB_PORT=30142
```

## 限制

- **Linux + systemd user** 是默认路径。macOS 没有 systemd，靠 `PI_WEB_RESTART_CMD` 兜底，但守护进程只能是普通 detached 进程，重启命令若把整个进程树带走就失效。
- 依赖 pi-web 的 `/api/agent/running` 与 `/api/agent/:id` 接口，纯 CLI 模式用不上。
- 快照只存会话 ID 和 session 文件路径，不存对话内容——内容本来就在 session 文件里。

## 排障

```bash
tail -f /tmp/piweb-safe-restart.log
```

常见失败：

- `共扫描到 0 个正在忙碌的会话` —— 端口探错了，或会话在重启前就结束了
- `超时 60s 未能探测到 pi-web 恢复就绪` —— 服务没起来，先手动 `systemctl --user status pi-web`
- `恢复会话 ... 失败` —— 会话文件被删了或 ID 对不上
""",
    },
    "en": {
        "tagline": "Note who is working, restart, then wake every session back up",
        "sub": "Busy-session snapshot · automatic handoff after readiness · interrupted tool calls repaired",
        "body": """
## Why

A plain `systemctl restart pi-web` kills every running session — the conversation stops mid-turn, tool calls dangle, and afterwards the model has to guess where it was.

d-restart turns that into a lossless handoff: **snapshot before, resume after**.

## What it does

1. Lists sessions currently running a task through pi-web's local API (`/api/agent/running`)
2. Writes the list into a snapshot file
3. Waits a few seconds so the reply that triggered the restart lands on disk
4. Restarts the service
5. Polls the port until it is actually up
6. Sends each session a "continue" instruction so it keeps going
7. Repairs interrupted `toolCall`s (adds an `isError` `toolResult`) so replay does not 400

The supervisor is dispatched with `systemd-run --user` into its own unit; otherwise restarting pi-web would kill it too.

## Usage

Three triggers, same effect:

| Way | How |
| --- | --- |
| Agent tool | The model calls `d_restart` |
| Slash command | `/d-restart` (alias `/restart`) |
| CLI | `d-restart`, or `node <package>/scripts/d-restart.mjs` |

CLI flags:

```bash
d-restart.mjs --delay 3 --caller <sessionId>
d-restart.mjs --dry-run        # list busy sessions without restarting
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PI_WEB_PORT` | auto | Probes `~/.pi/agent/pi-web-run/*.json`, falls back to `30142` |
| `PI_WEB_SERVICE` | `pi-web.service` | systemd user unit |
| `PI_WEB_RESTART_CMD` | empty | Custom restart command, takes precedence over systemctl |
| `PI_SAFE_RESTART_STATE` | `~/.pi/agent/state/piweb-restarting-sessions.json` | Snapshot file |
| `PI_SAFE_RESTART_LOG` | `/tmp/piweb-safe-restart.log` | Log file |

Non-systemd environments (docker / pm2):

```bash
export PI_WEB_RESTART_CMD="docker restart pi-web"
export PI_WEB_PORT=30142
```

## Limits

- **Linux + systemd user** is the default path. macOS has no systemd and falls back to `PI_WEB_RESTART_CMD`, where the supervisor is an ordinary detached process — if the restart command takes the whole process tree down, it dies too.
- Depends on pi-web's `/api/agent/running` and `/api/agent/:id`; nothing to do in pure CLI.
- The snapshot stores session IDs and file paths only — content already lives in the session files.

## Troubleshooting

```bash
tail -f /tmp/piweb-safe-restart.log
```

Common failures:

- `scanned 0 busy sessions` — wrong port, or sessions ended before the restart
- `timed out after 60s waiting for pi-web` — service did not come up; check `systemctl --user status pi-web`
- `resume session ... failed` — session file removed or ID mismatch
""",
    },
}

META = {
    "auto-name": "extensions/auto-name",
    "d-live": "extensions/d-live",
    "d-split": "extensions/d-split",
    "goal-guard": "extensions/goal-guard",
    "pi-cmd-guard": "extensions/pi-cmd-guard",
    "pi-web-patch-keeper": "extensions/pi-web-patch-keeper",
    "skill-search": "extensions/skill-search",
    "skill-trigger": "extensions/skill-trigger",
    "sol-pi-stats": "extensions/sol-pi-stats",
    "d-restart": "plugins/d-restart",
}

if __name__ == "__main__":
    for slug, spec in PKGS.items():
        for lang in ("zh", "en"):
            d = spec[lang]
            text = head(slug, lang == "zh", d["tagline"], d["sub"]) + d["body"] + FOOT
            name = "README.md" if lang == "zh" else "README.en.md"
            path = os.path.join(ROOT, META[slug], name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.lstrip("\n"))
            print(path)
