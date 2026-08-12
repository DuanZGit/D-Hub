# d-hub API 协议

## 基础

- 基础 URL：`http://192.168.5.242:10101`
- 请求格式：JSON
- 响应格式：JSON
- 认证：新安装默认启用 API key。除 `/`、`/ui`、`/health` 和 API 文档外，
  使用 `Authorization: Bearer <DHUB_API_KEY>` 或 `X-API-Key` 请求头。

```bash
export DHUB_API_KEY="<安装脚本输出的密钥>"
curl -H "Authorization: Bearer $DHUB_API_KEY" http://192.168.5.242:10101/agents
```

## 1. Agent 注册

### POST /register

```json
{
  "agent_id": "minis",
  "host": "192.168.5.101",
  "tools": ["memory", "wiki", "mcp", "files", "skills"],
  "projects": ["project-a", "project-b"]
}
```

```json
{"status":"ok","agent_id":"minis","registered_at":"2026-08-12T01:00:00Z"}
```

## 2. MCP 路由

### POST /mcp/tools/list

列出 agent 可见的 MCP 工具（三层合并后）。

**请求**：
```json
{
  "agent_id": "minis",
  "project": "project-a"
}
```

**响应**：
```json
{
  "tools": [
    {"name": "rmcp__memory__memory_search", "description": "搜索记忆", ...},
    {"name": "rmcp__wiki__wiki_search", "description": "搜索 Wiki", ...},
    {"name": "rmcp__review__code_review", "description": "代码审查（来自 project 层）", ...}
  ]
}
```

### POST /mcp/tools/call

调用 MCP 工具。

**请求**：
```json
{
  "agent_id": "minis",
  "project": "project-a",
  "name": "rmcp__memory__memory_search",
  "arguments": {"query": "最近的项目决策", "limit": 5}
}
```

**响应**：
```json
{
  "result": {"content": [{"type": "text", "text": "..."}]}
}
```

## 3. 记忆

### POST /memory/add

```json
{
  "namespace": "projects/project-a",
  "agent_id": "minis",
  "content": "决定使用 PostgreSQL 作为主数据库",
  "metadata": {"type": "decision"}
}
```

```json
{"status":"ok","id":"mem_123"}
```

### POST /memory/search

```json
{
  "namespace": "projects/project-a",
  "agent_id": "minis",
  "query": "数据库选型",
  "limit": 10
}
```

```json
{"results": [
  {"id":"mem_123","content":"决定使用 PostgreSQL...","score":0.95,"created_at":"..."}
]}
```

## 4. Wiki

### POST /wiki/page

```json
{
  "namespace": "projects/project-a",
  "title": "架构决策",
  "content": "# 数据库选型\n\n决定使用 PostgreSQL..."
}
```

```json
{"status":"ok","path":"/wiki/projects/project-a/架构决策.md"}
```

### GET /wiki/page

```
GET /wiki/page?namespace=projects/project-a&title=架构决策
```

### GET /wiki/search

```
GET /wiki/search?namespace=projects/project-a&q=database
```

## 5. 技能

### GET /skills

```
GET /skills?agent_id=minis&project=project-a
```

**响应**：三层合并后的技能列表。

### GET /skills/{name}

获取技能内容。

## 6. 文件

### GET /files/list

```
GET /files/list?namespace=projects/project-a
```

### POST /files/upload

multipart/form-data

### GET /files/download

```
GET /files/download?namespace=projects/project-a&file=meeting-notes.md
```

## 7. Agent 互相调用

### POST /agent/{agent_id}/call

```json
{
  "method": "memory.query",
  "params": {"query": "最近的项目", "namespace": "projects/project-a"}
}
```

```json
{"result":{"answer":"...","source_agent":"minis"}}
```

## 8. 系统

### GET /health

```json
{"status":"ok","version":"0.1.0","uptime":"1h23m"}
```

### GET /agents

列出已注册 agent。

### POST /sync/trigger

手动触发同步。

## 错误码

| 状态码 | 说明 |
|---|---|
| 200 | 成功 |
| 400 | 参数错误 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 冲突（文件锁） |
| 500 | 服务器错误 |
