# Pi 插件：会话同步到 D-Hub

Pi（pi.dev coding agent）会话关闭时，自动把会话转录单向推送到 D-Hub。

## 原理

- 用 Pi 原生 **TypeScript extension** 机制，监听 `session_shutdown` 事件
- 事件触发后，通过 `ctx.sessionManager.getSessionFile()` 拿到当前会话的 JSONL 文件
- 解析出消息（role + content），增量上传到 D-Hub 的 `POST /sessions` + `POST /sessions/{id}/messages`
- 零依赖：只用 Node 内置模块 + Pi 自带的类型

## 安装

### 1. 拷贝文件

```bash
mkdir -p ~/.pi/agent/extensions
cp plugins/pi/dhub-sync.ts ~/.pi/agent/extensions/
```

### 2. 配置环境变量

```bash
export DHUB_URL="http://duanz.xin:47222"        # D-Hub 地址
export DHUB_API_KEY="<admin 或 agent key>"       # 鉴权
export DHUB_NAMESPACE="agents/pi"                # 目标命名空间
export DHUB_AGENT_ID="pi"                        # agent 标识
```

### 3. 重载扩展

启动 Pi 后执行 `/reload`，或在启动前已放置好文件则自动加载。

## 验证

结束一次 Pi 会话（退出或 `/new`）后，检查 D-Hub：

```bash
curl "http://<d-hub>:10101/sessions?namespace=agents/pi" \
  -H "Authorization: Bearer $DHUB_API_KEY"
```

## 增量与状态

- 状态文件 `~/.pi/agent/.dhub-sync.json` 记录每个 session 文件的远程 session id 和已上传行数
- 重跑/续传不会重复上传
- 删除状态文件会重新创建会话并全量上传

## 触发时机

`session_shutdown` 在以下场景触发（`event.reason`）：

| reason | 场景 |
|---|---|
| `quit` | 退出 Pi |
| `new` / `resume` | `/new` 或 `/resume` 切换会话 |
| `fork` | `/fork` 或 `/clone` |
| `reload` | `/reload` |

每次触发都会把当前会话文件的新增消息同步上去，天然覆盖所有会话结束/切换路径。

## 消息映射

Pi 的消息 role → D-Hub role：

| Pi role | D-Hub role |
|---|---|
| `user` | `user` |
| `assistant` | `assistant` |
| `toolResult` / `bashExecution` | `tool` |
| 其他（custom/branchSummary/compactionSummary） | `system` |

`assistant` 的 content 是块数组，只提取 `text` 和 `thinking` 块，丢弃 `toolCall` 块（工具调用本身由 `toolResult` 承载）。
