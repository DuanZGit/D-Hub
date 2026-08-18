# 跨电脑 Agent Connector API（v1）

D-Hub 作为中心协调层，让不同电脑上的 DSH 通过各自的插件**主动出站**连接同一个
D-Hub，无需任何入站端口暴露。本页记录 Connector 服务端 API。

## 1. 通信拓扑

```text
DSH Plugin A ─┐
              ├── outbound HTTPS/私有网络 → D-Hub
DSH Plugin B ─┘
```

- DSH 客户端只需要主动出站连接 D-Hub。
- D-Hub 不接受 DSH 反向入站连接。
- 所有 endpoint / TLS / proxy / VPN / 端口均通过配置表达，不硬编码。

## 2. 身份与 scoped token

每个 Connector Agent 在创建时获得**一次性 scoped token**：

- token 只在 register 时返回一次；
- 服务端只保存 token 的 SHA-256 hash（不可逆）；
- token 绑定 namespace / project / capability；
- 可通过重新 register（覆盖）或 unregister 撤销；
- token 不写入源码，也不写入示例配置真实值。

创建 Connector Agent（需要 admin key）：

```bash
curl -X POST http://<dhub>/v1/connector/register \
  -H "Authorization: Bearer $DHUB_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "machine-a",
    "agent_name": "work-laptop",
    "owner": "alice",
    "namespace": "global",
    "project": "project-a",
    "capabilities": ["memory", "task", "wiki"]
  }'
```

响应（token 仅此一次）：

```json
{
  "status": "ok",
  "agent_id": "machine-a",
  "token": "<one-time scoped token>"
}
```

之后所有数据面请求都用该 token 认证：

```bash
export DHUB_AGENT_TOKEN="<token>"
```

## 3. 数据面端点

除 `register` / `status`（admin）外，数据面端点用 scoped token 认证。

### 3.1 心跳 `POST /v1/connector/heartbeat`

```json
{"agent_id": "machine-a", "status": "online"}
```

### 3.2 拉取 `POST /v1/connector/poll`

```json
{"agent_id": "machine-a", "project": "project-a", "limit": 10}
```

返回待处理且未 ack 的消息（含 TTL 过期检查）。

### 3.3 确认 `POST /v1/connector/ack`

```json
{"agent_id": "machine-a", "message_id": "<mid>"}
```

### 3.4 发送 `POST /v1/connector/send`

只允许**结构化消息 / 结构化任务描述**，禁止任意 shell / 任意程序执行字段。

```json
{
  "sender_agent_id": "machine-a",
  "recipient_agent_id": "machine-b",
  "type": "task",
  "namespace": "global",
  "project_id": "project-a",
  "payload": {"command": "summarize", "inputs": [...]},
  "idempotency_key": "unique-key",
  "required_capability": "task",
  "requires_user_approval": true
}
```

message envelope 至少包含：

```text
id / type / sender_agent_id / recipient_agent_id 或 recipient_scope
namespace / project_id / session_id / created_at / expires_at
idempotency_key / payload / required_capability / requires_user_approval
```

### 3.5 状态 `GET /v1/connector/status`（admin）

```bash
curl -H "Authorization: Bearer $DHUB_ADMIN_KEY" \
  http://<dhub>/v1/connector/status
```

返回 agents（含 last_seen / status）、pending 队列数、dead-letter 数。

### 3.6 注销 `POST /v1/connector/unregister`

```json
{"agent_id": "machine-a"}   # 需 machine-a 的 token
```

## 4. 队列与可靠性

- 持久化队列（JSON 文件），重启可恢复；
- register / heartbeat / poll / ack；
- 有限重试 + TTL；
- 幂等（idempotency_key 去重，同一消息不会因重复 poll 被重复执行）；
- 离线补投（agent 上线后 poll 到离线期间的消息）；
- dead-letter（TTL 过期消息进入 dead 状态，可检查）；
- 审计事件（register / send / unregister 写入 audit log）。

## 5. 安全边界

- 不共用管理员 key；
- Agent 级身份 + scoped token；
- token 只显示一次、服务端只存 hash、可撤销轮换；
- token 绑定 namespace / project / capability；
- `send` 只允许结构化消息；
- 若未来要执行任务，必须作为 DSH 自己的用户审批和安全策略输入，
  不得由 D-Hub 绕过 DSH 执行。

## 6. 配置项

```env
DHUB_CONNECTOR_MAX_PAYLOAD=65536      # 单条消息 payload 上限（字节）
DHUB_CONNECTOR_MESSAGE_TTL=86400      # 消息 TTL（秒）
```
