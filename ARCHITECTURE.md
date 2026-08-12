# d-hub 架构文档（单进程版）

## 1. 模块职责

d-hub 一个进程包含以下模块：

| 模块 | 路由 | 说明 |
|---|---|---|
| **Agent Registry** | `POST /register` | Agent 注册表（JSON 文件） |
| **MCP Router** | `POST /mcp` | MCP 路由：三层合并 + JSON-RPC 转发 |
| **Memory** | `POST /memory/*` | 记忆：直接调用 mem0ai 库 |
| **Wiki** | `POST /wiki/*` | Wiki：Markdown CRUD + 全文搜索 |
| **Skills** | `GET/POST /skills/*` | 技能仓库：三级目录读写 |
| **Files** | `GET/POST /files/*` | 文件共享：三级目录读写 |
| **Agent Call** | `POST /agent/<id>/call` | Agent 互相调用：注册表 → 转发 |
| **Sync** | `POST /sync/trigger` | 同步触发：cron 定时调用 |
| **Dashboard** | `GET /ui` | Web 管理界面 |

## 2. 三级目录结构（MCP、Skills、Wiki、Files 统一）

```
/opt/d-hub/
├── mcp/                     # MCP 服务器配置
│   ├── global/              #   全局共享（所有 agent 可用）
│   │   ├── mem0-mcp.json    #     Mem0 的 MCP 接口
│   │   ├── wiki-mcp.json    #     Wiki 的 MCP 接口
│   │   └── files-mcp.json   #     文件共享的 MCP 接口
│   ├── agents/              # Agent 专属（覆盖 global）
│   │   └── minis/
│   │       └── custom-tool.json
│   └── projects/            # 项目专属（覆盖 agent + global）
│       └── project-a/
│           └── code-review.json
├── skills/                  # 技能仓库
│   ├── global/
│   │   └── agent-reach/SKILL.md
│   ├── agents/
│   └── projects/
├── wiki/                    # Wiki 页面（Markdown）
│   ├── global/
│   │   └── index.md
│   ├── agents/
│   └── projects/
└── files/                   # 共享文件
    ├── global/
    ├── agents/
    └── projects/
```

### MCP 配置文件格式

每个 MCP 配置是一个 JSON 文件：

```json
{
  "name": "mem0",
  "description": "记忆搜索服务",
  "transport": "http",
  "url": "http://localhost:8888/mcp",
  "headers": {
    "Authorization": "Bearer $MEM0_API_KEY"
  },
  "tools": [
    {
      "name": "memory_search",
      "description": "搜索记忆",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" },
          "limit": { "type": "number" }
        }
      }
    }
  ]
}
```

### 合并规则

```
Agent 请求 MCP 工具列表（tools/list）
  → 收集 project 层所有 MCP 配置
  → 收集 agent 层所有 MCP 配置
  → 收集 global 层所有 MCP 配置
  → 合并规则：
    - 同名 tool → project 覆盖 agent 覆盖 global
    - 不同名 tool → 全部合并
  → 返回合并后的工具列表

Agent 调用 MCP 工具（tools/call {name, args}）
  → d-hub 查合并后的配置表
  → 找到 tool 对应的 MCP server 地址
  → 转发 JSON-RPC 请求
  → 返回结果
```

## 3. 三级命名空间（记忆）

### 3.1 Mem0 user_id 映射

| d-hub 命名空间 | Mem0 user_id | 说明 |
|---|---|---|
| global:shared | global:shared | 共识层 |
| agents:minis | global:minis | Agent: minis |
| agents:claude-code | global:claude-code | Agent: claude-code |
| projects:project-a:minis | global:minis:project-a | Project: minis + project-a |

### 3.2 访问规则

| 层级 | 读 | 写 |
|---|---|---|
| global:shared | 所有 agent | 受控（仅 sync + 人工） |
| agents:<id> | 仅该 agent | 仅该 agent |
| projects:<id> | 项目成员 | 项目成员 |

## 4. Wiki 引擎

### 4.1 存储

- 每个 Wiki 页面是一个 Markdown 文件
- 路径对应命名空间：`/opt/d-hub/wiki/<namespace>/<title>.md`

### 4.2 全文搜索

- 使用 `whoosh` 或 `sqlite-utils` 建立全文索引
- 索引更新：写入页面时自动更新
- 索引重建：定时 cron 任务

### 4.3 隔离

- 按目录隔离
- 共识层：`/opt/d-hub/wiki/global/`
- Agent 层：`/opt/d-hub/wiki/agents/<id>/`
- Project 层：`/opt/d-hub/wiki/projects/<id>/`

## 5. 记忆 ↔ Wiki 同步

### 5.1 同步方向

```
共识层记忆（global:shared）
  ──→ 生成/更新 Wiki 共识页面
  ──→ 提取 Wiki 新增内容写回记忆
```

### 5.2 冲突处理

- 文件锁（flock）
- last-write-wins
- Dashboard 记录冲突日志，可人工审核

## 6. 配置合并（读时计算，无缓存无 cron）

MCP 和 Skills 的合并**不需要同步**——每次请求实时读目录：

