# Agent 接入与资产同步

本文描述一个 Agent 如何接入 d-hub、发布自己的资产，并在运行期间读取和沉淀知识。

## 1. 两条通道

Agent 使用两条互补的通道：

| 通道 | 用途 | 入口 |
|---|---|---|
| MCP | 工作时查询/写入记忆和 Wiki，读取 Skill 和文件，调用上游工具 | `/mcp?agent_id=<id>&project=<id>` |
| Manifest 同步 | 启动或发布时注册 Agent，将本地声明的 MCP/Skill/提示词/Wiki/文件上传 | `dhub-agent-sync` |

Manifest 同步是本地到 d-hub 的幂等发布：同名 MCP、Skill、Wiki 和文件会被覆盖，
未在 manifest 中声明的远端资产不会被删除。运行期产生的事实不要写进 manifest，使用
`dhub_memory_add` 写入 Memory。

## 2. 选择资产类型和作用域

### 资产类型

| 内容 | 放置位置 | 原因 |
|---|---|---|
| 工具服务地址、工具声明 | MCP | 供 d-hub 合并和转发工具调用 |
| Agent 行为规则、操作流程、检查清单 | Skill | Agent 可按名称读取并执行 |
| 系统提示词中的稳定业务上下文 | Wiki | 可维护、可搜索、可追踪历史 |
| 事实、观察、执行结果、短期经验 | Memory | 适合语义检索和持续积累 |
| 原始配置、样例、报告或其他附件 | Files | 保留原始文件，不强行转成知识 |

提示词不作为第五种存储类型。行为提示词发布为 Skill；项目背景提示词发布为 Wiki。

### 作用域

| manifest `namespace` | MCP `scope` | 可见范围 |
|---|---|---|
| `global` | `global` | 所有 Agent |
| `agents/<agent_id>` | `agent` | 当前 Agent |
| `projects/<project_id>` | `project` | 当前项目 |

项目层覆盖 Agent 层，Agent 层覆盖全局层。Agent 的 MCP URL 必须携带真实的
`agent_id`；需要项目资产时也必须携带 `project`。
项目 Memory 由项目内 Agent 共享；Agent Memory 保持个人隔离。

## 3. 服务端准备

在 d-hub 服务器更新并重启服务：

```bash
cd /path/to/D-Hub
git pull
./deploy/install.sh
```

安装脚本会输出 Dashboard 地址和 `DHUB_ADMIN_KEY`。该密钥只用于管理员、Dashboard
和资产同步，不能配置到运行期 Agent。健康检查：

```bash
curl -fsS http://192.168.5.242:10101/health
```

## 4. Agent 配置 MCP

通用 Streamable HTTP 配置：

```json
{
  "mcpServers": {
    "dhub": {
      "url": "http://192.168.5.242:10101/mcp?agent_id=codex&project=project-a",
      "transport": "streamable-http",
      "headers": {
        "Authorization": "Bearer <AGENT_API_KEY>"
      }
    }
  }
}
```

接入后，d-hub 原生提供以下工具：

| 工具 | 功能 |
|---|---|
| `dhub_memory_search` | 搜索当前作用域记忆 |
| `dhub_memory_add` | 写入事实、决定或执行结果 |
| `dhub_wiki_search` | 搜索 Markdown 知识 |
| `dhub_wiki_get` | 读取 Wiki 页面 |
| `dhub_wiki_put` | 创建或更新 Wiki 页面 |
| `dhub_skills_list` | 列出当前 Agent/项目合并后的 Skill |
| `dhub_skill_get` | 读取一个 Skill |
| `dhub_files_list` | 列出当前作用域文件 |
| `dhub_file_read` | 读取小于 256 KiB 的 UTF-8 文本文件 |

另外，manifest 发布的上游 MCP 工具以 `rmcp__<server>__<tool>` 命名。

每个原生工具都支持 `scope: global | agent | project`。未传 `scope` 时，如果 MCP URL
配置了 `project` 则默认使用项目层，否则默认使用 Agent 层。
Agent key 只能用于 `/mcp`，并绑定注册时的 `agent_id` 和 `projects`；不能调用管理 REST，
也不能访问 global scope。Admin key 可以维护 global scope。

## 5. 创建 Agent 资产清单

复制项目中的完整示例：

```bash
cp -r examples/agent-assets /path/to/agent-repo/.dhub
```

核心文件 `.dhub/dhub-agent.json`：

```json
{
  "agent_id": "codex",
  "host": "developer-workstation",
  "callback_url": null,
  "projects": ["project-a"],
  "assets": {
    "mcp": [
      {
        "namespace": "agents/{agent_id}",
        "server_id": "local-tools",
        "path": "mcp/local-tools.json"
      }
    ],
    "skills": [
      {
        "namespace": "agents/{agent_id}",
        "name": "project-workflow",
        "path": "skills/project-workflow/SKILL.md"
      }
    ],
    "prompts": [
      {
        "namespace": "projects/{project}",
        "target": "wiki",
        "title": "agent-context",
        "path": "prompts/agent-context.md"
      }
    ],
    "wiki": [],
    "files": []
  }
}
```

