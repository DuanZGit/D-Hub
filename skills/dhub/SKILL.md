---
name: dhub
description: "与 D-Hub 多 agent 协调层交互。当任务涉及读写共享记忆、查询/写入 wiki 知识库、读取会话转录、或把本机数据同步到 D-Hub 时使用。触发词：dhub、D-Hub、共享记忆、同步到云端、查之前 agent 的记忆/会话。"
---

# D-Hub 客户端速查

D-Hub 是统一的云协调层（记忆 + wiki + 会话 + 文件 + MCP）。本 skill 给**最小必要**的调用模板，避免反复试探 API 格式浪费 token。

## 核心原则（省 token）

1. **能走 MCP 就走 MCP**：如果本环境已连 D-Hub MCP（有 `dhub_*` 工具），直接调工具，不写 curl。
2. **环境变量已配好**：地址/鉴权/命名空间从环境变量读，别每次去翻文档找 key。
3. **一次调用完成**：不要先探测再调用，直接按模板发请求，出错看返回再调一次。

## 环境（一次性，从环境变量读）

| 变量 | 说明 | 默认 |
|---|---|---|
| `DHUB_URL` | D-Hub 地址 | `http://192.168.5.242:10101` |
| `DHUB_API_KEY` | 鉴权（Bearer） | 无 |
| `DHUB_NAMESPACE` | 命名空间 | `global` |
| `DHUB_AGENT_ID` | 本机 agent id | — |

鉴权：所有请求带 `Authorization: Bearer $DHUB_API_KEY`。**不要打印 key 明文。**

## 方式一：MCP 工具（优先，最省 token）

| 想做什么 | 调哪个工具 | 关键参数 |
|---|---|---|
| 写一条记忆 | `dhub_memory_add` | `content`（必填） |
| 搜记忆 | `dhub_memory_search` | `query`, `limit` |
| 查/写 wiki | `dhub_wiki_get` / `dhub_wiki_put` | `title`（+`content`） |
| 搜 wiki | `dhub_wiki_search` | `query` |
| 列/读会话 | `dhub_session_list` / `dhub_session_get` | `session_id` |
| 追加会话消息 | `dhub_session_append` | `session_id`, `messages` |

工具里的 `scope` 默认 `agent`（= 本 agent 命名空间），不要手动改。

## 方式二：REST（curl 兜底，无 MCP 时用）

模板统一用环境变量，复制后只改 `<...>` 部分。

### 写记忆

```bash
curl -sS -X POST "$DHUB_URL/memory/add" \
  -H "Authorization: Bearer $DHUB_API_KEY" -H "Content-Type: application/json" \
  -d '{"namespace":"'"$DHUB_NAMESPACE"'","agent_id":"'"$DHUB_AGENT_ID"'","content":"<内容>","infer":false}'
```

### 搜记忆

```bash
curl -sS -X POST "$DHUB_URL/memory/search" \
  -H "Authorization: Bearer $DHUB_API_KEY" -H "Content-Type: application/json" \
  -d '{"namespace":"'"$DHUB_NAMESPACE"'","agent_id":"'"$DHUB_AGENT_ID"'","query":"<关键词>","limit":10}'
```

### 写 wiki（Markdown）

```bash
curl -sS -X POST "$DHUB_URL/wiki/page" \
  -H "Authorization: Bearer $DHUB_API_KEY" -H "Content-Type: application/json" \
  -d '{"namespace":"'"$DHUB_NAMESPACE"'","title":"<页面名>","content":"<Markdown 内容>"}'
```

### 读 wiki

```bash
curl -sS -G "$DHUB_URL/wiki/page" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  --data-urlencode "namespace=$DHUB_NAMESPACE" --data-urlencode "title=<页面名>"
```

### 搜 wiki

```bash
curl -sS -G "$DHUB_URL/wiki/search" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  --data-urlencode "namespace=$DHUB_NAMESPACE" --data-urlencode "q=<关键词>"
```

### 列会话 / 读会话

```bash
curl -sS -G "$DHUB_URL/sessions" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  --data-urlencode "namespace=$DHUB_NAMESPACE"

curl -sS -G "$DHUB_URL/sessions/<session_id>" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  --data-urlencode "namespace=$DHUB_NAMESPACE"
```

## 会话同步（别手动做）

本机会话转录的同步由**原生插件自动完成**（Codex hooks / Pi extension / Claude Code hooks），会话结束自动 push，增量去重。**不要**在对话里手动逐条调 `dhub_session_append` 去同步本机会话——那是重复劳动且费 token。

只有用户明确要求"把当前对话存到 D-Hub"时，才手动调 `dhub_session_create` + `dhub_session_append` 一次。

## 命名空间约定

- `global` — 所有 agent 共享的共识
- `agents/<id>` — 单个 agent 专属
- `projects/<id>` — 单个项目专属

默认用 `agents/$DHUB_AGENT_ID`（写自己的），需要跨 agent 共享才用 `global`。

## 出错处理

- `401` → API key 不对，检查 `$DHUB_API_KEY`，不要重试。
- `404` → 资源不存在（session/wiki 未建），先创建再操作。
- `422` → 参数格式错，看返回的 `detail` 字段改参数。