```python
def merge_tiers(tier_type: str, agent_id: str, project: str):
    """读时合并：project > agent > global"""
    merged = {}
    # 从 global 开始（最低优先级）
    for f in Path(f"/opt/d-hub/{tier_type}/global").glob("*.json"):
        merged[f.stem] = json.load(f)
    # agent 覆盖
    for f in Path(f"/opt/d-hub/{tier_type}/agents/{agent_id}").glob("*.json"):
        merged[f.stem] = json.load(f)
    # project 覆盖（最高优先级）
    for f in Path(f"/opt/d-hub/{tier_type}/projects/{project}").glob("*.json"):
        merged[f.stem] = json.load(f)
    return merged
```

文件变更立即生效，无需任何同步机制。

### 唯一需要 cron 的：记忆 ↔ Wiki 语义同步

```
cron 每 4 小时：
  → 从 Mem0 共识层提取记忆
  → LLM 提炼成 Wiki 页面
  → 冲突用文件锁 + last-write-wins
```

## 7. 并发控制

| 资源 | 策略 |
|---|---|
| 记忆写入 | mem0ai 内部处理（PostgreSQL 行锁） |
| Wiki 写入 | 文件锁（flock） |
| MCP 配置写入 | 文件锁 + 原子替换 |
| Skills 写入 | 文件锁 + 原子替换 |
| 不同 namespace | 并行无冲突 |

## 8. Dashboard（全功能）

d-hub 内嵌 `/ui`，提供完整的可视化管理和操作界面。

### 功能模块

| 模块 | 路由 | 功能 |
|---|---|---|
| **总览** | `/ui/` | 系统状态、各模块健康、运行时长、请求量 |
| **Agent** | `/ui/agents` | 查看/添加/禁用 agent，编辑工具和项目权限 |
| **MCP** | `/ui/mcp` | 三层 MCP 配置可视化，添加/编辑/删除工具，查看合并结果 |
| **记忆** | `/ui/memory` | 按命名空间浏览记忆，手动添加/删除，搜索 |
| **Wiki** | `/ui/wiki` | 页面浏览/编辑/新建，Markdown 编辑器，搜索，版本历史 |
| **技能** | `/ui/skills` | 技能库浏览，三层覆盖视图，启用/禁用 |
| **文件** | `/ui/files` | 上传/下载/浏览/删除共享文件 |
| **同步** | `/ui/sync` | 查看记忆↔Wiki 同步历史，手动触发，冲突审核 |
| **日志** | `/ui/logs` | 请求日志、错误、审计、实时 tail |
| **配置** | `/ui/config` | 编辑 d-hub 配置（端口、密钥、agent 默认值） |
| **备份** | `/ui/backup` | 一键备份、恢复、备份历史列表 |

### 技术

- 前端：单页 HTML/JS（可内嵌 CDN 的 Vue/HTMX，或纯 JS）
- 数据：通过 d-hub 的 REST API 读写（与 agent 同一套 API）
- 认证：当前无（局域网），后续 JWT
- 路由：`/ui/*` 由 FastAPI 提供静态文件

### 与 agent API 的关系

Dashboard **复用同一套 REST API**，不额外建一套数据接口。代理 agent 的 API 是编程接口，Dashboard 是它的可视化前端。

```python
# FastAPI 挂载
app.mount("/ui", StaticFiles(directory="/opt/d-hub/dhub/ui", html=True), name="ui")
# 业务 API 照常提供，/ui/* 只是包装它们的页面
```

## 9. 安全

- 局域网：无认证（当前阶段）
- 后续公网：JWT + API key，每 agent 独立密钥
- mcp-switch 仅 localhost，不对外暴露
- PostgreSQL 仅 localhost，不对外暴露
- Dashboard 无认证（局域网内），后续可加密码

## 10. 恢复手册

### 10.1 完整恢复

```bash
# 1. 恢复 PostgreSQL
sudo -u postgres psql mem0 < mem0-backup.sql

# 2. 恢复文件目录
tar -xzf dhub-files-backup.tar.gz -C /

# 3. 重启 d-hub
sudo systemctl restart dhub
```

### 10.2 备份脚本

```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/opt/d-hub/backups/$DATE"
mkdir -p "$BACKUP_DIR"

# PostgreSQL
sudo -u postgres pg_dump mem0 > "$BACKUP_DIR/mem0.sql"

# 文件目录
tar -czf "$BACKUP_DIR/files.tar.gz" /opt/d-hub/{mcp,skills,wiki,files,config}

# 保留最近 7 天
find /opt/d-hub/backups/ -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
```

## 11. 开发优先级

| 阶段 | 内容 | 预计 |
|---|---|---|
| P0 | PostgreSQL + pgvector 安装 | 0.5 天 |
| P1 | FastAPI 框架 + 目录结构 + Agent Registry | 1 天 |
| P2 | MCP Router（三层合并 + JSON-RPC 转发） | 2 天 |
| P3 | Memory（mem0ai 集成 + 三级命名空间） | 1 天 |
| P4 | Wiki（Markdown CRUD + 全文搜索） | 1.5 天 |
| P5 | Skills API + Files API | 1 天 |
| P6 | Agent Call Router | 1 天 |
| P7 | Sync Scheduler + Dashboard | 2 天 |
| P8 | 测试 + 客户端配置 | 1 天 |

**总计**：约 10 天