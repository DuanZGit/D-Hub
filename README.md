# D-Hub：多 Agent 统一协调层

> **版本 v0.3.0** — 会话转录层 + 单向自动上传器（dhub-uploader）

## 一句话

D-Hub = 一个 Python 进程（:10101）+ 一个 PostgreSQL（:5432）。  
记忆、Wiki、会话转录、MCP、技能、文件、Agent 路由、Dashboard，全在一个进程里。

Dashboard：`http://<服务器>:10101/ui`。根地址会自动跳转到 Dashboard；
`deploy/install.sh` 会生成 `DHUB_ADMIN_KEY`，仅供管理台和资产同步使用；运行期
Agent 使用注册时单独签发的密钥。

Agent 接入、原生 MCP 工具、资产 manifest 和提示词模板见
[AGENT_INTEGRATION.md](AGENT_INTEGRATION.md)。可运行示例位于
[`examples/agent-assets`](examples/agent-assets)。

## 设计原则

1. **单进程**：D-Hub 一个 Python 进程搞定所有协调
2. **单数据库**：PostgreSQL + pgvector 存储记忆和结构化数据
3. **三级隔离**：共识层（global）/ Agent 层（agents/<id>）/ Project 层（projects/<id>）
4. **读时合并**：MCP、Skills 配置每次请求实时合并，无缓存、无 cron
5. **Wiki git 化**：Markdown 文件 + 自动 commit，可回滚
6. **非 Docker**：原生 Python，systemd 管理
7. **定时任务只做语义同步**：记忆 ↔ Wiki 提炼（LLM 处理）

## 快速开始

### 1. 环境要求

- Linux 服务器，建议 Ubuntu 24.04
- Python 3.10+
- PostgreSQL 16 + pgvector

### 2. 安装依赖

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgresql-16-pgvector
sudo systemctl enable --now postgresql
```

### 3. 准备数据库

```bash
sudo -u postgres psql -c "CREATE DATABASE mem0;"
sudo -u postgres psql -d mem0 -c "CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -c "CREATE USER mem0 WITH PASSWORD 'your-password';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE mem0 TO mem0;"
```

### 4. 部署 D-Hub

```bash
git clone https://github.com/DuanZGit/D-Hub.git
cd D-Hub
sudo bash deploy/install.sh
```

安装脚本会自动完成：
- 创建 `/opt/d-hub` 目录结构
- 安装 Python 依赖
- 配置 systemd 服务
- 启动 `dhub.service`

### 5. 验证

```bash
curl http://127.0.0.1:10101/health
```

## 如何使用

### 启动与停止

```bash
sudo systemctl start dhub
sudo systemctl stop dhub
sudo systemctl restart dhub
sudo systemctl status dhub
```

### 配置环境变量

编辑 `/opt/d-hub/config/dhub.env`：

```env
DHUB_ROOT=/opt/d-hub
DHUB_PORT=10101
DHUB_MEMORY_BACKEND=json
NEW_API_BASE_URL=http://127.0.0.1:3000/v1
NEW_API_KEY=your-key
DHUB_LLM_MODEL=your-model
DHUB_EMBED_MODEL=your-embedding-model
DHUB_EMBED_DIMS=1536
MEM0_DB_HOST=127.0.0.1
MEM0_DB_PORT=5432
MEM0_DB_NAME=mem0
MEM0_DB_USER=mem0
MEM0_DB_PASSWORD=your-password
```

修改后重启：

```bash
sudo systemctl restart dhub
```

### Dashboard

浏览器打开：

```
http://<服务器IP>:10101/ui
```

Dashboard 提供 12 个功能模块：总览、Agent、MCP、记忆、Wiki、会话、技能、文件、同步、日志、配置、备份。

### 常用 API 示例

#### Agent 注册

```bash
curl -X POST http://127.0.0.1:10101/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"minis","projects":["project-a"]}'
```

#### 添加记忆

```bash
curl -X POST http://127.0.0.1:10101/memory/add \
  -H "Content-Type: application/json" \
  -d '{"namespace":"projects/project-a","agent_id":"minis","content":"决定使用 PostgreSQL"}'
```

#### 搜索记忆

```bash
curl -X POST http://127.0.0.1:10101/memory/search \
  -H "Content-Type: application/json" \
  -d '{"namespace":"projects/project-a","agent_id":"minis","query":"PostgreSQL"}'
```

#### 创建 Wiki 页面

```bash
curl -X POST http://127.0.0.1:10101/wiki/page \
  -H "Content-Type: application/json" \
  -d '{"namespace":"projects/project-a","title":"架构决策","content":"# 数据库选型\n\nPostgreSQL。"}'
