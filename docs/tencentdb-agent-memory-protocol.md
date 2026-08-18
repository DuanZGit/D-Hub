# TencentDB Agent Memory 协议确认与 Adapter 支持范围

> 本文档记录 d-hub 内置 `TencentAgentMemoryBackend` adapter 所依据的公开协议，
> 以及实际支持范围。协议来源为公开的
> `TencentCloud/TencentDB-Agent-Memory` 仓库（MemoryCore 网关 + `sdk/memory-core`）。

## 1. 依据的公开源码

- 仓库：`https://github.com/TencentCloud/TencentDB-Agent-Memory`
- 参考文件：
  - `MemoryCore/src/gateway/v2-router.ts`（v2/v3 数据面路由）
  - `MemoryCore/src/core/tools/conversation-search.ts`（L0 搜索结果结构）
  - `sdk/memory-core/python/tencentdb_agent_memory/v3/client.py`（v3 客户端）
  - `sdk/memory-core/python/tencentdb_agent_memory/_v3_http.py`（v3 传输）

## 2. 当前稳定 API 版本

- Adapter 默认使用 **v3** 数据面协议（`/v3/...`）。
- 通过配置项 `DHUB_AGENT_MEMORY_API_VERSION` 可切换路径前缀（例如 `v2`）。
- 支持范围：L0 Conversation（add/search/query/delete/count）与 L1 Atomic
  （update）。L2/L3 场景与离线文件（offload / read_file）不在本 adapter 范围内，
  这些接口在公开 SDK 中继续走 v2。

## 3. 认证方式

- `Authorization: Bearer <api_key>`
- `x-tdai-service-id: <service_id>`（内存实例 ID）
- 可选 `x-tdai-user-key`（系统管理员类接口才需要，本 adapter 不启用）

## 4. 隔离与映射

d-hub 的 namespace（`global` / `agents/<id>` / `projects/<id>`）映射为：

```text
team_id   <- DHUB_AGENT_MEMORY_TEAM_ID  （默认 "default"）
agent_id  <- MemoryRecord.agent_id       （默认 "shared"）
user_id   <- DHUB_AGENT_MEMORY_USER_ID   （默认 "shared"）
session_id<- DHUB_AGENT_MEMORY_NAMESPACE 或 d-hub namespace
```

## 5. 响应封装

```json
{"code": 0, "message": "", "data": {...}, "request_id": "..."}
```

- `code == 0` 表示成功；`data` 为业务数据。
- `code != 0` 或 HTTP 4xx/5xx 视为错误；错误携带 `request_id`，
  响应头含 `x-qcloud-transaction-id` / `x-trace-id`。

## 6. 主要端点

| 操作 | 方法与路径 | 关键请求字段 | 关键响应字段 |
|---|---|---|---|
| add | `POST /v3/conversation/add` | `messages`, `session_id` | `accepted_ids` |
| search | `POST /v3/conversation/search` | `query`, `limit`, `session_id` | `results[]` |
| query | `POST /v3/conversation/query` | `limit`, `offset`, `session_id` | `messages[]`, `total` |
| delete | `POST /v3/conversation/delete` | `message_ids`, `session_ids` | `deleted` |
| update | `POST /v3/atomic/update` | `id`, `content` | `id` |
| count | `POST /v3/conversation/count` | `session_id` | `total` |

搜索结果条目：

```json
{"id","session_key","session_id","user_id","agent_id","role","content","score","recorded_at"}
```

## 7. Adapter 行为（resilience）

- 请求级超时：`DHUB_AGENT_MEMORY_TIMEOUT_MS`（默认 5000ms）
- 有界重试：`DHUB_AGENT_MEMORY_RETRIES`（默认 2），指数退避
- 认证失败（401/403）不重试
- 429 / 5xx / 网络错误 / 超时才重试
- 熔断：连续失败达到阈值后短暂打开（`_CircuitBreaker`）
- 幂等：写入带 `request_id`；响应归一化为 `MemoryRecord`
- secret 脱敏：日志仅记录非敏感 endpoint、状态码与 request_id，
  绝不记录 Authorization / API key / 完整敏感 payload

## 8. 支持范围声明

- 支持 API 版本：**v3（默认）、v2（通过配置切换）**
- 未配置 `DHUB_AGENT_MEMORY_URL` / `DHUB_AGENT_MEMORY_API_KEY` 时，
  backend 健康检查返回 `ok=False`，不影响 d-hub 启动；Mem0/JSON 模式仍可用。
- 真实腾讯服务 E2E：**NOT VERIFIED**（无测试凭据）。本地仅使用 fake server
  contract test（见 `tests/test_tencent_backend.py`）。

## 9. 配置项

见 `.env.example`：

```env
DHUB_AGENT_MEMORY_URL=
DHUB_AGENT_MEMORY_API_KEY=
DHUB_AGENT_MEMORY_SERVICE_ID=
DHUB_AGENT_MEMORY_API_VERSION=v3
DHUB_AGENT_MEMORY_TIMEOUT_MS=5000
DHUB_AGENT_MEMORY_RETRIES=2
DHUB_AGENT_MEMORY_NAMESPACE=
DHUB_AGENT_MEMORY_TEAM_ID=
DHUB_AGENT_MEMORY_USER_ID=
```
