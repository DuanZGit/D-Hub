# d-hub：多 Agent 统一协调层

## 一句话

d-hub = 一个 Python 进程（:10101）+ 一个 PostgreSQL（:5432）。  
记忆、Wiki、MCP、技能、文件、Agent 路由、Dashboard，全在一个进程里。

## 设计原则

1. **单进程**：d-hub 一个 Python 进程搞定所有协调
2. **单数据库**：PostgreSQL + pgvector 存储记忆和结构化数据
3. **三级隔离**：共识层（global）/ Agent 层（agents/<id>）/ Project 层（projects/<id>）
4. **读时合并**：MCP、Skills 配置每次请求实时合并，无缓存、无 cron
5. **Wiki git 化**：Markdown 文件 + 自动 commit，可回滚
6. **非 Docker**：原生 Python，systemd 管理
7. **cron 只做语义同步**：记忆 ↔ Wiki 提炼（LLM 处理）

## 技术栈

| 组件 | 技术 | 说明 |
|---|---|---|
| d-hub | Python FastAPI | 一个进程，全包 |
| 记忆 | `import mem0` | Python 库，直接调用，不是独立服务 |
| Wiki | Python 内置 | Markdown 文件 CRUD + 全文搜索（whoosh） |
| MCP 路由 | Python 内置 | JSON-RPC 转发 + 三层配置合并 |
| 技能仓库 | 文件系统 | 三层目录：global / agents / projects |
| 文件共享 | 文件系统 | 三层目录：global / agents / projects |
| Dashboard | FastAPI 静态文件 | 内嵌在 d-hub |
| 数据库 | PostgreSQL + pgvector | 系统 apt 安装，仅 localhost |
| 同步 | cron | 定时同步 MCP/Skills/Wiki 配置 |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│               d-hub (:10101) — 唯一进程                     │
│                                                           │
│  FastAPI 服务                                            │
│  ├── /mcp/*          MCP 路由（三层合并）                 │
│  ├── /memory/*       记忆（mem0ai 库直接调用）            │
│  ├── /wiki/*         Wiki（内置 Markdown 引擎）           │
│  ├── /skills/*       技能仓库                             │
│  ├── /files/*        文件共享                             │
│  ├── /agent/*        Agent 注册 + 路由                    │
│  ├── /sync/*         同步触发                             │
│  └── /ui             Dashboard                            │
│                                                           │
│  mem0ai 库（import mem0）                                 │
│  └── 直接读写 PostgreSQL                                   │
└───────────────────────────────────────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────────────────┐
│  PostgreSQL + pgvector (:5432) — 唯一数据库                 │
│  仅 localhost，不对外暴露                                    │
└───────────────────────────────────────────────────────────┘
```

## 三级目录结构

所有资产（MCP、Skills、Wiki、Files）统一走同一套目录模式：

```
/opt/d-hub/
├── mcp/                     # MCP 服务器配置（JSON 文件）
│   ├── global/              #   全局共享
│   ├── agents/<id>/         #   Agent 专属
│   └── projects/<id>/       #   项目专属
├── skills/                  # 技能（SKILL.md 文件）
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
├── wiki/                    # Wiki 页面（Markdown 文件）
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
└── files/                   # 共享文件
    ├── global/
    ├── agents/<id>/
    └── projects/<id>/
```

**查找顺序**（MCP、Skills 一致）：

```
Agent 请求资源 X
  → 查 project 层（/opt/d-hub/<type>/projects/<project>/X）
  → 查 agent 层（/opt/d-hub/<type>/agents/<agent>/X）
  → 查 global 层（/opt/d-hub/<type>/global/X）
  → 找不到 → 404
```

**合并规则**：同名覆盖（project > agent > global），不同名合并。

## 数据流 — MCP 路由（读时合并）

```
Agent → POST /mcp/tools/list {agent_id, project}
     → d-hub 读取 mcp/global/ + mcp/agents/<id>/ + mcp/projects/<id>/
     → 合并（project 覆盖 agent 覆盖 global）
     → 返回合并后的工具列表
     （无缓存、无 cron、每请求实时计算）

Agent → POST /mcp/tools/call {name, arguments}
     → d-hub 查合并后的配置表里该 tool 对应的 MCP server
     → 转发 JSON-RPC 请求
     → 返回结果
```

## 数据流 — Wiki（git 化）

```
Agent → POST /wiki/page {namespace, title, content}
     → d-hub 写入对应目录的 Markdown 文件
     → git add + git commit（自动）
     → 更新全文索引

回滚：
  cd /opt/d-hub/wiki && git revert <commit>
```

## 端口分配

| 服务 | 端口 | 访问范围 | 说明 |
|---|---|---|---|
| d-hub | 10101 | 局域网 | 唯一入口 |
| PostgreSQL | 5432 | 仅 localhost | 数据库 |

## 同步机制（只有一种）

不是所有资产都需要同步。只有需要 LLM 处理的**语义同步**才需要 cron：

```
cron 每 4 小时：
  记忆共识层（global:shared）
    → LLM 提取精华
    → 生成/更新 Wiki 共识页面
    → 回写确认

MCP 配置 / Skills / 文件：
  → 不需要 cron
  → 每次请求实时读目录合并
  → 文件变更立即生效
```

## 当前依赖状态

| 依赖 | 状态 | 说明 |
|---|---|---|
| UG（192.168.5.242） | ✅ 在线 | Ubuntu 24.04 |
| PostgreSQL + pgvector | ⚠️ 待安装 | apt install + 编译 |
| mem0ai | ⚠️ 待安装 | pip install mem0ai |
| Python 3.10+ | ✅ 已装 | 系统自带 |
| FastAPI 等 | ⚠️ 待安装 | pip install |
| Node.js | ❌ 不需要 | 全 Python，无外部运行时依赖 |
| gh CLI | ✅ 已装 | 账号 DuanZGit |