```

#### 搜索 Wiki

```bash
curl "http://127.0.0.1:10101/wiki/search?namespace=projects%2Fproject-a&q=PostgreSQL"
```

#### 创建会话转录

```bash
curl -X POST http://127.0.0.1:10101/sessions \
  -H "Content-Type: application/json" \
  -d '{"namespace":"projects/project-a","title":"重构讨论","cwd":"/repo"}'
```

#### 追加消息到会话

```bash
curl -X POST http://127.0.0.1:10101/sessions/<session_id>/messages \
  -H "Content-Type: application/json" \
  -d '{"namespace":"projects/project-a","messages":[{"role":"user","content":"开始重构"}]}'
```

#### 搜索会话

```bash
curl "http://127.0.0.1:10101/sessions/search?namespace=projects%2Fproject-a&q=重构"
```

#### 上传文件

```bash
curl -X POST "http://127.0.0.1:10101/files/upload?namespace=global" \
  -F "file=@/path/to/file.txt"
```

#### MCP 工具列表

```bash
curl -X POST http://127.0.0.1:10101/mcp/tools/list \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"minis","project":"project-a"}'
```

### 启用 Mem0 记忆后端

1. 确认 PostgreSQL 和 pgvector 已安装
2. 在 `/opt/d-hub/config/dhub.env` 中配置：
   - `NEW_API_KEY`
   - `DHUB_LLM_MODEL`
   - `DHUB_EMBED_MODEL`
   - `MEM0_DB_PASSWORD`（与 PostgreSQL `mem0` 用户密码一致）
3. 重启服务：

```bash
sudo systemctl restart dhub
```

4. 验证后端：

```bash
curl http://127.0.0.1:10101/health
# 查看 "memory_backend": "mem0"
```

### 备份与恢复

#### 手动备份

```bash
curl -X POST http://127.0.0.1:10101/backup
```

备份文件保存在 `/opt/d-hub/backups/<时间戳>/`。

#### 查看备份列表

```bash
curl http://127.0.0.1:10101/backups
```

#### 恢复备份

```bash
curl -X POST "http://127.0.0.1:10101/backup/<备份名>/restore"
```

### 定时任务

D-Hub 使用 systemd timer 管理定时任务：

| 任务 | 频率 | 说明 |
|---|---|---|
| 记忆 ↔ Wiki 语义同步 | 每 4 小时 | 需要配置 LLM 模型 |
| 完整备份 | 每天 02:00 | 文件 + PostgreSQL |

查看定时任务状态：

```bash
systemctl list-timers | grep dhub
```

## Agent 接入

Agent 通过三条通道接入 D-Hub：

### 1. MCP（运行时通道）

Agent 配置 Streamable HTTP MCP，连接 D-Hub 后可使用原生工具和上游工具。

**配置示例**（Claude Code / Cursor 等客户端）：

```json
{
  "mcpServers": {
    "dhub": {
      "url": "http://192.168.5.242:10101/mcp?agent_id=codex&project=project-a",
      "transport": "streamable-http"
    }
  }
}
```

### 2. Manifest 同步（发布通道）

Agent 启动时通过 Manifest 发布自己的 MCP 配置、Skill、Wiki 和文件。

```bash
# 安装 D-Hub Python 包
pip install d-hub