支持 `{agent_id}` 和 `{project}` 占位符。`{project}` 使用 `projects` 的第一项；一个
Agent 同时参与多个项目时，为每个项目准备一份 manifest，避免资产被错误发布到首个项目。
同步器拒绝把 Agent 层资产发布到其他 Agent，也拒绝发布到 `projects` 中未声明的项目。

MCP 配置中的 `$ENV_NAME` 不会在同步机器展开，而是在 d-hub 调用上游服务时读取服务端
环境变量。例如：

```json
{
  "transport": "http",
  "url": "http://192.168.5.101:9000/mcp",
  "headers": {"Authorization": "Bearer $LOCAL_TOOLS_API_KEY"}
}
```

不要把实际 Token 写进 manifest 或上传资产。

## 6. 执行同步

在装有 `d-hub` Python 包的机器上：

```bash
export DHUB_URL="http://192.168.5.242:10101"
export DHUB_ADMIN_KEY="<安装脚本输出的管理密钥>"

# 只验证清单和本地文件，不发送请求
dhub-agent-sync .dhub/dhub-agent.json --dry-run

# 使用 Admin key 注册并上传所有声明的资产
dhub-agent-sync .dhub/dhub-agent.json
```

也可以直接运行模块：

```bash
python -m dhub.agent_sync .dhub/dhub-agent.json
```

成功输出示例：

```json
{
  "status": "ok",
  "agent_api_key": "<首次注册时返回一次>",
  "actions": [
    "register",
    "mcp:agents/codex/local-tools",
    "skill:agents/codex/project-workflow",
    "wiki:projects/project-a/agent-context"
  ]
}
```

适合在 Agent 启动脚本或 CI 发布阶段执行。同步失败时命令返回非零状态；不要忽略错误。
把首次返回的 `agent_api_key` 配进该 Agent 的 MCP 客户端。再次同步不会返回旧密钥；密钥
遗失时由管理员删除并重新注册 Agent。远端资产按顺序写入但不是跨请求事务。

从只支持单一 `DHUB_API_KEY` 的旧版本升级时，先为每个 Agent 执行一次 manifest 同步，
取得新签发的 `agent_api_key`，再把 MCP 客户端中的旧管理密钥替换掉。旧变量
`DHUB_API_KEY` 仅作为服务端 Admin key 的兼容回退，不应继续分发给 Agent。

## 7. 给 Agent 的建议提示词

将以下内容加入 Agent 的系统提示词，或作为 `project-workflow` Skill 发布：

```text
你已连接 d-hub。开始任务时，先用 dhub_skill_get 读取 project-workflow，再用
dhub_wiki_search 和 dhub_memory_search 查询与当前任务相关的项目上下文。

工作期间：
- 稳定的架构决定、接口约定和维护文档写入 project scope 的 Wiki；
- 可复用的事实、观察、故障原因和验证结果写入 project scope 的 Memory；
- 仅属于你个人工作方式的规则放在 agent scope；
- 多 Agent 都应遵守的规则放在 project scope，跨项目通用规则才放 global scope；
- 不写入密钥、Token、个人隐私、未经确认的推测或大段临时日志；
- 写入前先搜索，避免重复；已有 Wiki 页面应更新，不要创建同义页面。

任务结束前，把最终决定和验证结论沉淀到 d-hub；临时过程不必保存。
```

## 8. 验证接入

```bash
curl -fsS -H "Authorization: Bearer $DHUB_ADMIN_KEY" \
  http://192.168.5.242:10101/agents

curl -fsS -H "Authorization: Bearer $DHUB_ADMIN_KEY" \
  "http://192.168.5.242:10101/skills?agent_id=codex&project=project-a"

curl -fsS -H "Authorization: Bearer $DHUB_ADMIN_KEY" \
  "http://192.168.5.242:10101/wiki/pages?namespace=projects/project-a"
```

客户端重新连接 MCP 后，`tools/list` 应同时看到 `dhub_*` 原生工具和已同步上游的
`rmcp__*` 工具。

## 9. 当前同步边界

- Manifest 是单向发布，不自动下载远端改动。
- Manifest 同步是管理员操作；不要把 Admin key 交给运行期 Agent。
- 所有本地资产会在首个请求前完成校验，但多个远端写请求不是原子事务。
- 同步不会删除远端未声明资产，删除需通过 Dashboard 或 REST 接口显式执行。
- Memory 不从 manifest 批量导入，避免每次发布产生重复记忆。
- Files 通过 manifest 上传；MCP 仅直接读取 UTF-8 小文本，大文件使用 REST 下载。
- 一个 MCP 会话绑定初始化 URL 中的 Agent 和项目，修改项目后需重新连接。
