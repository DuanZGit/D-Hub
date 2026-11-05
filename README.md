# DHub

自制 agent skill、插件与扩展的合集仓库。集中放、集中维护，不再散在各处。

## 目录

| 目录 | 内容 | 本机落地位置 |
|---|---|---|
| `extensions/` | pi 扩展（TypeScript） | `~/.pi/agent/extensions/<name>/` |
| `plugins/` | 独立命令行 / 集成插件 | 见各自 README |
| `skills/` | 自制 agent skill（`SKILL.md`） | `~/.pi/agent/skills/<name>/` |

## extensions

| 扩展 | 作用 | 触发点 |
|---|---|---|
| [auto-name](extensions/auto-name/) | 会话第一条消息即自动命名，让 PWA 通知能显示「是哪个会话」完成了 | `agent_start` |
| [pi-web-patch-keeper](extensions/pi-web-patch-keeper/) | pi-web 升级覆盖本地补丁后自动重放，并提示重启生效 | 加载时 / `agent_start` |
| [d-split](extensions/d-split/) | 按切点把一个会话拆成两个独立会话，原会话不动 | 工具 `d_split` |
| [d-live](extensions/d-live/) | 把思考与工具调用改写成「内心独白」，经本地 SSE 推到 pi-web 顶部浮层 | `thinking_delta` / `tool_execution_start` |
| [goal-guard](extensions/goal-guard/) | `/goal <一句话>` 把本会话目标钉进系统提示，防止跑偏 | 命令 `/goal` |
| [pi-cmd-guard](extensions/pi-cmd-guard/) | 拦截危险命令（`cat .env`、裸 `env`、`systemctl restart pi-web` 等） | `tool_call` |
| [skill-search](extensions/skill-search/) | 检索本机已装的全部技能，返回最匹配的 `SKILL.md` 路径 | 工具 `skill_search` |
| [skill-trigger](extensions/skill-trigger/) | 按任务内容自动匹配并触发对应技能 | 会话开始 |
| [sol-pi-stats](extensions/sol-pi-stats/) | 状态栏统计（token / 上下文用量） | UI 状态栏 |

## plugins

| 插件 | 作用 |
|---|---|
| [d-restart](plugins/d-restart/) | pi-web 安全重启：快照忙碌会话，服务就绪后自动续跑 |

## skills

| skill | 作用 |
|---|---|
| [ask-me](skills/ask-me/) | 怎么选技能：扫本机技能库，针对当前任务列出该用哪些，给 `SKILL.md` 路径 |
| [DK](skills/DK/) | 日常生活与家庭知识问答：做菜/营养/家电数码购物决策 |
| [gushen](skills/gushen/) | 股神：每日挂单 + 投研问答 |
| [show-me](skills/show-me/) | 解释形态阶梯：文字 → 图 → 交互页 → 自播放讲解页 |
| [teardown](skills/teardown/) | 把真实机械做成可拆解 3D 交互说明书，并录 60fps 视频 |
| [coffee-extraction](skills/coffee-extraction/) | 咖啡萃取追踪、设备标定与排障 |
| [ponytail](skills/ponytail/) | 最懒但能跑通的写码方案；变体 `-audit`/`-debt`/`-gain`/`-help`/`-review` 分别只审不改/清技术债/性能/用法/评审 |
| [lieflat-less-ai-tone](skills/lieflat-less-ai-tone/) | 去 AI 腔，按规则改写写作痕迹 |
| [svg-diagram](skills/svg-diagram/) | SVG 图解规范：技术感 + 中文字体友好 |
| [fireworks-tech-graph](skills/fireworks-tech-graph/) | 科技类图表生成 |
| [handoff](skills/handoff/) | 把当前会话压成交接文档给别的 agent |
| [trip-planner](skills/trip-planner/) | 国内多日游行程规划端到端 |
| [jianhao-travel-planner](skills/jianhao-travel-planner/) | 见好：出行路书工作流（通用版） |
| [magpie-quota](skills/magpie-quota/) | 查 AI 订阅 / 额度剩余与重置时间 |
| [magpie-setup](skills/magpie-setup/) | 把 magpie 配成用户想要的样子 |
| [ui-ux-pro-max](skills/ui-ux-pro-max/) | UI/UX 设计智能：网页 / 移动 / 桌面 |
| [taste](skills/taste/) | 反流水线前端审美：落地页 / 作品集 / 改版 |
| [travel-photo-abstraction](skills/travel-photo-abstraction/) | 旅行照片抽象化处理 |

## 安装

扩展（每个子目录对应 `~/.pi/agent/extensions/<name>/`）：

```bash
git clone https://github.com/DuanZGit/D-Hub /tmp/dhub
cp -r /tmp/dhub/extensions/auto-name ~/.pi/agent/extensions/
```

插件见各自目录的 README。

## 说明

- `skills/` 里的参考图、演示视频等大素材（单文件 >1.5MB）未入库，运行时按各 `SKILL.md` 的说明自备；`__pycache__`、生成产物同样剔除。
- 部分扩展依赖本机路径或约定（如 `pi-web-patch-keeper` 依赖 `~/.pi/agent/.cn-patches/apply.py`），按文件内注释调整。
- `pi-secret-mask`、`magpie.ts`、`d-reach`、`openviking` 不在此仓库：前两个含本地凭据或为第三方汉化副本，后两个各有独立来源。
- 旧内容（D-Hub 多 Agent 协调层 v0.4.0）已归档在 tag `archive/d-hub-v0.4.0`，随时可取回。

## License

MIT