# 注册并发布资产
dhub-agent-sync .dhub/dhub-agent.json
```

### 3. 单向手动同步（dhub-uploader）

多端 Agent 把本地资产**手动推送**到云 D-Hub。方向是**单向 push**——下载由 Agent 通过 MCP 工具（`dhub_session_get`、`dhub_memory_search` 等）按需主动拉取，不做反向实时同步。

每次运行扫描一次即退出，无守护进程、无轮询。想同步时手动跑一条命令即可。

支持的源：

| `--source` | 本地资产 | 映射到 D-Hub |
|---|---|---|
| `claude` | `~/.claude/projects/*/*.jsonl` | 会话转录 |
| `codex` | `~/.codex/sessions/*/rollout-*.jsonl` | 会话转录 |
| `minis` | `/var/minis/memory/*.md` | 记忆 + Wiki（GLOBAL.md） |
| `generic` | 任意目录（`--dir`） | 会话 + 记忆 |

```bash
# 手动同步一次（扫描后退出）
dhub-uploader --source minis --url http://<d-hub>:10101 \
  --api-key <admin-key> --namespace agents/minis --agent-id minis
```

增量策略（重跑不重复）：
- 会话转录**按行追加**（只上传新消息）
- 记忆**按内容哈希判重**（不变不重传）
- 状态文件记录映射，默认 `~/.dhub-uploader-state.json`

如果需要定时，交给 cron / systemd timer 自行调度（`dhub-uploader` 本身只做单次同步）。

### 4. 会话自动同步插件（推荐）

`dhub-uploader` 是手动一次性同步，但**会话自动同步**更优雅的方式是用各 Agent 的**原生插件**：会话一结束自动把 transcript 推上去，零安装、零依赖、增量去重。

| Agent | 机制 | 触发点 | 位置 |
|---|---|---|---|
| Codex | hooks | `SessionEnd` | [plugins/codex](plugins/codex/) |
| Pi | TypeScript extension | `session_shutdown` | [plugins/pi](plugins/pi/) |

详见 [plugins/README.md](plugins/README.md)。

另有一个 [dhub skill](skills/dhub/)，让 agent 按需加载 D-Hub 用法速查（省 token），遵循 agentskills.io 标准，Claude Code / Codex / Pi 通用。

### 原生 MCP 工具

连接后，D-Hub 自动提供以下工具：

| 工具 | 用途 |
|---|---|
| `dhub_memory_search` | 搜索记忆 |
| `dhub_memory_add` | 写入记忆 |
| `dhub_wiki_search` | 搜索 Wiki |
| `dhub_wiki_put` | 创建/更新 Wiki |
| `dhub_skills_list` | 列出技能 |
| `dhub_files_list` | 列出文件 |
| `dhub_file_read` | 读取文件 |
| `dhub_session_create` | 创建会话转录 |
| `dhub_session_list` | 列出会话 |
| `dhub_session_get` | 读取会话 |
| `dhub_session_append` | 追加会话消息 |
| `dhub_session_search` | 搜索会话 |

更多细节见 [AGENT_INTEGRATION.md](AGENT_INTEGRATION.md) 和 [examples/agent-assets](examples/agent-assets)。

### 目录结构

```
/opt/d-hub/
├── mcp/                     # MCP 服务器配置
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
├── skills/                  # 技能仓库
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
├── wiki/                    # Wiki 页面
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
├── files/                   # 共享文件
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
├── sessions/                # 会话转录（JSON 元数据 + JSONL 消息流）
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
├── config/                  # 配置文件
│   └── dhub.env
├── data/                    # 数据文件
├── logs/                    # 日志
├── backups/                 # 备份
└── scripts/                 # 脚本
```

## 技术栈

| 组件 | 技术 | 说明 |
|---|---|---|
| D-Hub | Python FastAPI | 一个进程，全包 |
| 记忆 | `import mem0` | Python 库，直接调用，不是独立服务 |
| Wiki | Python 内置 | Markdown 文件 CRUD + 全文搜索（whoosh） |
| MCP 路由 | Python 内置 | JSON-RPC 转发 + 三层配置合并 |
| 技能仓库 | 文件系统 | 三层目录：global / agents / projects |
| 文件共享 | 文件系统 | 三层目录：global / agents / projects |
| 会话转录 | 文件系统 | JSON 元数据 + JSONL 消息流，三层目录 |
| 手动同步 | `dhub-uploader` CLI | 单向 push，单次扫描增量同步 |
| Dashboard | FastAPI 静态文件 | 内嵌在 D-Hub |
| 数据库 | PostgreSQL + pgvector | 系统 apt 安装，仅 localhost |
| 同步 | systemd timer | 定时运行记忆 ↔ Wiki 语义同步 |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│               D-Hub (:10101) — 唯一进程                     │
│                                                           │
│  FastAPI 服务                                            │
│  ├── /mcp/*          MCP 路由（三层合并）                 │
│  ├── /memory/*       记忆（mem0ai 库直接调用）            │
│  ├── /wiki/*         Wiki（内置 Markdown 引擎）           │
│  ├── /skills/*       技能仓库                             │
│  ├── /files/*        文件共享                             │
│  ├── /sessions/*     会话转录                             │
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

所有资产（MCP、Skills、Wiki、Files、Sessions）统一走同一套目录模式：

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
├── files/                   # 共享文件
│   ├── global/
│   ├── agents/<id>/
│   └── projects/<id>/
└── sessions/                # 会话转录（<id>.json + <id>.jsonl）
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
     → D-Hub 读取 mcp/global/ + mcp/agents/<id>/ + mcp/projects/<id>/
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

不是所有资产都需要同步。只有需要 LLM 处理的**语义同步**才需要定时任务：

```
systemd timer 每 4 小时：
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
