# D-Hub 插件

各 Agent 原生插件，实现**会话转录单向同步到云 D-Hub**（零安装、自动触发、增量去重）。

## 设计定位

D-Hub 的资产分三层：

| 层 | 通道 | 方向 | 触发 |
|---|---|---|---|
| 数据通道 | MCP（通用，已就绪） | 双向按需 | Agent 主动 |
| 会话同步 | **各 Agent 原生插件**（本目录） | 单向 push | 会话结束自动 |

插件解决 MCP 的局限——**被动**（Agent 不主动调工具就不同步）。插件挂在会话生命周期钩子上，会话一结束就自动把 transcript 推上去，不需要 Agent 主动操作。

## 为什么是"原生插件"而不是统一插件协议

各 Agent 的插件/扩展机制不通用：

| Agent | 机制 | 触发点 | 会话文件 |
|---|---|---|---|
| **Codex** | hooks（`~/.codex/hooks.json`） | `SessionEnd` | `rollout-*.jsonl` |
| **Pi** | TypeScript extension（`~/.pi/agent/extensions/`） | `session_shutdown` | `--<path>--/<ts>_<uuid>.jsonl` |
| Claude Code | hooks（`settings.json`） | `SessionEnd`/`Stop` | `~/.claude/projects/*/*.jsonl` |

唯一通用的只有 **MCP**（数据通道）和 **agentskills.io**（技能）。但会话自动同步需要"生命周期钩子"，各家钩子 API 不同，只能逐家写薄适配。

因此这里每个插件**只做一件事**：会话结束时读本地 JSONL → 解析消息 → POST 到 D-Hub。逻辑极薄、零依赖、各自用原生语言。

## 当前覆盖

| 插件 | 语言 | 依赖 | 触发点 |
|---|---|---|---|
| [codex/](codex/) | Python（标准库） | 无 | `SessionEnd`（async） |
| [pi/](pi/) | TypeScript（node 内置） | 无 | `session_shutdown` |

## 通用约定

所有插件遵循同一套环境变量和增量策略：

**环境变量**：

| 变量 | 说明 | 默认 |
|---|---|---|
| `DHUB_URL` | D-Hub 地址 | `http://127.0.0.1:10101` |
| `DHUB_API_KEY` | admin 或 agent key | 无 |
| `DHUB_NAMESPACE` | 目标命名空间 | `global` |
| `DHUB_AGENT_ID` | agent 标识 | 各插件默认值 |
| `DHUB_SYNC_STATE` | 状态文件路径 | 各插件默认值 |

**增量策略**（避免重复上传）：

- 会话文件按行号 offset 记录已上传位置
- 状态文件（JSON）持久化 `会话文件 → {session_id, offset}`
- 重跑/续传只传新增消息
- 删除状态文件 = 重新全量

**D-Hub REST 端点**（插件目标）：

- `POST /sessions` — 创建会话（namespace/title/cwd/agent_id/metadata）
- `POST /sessions/{id}/messages` — 追加消息（messages: [{role, content}]）

## 添加新 Agent 插件

复制最接近的一个，改两处：

1. 触发点（该 Agent 的钩子 API）
2. 会话文件解析（该 Agent 的 JSONL 格式）

消息统一规范化为 `{role: user|assistant|tool|system, content: string}` 后调 `/sessions/{id}/messages`。

---

## 跨设备 Agent Connector 插件（DSH）

[`dsh-dhub/`](dsh-dhub/) 是一个独立 Node 包，让 DSH 通过 D-Hub 获得跨设备共享记忆、
Wiki 与结构化 Agent 消息。它只**主动出站**连接 D-Hub，不要求 DSH 开放入站端口；
不把任意 shell 作为远程任务接口。安装与配置见
[`dsh-dhub/README.md`](dsh-dhub/README.md)。
