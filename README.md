# DHub

**个人的 agent 工具箱** — pi 扩展、独立插件与 agent 技能，一个仓库全收。

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D20-black.svg)](https://nodejs.org)
[![npm](https://img.shields.io/badge/npm-%40duanz-black.svg)](https://www.npmjs.com/org/duanz)

不用再从十几个仓库里找某个小工具。这里是我给自己搭的一堆东西：让会话有名字的通知补丁、防止命令炸机器的守卫、把思考过程推到界面上的浮层、一堆按任务自动挑技能的小扩展，以及几十个 SKILL.md。

写这些的出发点很朴素 —— 每天用 agent 干活时遇到的具体麻烦，顺手就修了。

---

## 目录

- [里面有什么](#里面有什么)
- [安装](#安装)
- [扩展 ext­ensions](#扩展-extensions)
- [插件 plugins](#插件-plugins)
- [技能 skills](#技能-skills)
- [目录结构](#目录结构)
- [License](#license)

---

## 里面有什么

三类东西，按「怎么用」分开：

| 类型 | 是什么 | 怎么生效 |
|---|---|---|
| **扩展** `extensions/` | 跑在 pi 进程里的 TypeScript 扩展，挂钩子、注册工具、加命令 | 装成 pi 包，或放进 `~/.pi/agent/extensions/` |
| **插件** `plugins/` | 独立的命令行工具 / 服务级集成 | 各自 README |
| **技能** `skills/` | `SKILL.md` 驱动的行为指南，模型按需加载 | 复制到 `~/.pi/agent/skills/` |

---

## 安装

每个扩展是一个独立的 npm 包，**用哪个装哪个**，不整包搬。

| 包 | 做什么 |
|---|---|
| `@duanz/pi-auto-name` | 会话自动命名 |
| `@duanz/pi-d-split` | 会话按切点拆分 |
| `@duanz/pi-d-live` | 思考与工具调用实时推到界面浮层 |
| `@duanz/pi-pi-cmd-guard` | 拦住危险命令 |
| `@duanz/pi-pi-web-patch-keeper` | 升级后重打本地补丁 |
| `@duanz/pi-skill-search` | 检索本机全部技能 |
| `@duanz/pi-skill-trigger` | 按任务自动匹配技能 |
| `@duanz/pi-goal-guard` | `/goal` 把目标钉进系统提示 |
| `@duanz/pi-sol-pi-stats` | 状态栏 token / 上下文用量 |
| `@duanz/pi-d-restart` | pi-web 安全重启器 |

```bash
pi install npm:@duanz/pi-d-split
pi install npm:@duanz/pi-d-restart
```

装完重启一次 pi-web 生效。

**想改源码**：

```bash
git clone https://github.com/DuanZGit/D-Hub ~/projects/D-Hub
```

**技能**手动挑，复制目录就行：

```bash
cp -r ~/projects/D-Hub/skills/ask-me ~/.pi/agent/skills/
```

> 不要用 `pi install git:...` 装这个仓库。根 `package.json` 是 private、不含扩展清单，git 方式装不进来 —— 这是故意的，避免一次性塞进十个扩展。
> 技能也没打进任何包里：一次塞 23 个技能进上下文不划算，用到哪个拿哪个。

---

## 扩展 extensions

每个扩展解决一个具体问题，彼此独立，可以只装需要的。

| 扩展 | 解决什么 | 钩子 |
|---|---|---|
| [auto-name](extensions/auto-name/) | 会话第一句话就自动命名。这样完成通知弹出来时，你能看出**是哪个会话**跑完了 | `agent_start` |
| [pi-web-patch-keeper](extensions/pi-web-patch-keeper/) | pi-web 升级会覆盖我改过的本地补丁，这个扩展在启动时把它们重新打上，并提示重启 | 加载时 |
| [pi-cmd-guard](extensions/pi-cmd-guard/) | 拦住会毁东西的命令：`cat .env`、裸 `env`、`systemctl restart pi-web` | `tool_call` |
| [d-split](extensions/d-split/) | 会话聊偏了就按切点拆成两个独立会话，原会话一个字不动 | 工具 `d_split` |
| [d-live](extensions/d-live/) | 把思考和工具调用实时改写成「内心独白」，经本地 SSE 推到界面顶部浮层 | `thinking_delta` |
| [goal-guard](extensions/goal-guard/) | `/goal 一句话` 把本次目标钉进系统提示，防止聊着聊着跑题 | 命令 |
| [skill-search](extensions/skill-search/) | 搜本机全部技能，返回该用哪个 + `SKILL.md` 路径 | 工具 |
| [skill-trigger](extensions/skill-trigger/) | 按任务内容自动匹配技能，省掉手动挑的一步 | 会话开始 |
| [sol-pi-stats](extensions/sol-pi-stats/) | 状态栏的 token / 上下文用量 | 状态栏 |

---

## 插件 plugins

### [d-restart](plugins/d-restart/)

pi-web 的安全重启器。普通 `systemctl restart` 会把正在跑的会话全掐断，它做的事是：

1. 逐个快照忙碌会话的现场
2. 重启服务
3. 等端口就绪，再把每个会话叫醒接着干

```bash
d-restart                  # 重启，自动续跑
d-restart --dry-run        # 只看会动哪些会话
```

装好以后在 agent 里也有对应工具，不用切终端。

---

## 技能 skills

`SKILL.md` 形式的技能，覆盖几块日常：写作去 AI 腔、图解与图表、旅行行程、咖啡萃取、机械原理可视化，以及一批「怎么组织工作流」的元技能（`ask-me`、`show-me`、`ponytail` 家族）。

| 技能 | 用途 |
|---|---|
| [ask-me](skills/ask-me/) | 不确定用哪个技能时，让它按当前任务列清单 |
| [show-me](skills/show-me/) | 解释的形态阶梯：文字 → 图 → 交互页 → 自播放讲解 |
| [ponytail](skills/ponytail/) | 最懒但能跑通的方案；附 `-audit`/`-debt`/`-gain`/`-help`/`-review` |
| [DK](skills/DK/) | 做菜、营养、家电数码的日常决策 |
| [gushen](skills/gushen/) | 每日挂单 + 投研问答 |
| [teardown](skills/teardown/) | 把真实机械做成可拆解的 3D 交互说明书 |
| [coffee-extraction](skills/coffee-extraction/) | 萃取追踪、设备标定与排障 |
| [lieflat-less-ai-tone](skills/lieflat-less-ai-tone/) | 按规则改写文字里的 AI 痕迹 |
| [svg-diagram](skills/svg-diagram/) · [fireworks-tech-graph](skills/fireworks-tech-graph/) | 图解与科技图表 |
| [handoff](skills/handoff/) | 把当前会话压成交接文档给下一个 agent |
| [trip-planner](skills/trip-planner/) · [jianhao-travel-planner](skills/jianhao-travel-planner/) | 国内多日游行程规划 |
| [magpie-quota](skills/magpie-quota/) · [magpie-setup](skills/magpie-setup/) | 订阅额度查询与配置 |
| [ui-ux-pro-max](skills/ui-ux-pro-max/) · [taste](skills/taste/) | 界面设计与审美把关 |
| [travel-photo-abstraction](skills/travel-photo-abstraction/) | 旅行照片抽象化处理 |

---

## 目录结构

```
D-Hub/
├── extensions/          # pi 扩展，一目录一个
│   ├── auto-name/
│   ├── pi-cmd-guard/
│   └── ...
├── plugins/             # 独立插件
│   └── d-restart/
├── skills/              # SKILL.md 技能
│   ├── ask-me/
│   └── ...
├── scripts/             # 生成各子包 package.json、批量发布
├── package.json         # 仓库根（private），不是 pi 包
└── LICENSE
```

---

## 更新

```bash
pi update npm:@duanz/pi-d-split   # 更新单个
pi update --extensions            # 更新全部
```

改完源码发版：

```bash
node scripts/gen-packages.mjs     # 同步子包 version
node scripts/publish-all.mjs      # 发布到 npm（可只发一个：传目录名）
```

这个仓库是**唯一真源**，npm 上的包都是从这里生成的产物。

---

## License

[MIT](LICENSE)
