# d-hub 交付包

> 本目录是 d-hub 项目的完整设计文档 + 参考资料包，供强模型直接实现。

## 一、架构文档（7 份 + 1 汇总）

| 文件 | 内容 |
|---|---|
| [README.md](minis://workspace/d-hub/README.md) | 项目概述、设计原则、架构图、数据流、端口规划 |
| [ARCHITECTURE.md](minis://workspace/d-hub/ARCHITECTURE.md) | 完整架构：模块职责、三级目录、Wiki 引擎、Dashboard 全功能、并发、安全、备份 |
| [NAMESPACE.md](minis://workspace/d-hub/NAMESPACE.md) | 三级命名空间设计（global/agents/projects） |
| [PROTOCOLS.md](minis://workspace/d-hub/PROTOCOLS.md) | 全部 API 接口定义 |
| [DEPLOYMENT.md](minis://workspace/d-hub/DEPLOYMENT.md) | 部署步骤（PostgreSQL + mem0ai + d-hub + cron） |
| [CLIENTS.md](minis://workspace/d-hub/CLIENTS.md) | 各 Agent 接入配置 |
| [BACKUP.md](minis://workspace/d-hub/BACKUP.md) | 备份与恢复 |
| [REFERENCES.md](minis://workspace/d-hub/REFERENCES.md) | **★ 实现参考汇总**：mem0 完整 API、mcp-switch 架构、PI-agent-wiki 语义编译、关键设计模式 |

## 二、开源源码参考（4 个仓库，已克隆）

```
references/
├── mem0/          # 10.7M — 记忆库完整源码（已精简，保留核心 + 示例）
├── mcp-switch/    # 1.4M — MCP 聚合网关源码（asashiki，MIT）
├── PI-agent-wiki/ # 795K — Wiki 引擎源码（ang-XWBWZ，LLM Wiki 模式）
└── pgvector/      # 1.8M — PostgreSQL 向量扩展源码
```

## 三、强模型实现时的关键要点

### 1. 总体架构（一句话）

**一个 FastAPI 进程（:10101）+ 一个 PostgreSQL（:5432），全包。**

### 2. 模块清单

| 模块 | 实现要点 | 参考 |
|---|---|---|
| MCP Router | 三层配置读时合并 + JSON-RPC 转发 + 上游工具缓存 2 分钟 | mcp-switch 的 registry/remote-mcp.ts + tools.ts |
| Memory | 直接 `import mem0`，`Memory.from_config()` 配 New-API + pgvector | mem0 的 configs + memory/main.py |
| Wiki | Markdown 文件 CRUD + whoosh 全文搜索 + git 版本控制 | PI-agent-wiki 的 search.ts + semantic-compiler.ts |
| Skills | 三层目录读写，读时合并 | NAMESPACE.md |
| Files | 三层目录读写 | NAMESPACE.md |
| Agent Registry | JSON 文件存储 | PROTOCOLS.md |
| Agent Call | 注册表 → HTTP 转发 | PROTOCOLS.md |
| Dashboard | 全功能 UI，复用同一套 REST API | mcp-switch 的 console/api.ts 路由清单 |
| Sync | 仅记忆↔Wiki 语义同步（cron 每 4h），MCP/Skills 无需同步 | REFERENCES.md §5.3 |

### 3. mem0 配置（New-API 兼容）

```python
config = {
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "dbname": "mem0", "collection_name": "mem0",
            "embedding_model_dims": 1536,  # 与 embedder 一致
            "user": "mem0", "password": "...",
            "host": "localhost", "port": 5432,
            "hnsw": True
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "<New-API 上的模型>", "temperature": 0.1,
            "api_key": "<New-API key>",
            "openai_base_url": "http://localhost:3000/v1"
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small", "embedding_dims": 1536,
            "api_key": "<New-API key>",
            "openai_base_url": "http://localhost:3000/v1"
        }
    }
}
memory = Memory.from_config(config)
```

**mem0 方法坑**：
- `search()` / `get_all()` 不接受顶层 user_id，必须 `filters={"user_id": "..."}`
- `add()` 接受顶层 user_id/agent_id/run_id
- `infer=True`（默认）时 LLM 提取事实；`infer=False` 原样存

### 4. 三级命名空间（记忆）

| 命名空间 | mem0 user_id |
|---|---|
| 共识层 | `global:shared` |
| Agent 层 | `global:<agent_id>` |
| Project 层 | `global:<agent_id>:<project_id>` |

### 5. 端口

| 服务 | 端口 | 访问 |
|---|---|---|
| d-hub | **10101** | 局域网 |
| PostgreSQL | 5432 | 仅 localhost |
| New-API | 3000 | 已有 |

### 6. 待确认（实现前问用户）

1. New-API 上可用的 **embedding 模型**和**LLM 模型**？（决定 embedding_dims 和 model 名）
2. 用户已有 wiki 数据的迁移路径
3. 是否需要 OAuth（mcp-switch 有完整参考，d-hub 局域网阶段可不做）
