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

## 会话同步（分场景）

### 有原生插件的 agent（Codex / Pi / Claude Code）

本机会话转录由**原生插件自动完成**（Codex hooks / Pi extension / Claude Code hooks），会话结束自动 push，增量去重。**不要**在对话里手动逐条调 `dhub_session_append` 去同步本机会话——那是重复劳动且费 token。

只有用户明确要求"把当前对话存到 D-Hub"时，才手动调 `dhub_session_create` + `dhub_session_append` 一次。

### Minis（本机，无原生插件）

Minis 本机跑一次 `dhub-uploader --minis-sessions`，把全部资产原样推到云端：

```bash
cd /var/minis/workspace/d-hub
PYTHONPATH=src python3 -m dhub.uploader \
  --source minis --minis-sessions \
  --url "$DHUB_URL" \
  --api-key "$(cat /var/minis/workspace/d-hub/.dhub-admin-key)" \
  --namespace agents/minis --agent-id minis
```

**同步原则（存原始格式，不改写）**：上传器只做"搬运 + 补 `source=minis` 元数据"，不解析、不重构内容。Minis 的会话/记忆各自带原始字段原样传递。

## Minis 资产格式说明（跨 agent 读取时要注意）

Minis 同步上去的资产和其他 agent（Pi/Codex）**格式不同**，查询层按 `metadata` 区分，别当成同一 schema：

| 维度 | Minis（`source=minis`） | Pi / Codex |
|---|---|---|
| 会话消息 role | 仅 `user` / `assistant` | 含 `user`/`assistant`/`tool`/`system` |
| 工具调用 | **没有独立 tool 条目**，工具调用已折叠进 assistant 的叙述文本里（`format: legacy-narrative`） | 独立 `tool` 条目 |
| 每条消息字段 | `role` / `content` / `timestamp` + `metadata{message_id, format}` | 类似，`metadata` 无 message_id |

**关键**：读 Minis 会话时，遇 `metadata.format == "legacy-narrative"`，不要去找结构化 tool 条目——工具结果已内嵌在 assistant 的 `content` 文本里。查询语义要靠读整段叙述，不能按 role 过滤工具。

## 命名空间约定

- `global` — 所有 agent 共享的共识
- `agents/<id>` — 单个 agent 专属
- `projects/<id>` — 单个项目专属

默认用 `agents/$DHUB_AGENT_ID`（写自己的），需要跨 agent 共享才用 `global`。

## 出错处理

- `401` → API key 不对，检查 `$DHUB_API_KEY`，不要重试。
- `404` → 资源不存在（session/wiki 未建），先创建再操作。
- `422` → 参数格式错，看返回的 `detail` 字段改参数。

## 服务端配置速查（mem0 / LLM / embedding）

以下配置在 D-Hub 服务器（UG）的 `/opt/d-hub/config/dhub.env`，改完 `sudo systemctl restart dhub`。

### 当前生效配置（2026-08-13）

| 键 | 值 | 说明 |
|---|---|---|
| `NEW_API_BASE_URL` | `https://api.duanz.xin:1217/v1` | NewAPI 地址（**必须 https**，http 会 307 重定向） |
| `DHUB_EMBED_MODEL` | `siliconflow/Qwen/Qwen3-Embedding-8B` | embedding 模型（**必须带渠道前缀**，裸名 `Qwen/...` 在 NewAPI 上 model_not_found） |
| `DHUB_EMBED_DIMS` | `4096` | Qwen3-Embedding Matryoshka 支持 4096 维 |
| `DHUB_LLM_MODEL` | `stepfun/step-3.7-flash` | 语义同步 LLM |
| `DHUB_MEMORY_BACKEND` | `mem0` | 启用向量后端 |
| `NEW_API_KEY` | 环境变量 | 从 Minis 环境变量 `NEW_API_KEY` 读 |

### 已知坑（改配置前先看）

1. **NewAPI 需要模型映射**：NewAPI 上模型 ID 带渠道前缀（如 `siliconflow/Qwen/...`），转发给上游时**必须**在渠道里配好模型映射剥掉前缀，否则上游报 "Model does not exist"。
2. **HNSW 索引上限 2000 维**：Qwen3-Embedding-8B 输出 4096 维，pgvector 的 HNSW 索引会报 `column cannot have more than 2000 dimensions`。已在 `memory.py` 里把 `"hnsw": True` 改成 `False`（用 IVFFlat）。
3. **缺 PostgreSQL 驱动**：`pip install psycopg2-binary`。
4. **重启后验证**：`curl http://127.0.0.1:10101/health`，看 `memory_backend` 应为 `mem0`、`memory_error` 为 `null`。

### 验证语义搜索

```bash
# 写一条
curl -sS -X POST "$DHUB_URL/memory/add" -H "Authorization: Bearer $DHUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"namespace":"<ns>","agent_id":"<id>","content":"测试内容","infer":false}'
# 语义搜（搜近义词/相关概念也能命中）
curl -sS -X POST "$DHUB_URL/memory/search" -H "Authorization: Bearer $DHUB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"namespace":"<ns>","agent_id":"<id>","query":"<相关但不同的词>","limit":5}'
```

返回 `score` 是相似度，越接近 1 越相关。
