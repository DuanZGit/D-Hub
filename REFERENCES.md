# d-hub 实现参考资料汇总

> 本文件为强模型实现 d-hub 时的完整参考资料。所有代码片段均来自已克隆到
> `/var/minis/workspace/d-hub/references/` 的真实开源项目源码，可直接参照。

---

## 目录

1. [mem0 完整 API（来自源码）](#1-mem0-完整-api)
2. [mcp-switch 完整架构（MCP 聚合参考）](#2-mcp-switch-mcp-聚合参考)
3. [PI-agent-wiki（Wiki 引擎参考）](#3-pi-agent-wiki-wiki-引擎参考)
4. [pgvector 安装](#4-pgvector-安装)
5. [关键设计模式提炼](#5-关键设计模式提炼)

---

## 1. mem0 完整 API

源码位置：`references/mem0/`（v2.0.17，最新 pip 版）

### 1.1 核心配置（from_config 字典格式）

**LLM provider 支持**：openai, anthropic, ollama, deepseek, gemini, vllm, lmstudio, xai, minimax, groq, together, aws_bedrock, litellm, azure_openai, langchain

**Embedder provider 支持**：openai, ollama, huggingface, azure_openai, gemini, vertexai, together, lmstudio, langchain, aws_bedrock, fastembed

**Vector store provider**：pgvector, qdrant, chroma, faiss, milvus, pinecone, weaviate, opensearch, redis, azure_ai_search, singlestore, etc.

### 1.2 完整配置示例（New-API + pgvector）

```python
from mem0 import Memory

config = {
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "dbname": "mem0",
            "collection_name": "mem0",          # 默认表名，可改
            "embedding_model_dims": 1536,        # 必须与 embedder 维度一致
            "user": "mem0",
            "password": "xxx",
            "host": "localhost",
            "port": 5432,
            "hnsw": True,                        # HNSW 索引加速
            "diskann": False,
            "minconn": 1,
            "maxconn": 5,
            # 也可以用 connection_string 替代单个参数：
            # "connection_string": "postgresql://mem0:xxx@localhost:5432/mem0"
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o",
            "temperature": 0.1,
            "max_tokens": 2000,
            "api_key": "$NEW_API_KEY",           # New-API 的 key
            "openai_base_url": "http://localhost:3000/v1"  # New-API 地址！
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small",
            "embedding_dims": 1536,
            "api_key": "$NEW_API_KEY",
            "openai_base_url": "http://localhost:3000/v1"  # New-API 地址！
        }
    },
    "history_db_path": "/opt/d-hub/data/mem0.db",  # SQLite 历史记录
}

memory = Memory.from_config(config)
```

**关键**：mem0 的 LLM 和 Embedder 都支持 `openai_base_url` 参数，直接指向任何
OpenAI 兼容端点（New-API 就是 OpenAI 兼容的）。embedder 配置里
`embedding_dims` 可选——不传则 API 不给 `dimensions` 参数（兼容 vLLM 等），
默认 1536。

### 1.3 Memory 类方法签名（v2.0.17 实际签名）

```python
# 添加记忆。messages 可以是 str / dict / list[dict]
# infer=True（默认）时 LLM 提取事实并决定 add/update/delete
# infer=False 时原样存入
def add(
    self,
    messages,                        # str 或 [{"role": "user", "content": "..."}]
    *,
    user_id=None, agent_id=None, run_id=None,
    metadata=None,                   # dict，随记忆存储
    timestamp=None,                  # OSS 不支持，会抛错
    expiration_date=None,            # "YYYY-MM-DD"，过期记忆默认隐藏
    infer=True,
    memory_type=None,                # 仅 "procedural_memory" 特殊
    prompt=None,
)
# 返回: {"results": [{"id": "...", "memory": "...", "event": "ADD"|"UPDATE"|"DELETE"}]}

# 搜索记忆（注意：用 filters，不接受顶层 user_id！）
def search(
    self,
    query: str,
    *,
    top_k: int = 20,
    filters: dict = None,            # 必须含 user_id/agent_id/run_id 至少一个
    threshold: float = 0.1,          # 最小相似度
    rerank: bool = False,
    explain: bool = False,
)
# 返回: {"results": [{"id": "...", "memory": "...", "score": 0.8, "metadata": {...}, "created_at": "...", "updated_at": "..."}]}

# 列出记忆
def get_all(self, *, filters: dict = None, top_k: int = 20, show_expired: bool = False)
# 返回: {"results": [...]}

# 按 id 获取单条
def get(self, memory_id)

# 删除
def delete(self, memory_id)
def delete_all(self, user_id=None, agent_id=None, run_id=None)
```

**注意**：
- `search`/`get_all` 的 filters **必须**含 user_id/agent_id/run_id 至少一个，否则 ValueError
- filters 支持元数据操作符：`{"key": "value"}` 精确、`{"key": {"gt": 10}}` 比较、
  `{"key": {"contains": "text"}}`、`{"key": {"in": [...]}}`、`{"$or": [...]}` 等
- 传顶层 user_id 给 search/get_all 会报错，必须用 filters 字典

### 1.4 pgvector 自动建表（mem0 内部 SQL）

mem0 首次使用时自动执行（无需手动建表）：

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS mem0 (
    id UUID PRIMARY KEY,
    vector vector(1536),           -- 维度=embedding_model_dims
    payload JSONB                  -- 存 user_id/agent_id/metadata/文本等
);

CREATE INDEX IF NOT EXISTS mem0_hnsw_idx ON mem0
    USING hnsw (vector vector_cosine_ops);   -- HNSW 余弦索引

CREATE INDEX IF NOT EXISTS mem0_text_lemmatized_idx ON mem0
    USING gin(to_tsvector('simple', payload->>'text_lemmatized'));  -- 全文索引
```

---

## 2. mcp-switch（MCP 聚合参考）

源码位置：`references/mcp-switch/`（asashiki/mcp-switch，MIT）

### 2.1 架构模式（值得照抄的核心）

```
单服务（Fastify，:4577）+ console SPA
  ├── StreamableHTTPServerTransport（MCP 传输层）
  ├── RemoteMcpRegistry（连接上游 MCP server，进程内）
  │     ├── stdio: 拉起子进程（npx/uvx/命令），stdin/stdout 通信
  │     └── http: StreamableHTTPClientTransport 连接远程 URL
  ├── AuthStore（SQLite：agents/OAuth/audit/skill_registry/remote_servers）
  └── Console API（/api/console/* 管理接口）+ SPA（/console）
```

**关键设计**：MCP Switch 不内置任何工具，所有工具都是代理上游。每次请求
`tools/list` 时动态从上游拉取，缓存 2 分钟（`cacheTtlMs: 2*60*1000`）。

### 2.2 SQLite 表结构（AuthStore，可直接照抄）

```sql
-- Agent 表
CREATE TABLE agents (
  agent_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  secret_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  last_authorized_at TEXT,
  last_used_at TEXT
);

-- 审计日志（每次工具调用记录一行）
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  agent_id TEXT,
  client_id TEXT,
  tool_name TEXT,
  action TEXT NOT NULL,
  success INTEGER NOT NULL,
  latency_ms INTEGER,
  detail TEXT
);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_agent ON audit_log(agent_id, created_at DESC);

-- 技能注册表（mcp-switch 把上游工具注册成 skill，带 enabled 开关）
CREATE TABLE skill_registry (
  skill_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'local',
  enabled INTEGER NOT NULL DEFAULT 1,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  remote_meta TEXT,       -- JSON: {serverId, toolName, inputSchema, readOnly}
  allow_write INTEGER NOT NULL DEFAULT 0,
  read_only INTEGER
);

-- Agent 可见性（per-agent 工具开关）
CREATE TABLE skill_visibility (
  agent_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  visible INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (agent_id, skill_id)
);

-- 上游 MCP server 注册表
CREATE TABLE remote_servers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,              -- http 存 URL；stdio 存 "stdio://command args"
  description TEXT NOT NULL,
  bearer_token_env TEXT,
  bearer_token TEXT,
  headers_json TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 2.3 工具名命名（可复用）

上游工具在 mcp-switch 中重命名为：`rmcp__<server_id>__<tool_name>`

### 2.4 Console API 路由（Dashboard 参考）

```
POST /api/console/login          # 登录
GET  /api/console/me             # 当前用户
POST /api/console/logout         # 登出
GET  /api/console/skills         # 技能列表
POST /api/console/skills/:id/enabled      # 启用/禁用
POST /api/console/skills/reorder         # 排序
POST /api/console/skills/:id/allow-write # 允许写
GET  /api/console/agents         # agent 列表
POST /api/console/agents         # 创建 agent
POST /api/console/agents/:id/regen       # 重新生成 token
DELETE /api/console/agents/:id   # 删除
POST /api/console/agents/:id/enabled     # 启用/禁用
GET  /api/console/agents/:id/visibility  # 工具可见性
POST /api/console/agents/:id/visibility  # 设置可见性
GET  /api/console/audit          # 审计日志（过滤/分页）
GET  /api/console/remote         # 上游服务器列表
POST /api/console/remote         # 添加上游服务器
POST /api/console/remote/:id/oauth/start # OAuth 授权
POST /api/console/remote/rediscover      # 重新发现工具
GET  /api/console/stats          # 统计
DELETE /api/console/remote/:id   # 删除上游服务器
```

### 2.5 工具调用转发（JSON-RPC 透传核心）

```typescript
// tools/call 时：查 skill_registry → 找到 serverId → 转发给上游
// 返回值透传 content/structuredContent/isError/_meta
```

**JSON Schema → Zod 类型转换**：mcp-switch 有完整的 jsonSchemaToZod 转换逻辑
（处理 string→number 的强转，因为很多 MCP 客户端会把参数序列化成字符串）。
d-hub 用 Python 实现时可以参考：把上游工具的 JSON Schema 转成 Python 的
pydantic 模型做参数校验和类型强转。

---

## 3. PI-agent-wiki（Wiki 引擎参考）

源码位置：`references/PI-agent-wiki/`（ang-XWBWZ，本地 Markdown 语义知识库）

### 3.1 核心理念（Karpathy LLM Wiki 模式）

LLM 充当"知识库管理员"，持续编译维护结构化 Markdown Wiki。摄入文档时
预编译知识（提取 concepts/aliases），形成持久化、可复利增长的知识库。
不是 RAG（每次查询重新检索），而是预编译（查询时直接命中结构化知识）。

### 3.2 数据模型（types.ts）

```typescript
// 文件条目
interface FileEntry {
  title: string;          // 从第一个 # 标题提取
  tags: string[];         // frontmatter tags
  sourceDir: string;
  relPath: string;
  mtime: string;
}

// 块编译元数据（LLM 填充）
interface ChunkInfo {
  heading: string; level: number;
  topic?: string;         // 核心主题
  summary?: string;       // 一句话摘要
  concepts?: string[];    // 核心概念
  entities?: string[];    // 实体
  aliases?: string[];     // 同义表达（中英对照）
  keywords?: string[];
  normalizedText?: string; // 规范化文本
  chunkType?: string;      // concept|note|code|reference|decision|...
  importance?: number;     // 0-1
  confidence?: number;     // 0-1
}

// 向量存储
interface EmbeddingData {
  model: string; dim: number;
  entries: Record<string, number[]>;  // key: relPath###N
  chunkInfo?: Record<string, ChunkInfo>;
  centroid?: number[];    // 全局质心（降噪）
}
```

### 3.3 manifest.json（文件追踪，防重复索引）

```json
{
  "version": 1,
  "files": {
    "relPath.md": {
      "md5": "...",           // 文件哈希，变了就要重新索引
      "fileSize": 1234,
      "astChunkCount": 5,
      "astIndexedAt": "ISO",
      "llmCompiled": true,
      "llmCompiledAt": "ISO",
      "compilingSince": "ISO",  // 正在编译中（防并发）
      "hasSemanticVectors": true
    }
  }
}
```

### 3.4 关键词搜索（加权打分，可直接照抄）

```typescript
// search.ts 核心逻辑
// 标题匹配 +10 分
// 路径匹配 +5 分
// 标签匹配 +3 分
// 内容首次命中 +1 分，多次出现再 +min(count-1, 9) 分
// 结果按分数降序
// 返回行级上下文（匹配行 ±1 行）
```

### 3.5 语义编译 prompt（LLM 提炼，可直接照抄）

```text
你是一个"知识语义编译器"。
你的任务不是总结内容。你的任务是：
将人类随手记录的非结构化笔记，转换为适合机器语义索引、
概念检索、知识聚类、长期演化的"认知知识单元"。

核心原则：
1. 保留原始信息 — 不删技术细节
2. 不改变原意 — 只规范化表达
3. 补全隐式表达 — 补充省略的主语、展开缩写
4. 统一术语 — 将同义表达归一
5. 提取核心概念 — 识别技术关键词
6. 保持单主题 — 一个 chunk 只描述一个认知主题
7. 输出结构化 JSON — 严格遵循 schema

禁止：过度总结 / 删除原文 / 改写逻辑 / 主观推断 / 引入不存在的信息

你的角色是："语义标准化器"，不是"内容作者"。
```

输出 JSON：`{topic, normalizedText, concepts, aliases}`

### 3.6 搜索策略（MCP 工具 prompt 指导）

```
BEFORE searching, decompose the user's query:
  • 缩写展开为全名
  • 中英互译
  • 复合词拆分
  • 领域同义词
PREFER keyword mode。semantic 模式只在模糊自然语言意图时用。
```

### 3.7 Markdown 纯文本提取（去标记）

```typescript
// 去 frontmatter → 去 # 标题 → 去 **__*_`~~ → 去 [text](url) → 去列表符号 → 合并换行
const plain = body
  .replace(/^#{1,6}\s+/gm, "")
  .replace(/\*\*|__|\*|_|`|~~/g, "")
  .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
  .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
  .replace(/^\s*[-*+]\s+/gm, "")
  .replace(/^\s*\d+\.\s+/gm, "")
  .replace(/\n{2,}/g, " ")
```

---

## 4. pgvector 安装

源码位置：`references/pgvector/`（v0.8.6）

```bash
# Ubuntu 24.04 两种方式：
# 方式1：APT（如果仓库有匹配版本）
sudo apt install postgresql-17 postgresql-17-pgvector  # 版本号按实际

# 方式2：源码编译（通用）
cd /tmp
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# 启用扩展（每个数据库一次）
sudo -u postgres psql -c "CREATE EXTENSION vector;"
```

**注意**：pgvector 版本必须与 PostgreSQL 主版本匹配。编译需要
`postgresql-server-dev-<ver>`。

---

## 5. 关键设计模式提炼

### 5.1 MCP 聚合（d-hub 的 /mcp 模块）

```
tools/list 流程：
  1. 读三层 MCP 配置（global/agents/projects）合并
  2. 对每个启用的上游 server，连接并拉取工具列表（缓存 2 分钟）
  3. 工具重命名：rmcp__<server>__<tool>
  4. 返回合并工具列表

tools/call 流程：
  1. 从工具名解析出 server_id + tool_name
  2. 查配置拿到连接信息（http URL 或 stdio 命令）
  3. 转发调用（JSON-RPC 透传）
  4. 返回 content/structuredContent/isError
```

### 5.2 三级命名空间（d-hub 核心）

```
/opt/d-hub/{mcp,skills,wiki,files}/
├── global/          共识层：所有 agent 可见
├── agents/<id>/     Agent 层：仅该 agent
└── projects/<id>/   Project 层：项目成员

查找：project > agent > global，同名覆盖
实现：读时合并，每次请求实时扫目录（文件系统毫秒级，无需缓存）
```

### 5.3 记忆 ↔ Wiki 同步（唯一需要 cron 的）

```
每 4 小时：
  1. mem0.search(filters={"user_id": "global:shared"}, top_k=50)
  2. LLM 提炼成 Wiki 页面（参考 PI-agent-wiki 编译 prompt）
  3. 写入 /opt/d-hub/wiki/global/*.md
  4. git add + commit
冲突：flock 文件锁 + last-write-wins
```

### 5.4 技能/MCP 配置同步（不需要 cron）

```
文件变更立即生效：每次请求实时读目录合并。
无缓存、无 cron、无索引。
```

### 5.5 端口规划

| 服务 | 端口 | 访问 |
|---|---|---|
| d-hub | 10101 | 局域网 |
| PostgreSQL | 5432 | 仅 localhost |
| New-API | 3000 | 已有 |

---

## 6. 待确认事项

1. **New-API 地址**：`http://localhost:3000/v1`？是否有可用的 embedding 模型
   （text-embedding-3-small 或 bge-m3 等）？维度多少？
2. **mem0 的 LLM 模型**：New-API 上哪个模型给 mem0 用（事实提取、语义编译）？
3. **PI-agent-wiki 数据迁移**：用户已有的 wiki 内容在哪个目录？直接拷贝到
   /opt/d-hub/wiki/global/ 还是按 namespace 分配？
