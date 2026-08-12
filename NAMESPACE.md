# d-hub 三级命名空间

## 目录结构（MCP / Skills / Wiki / Files 统一）

```
/opt/d-hub/<type>/
├── global/              # 共识层：全 agent 共享
│   ├── tool-1.json
│   └── tool-2.json
├── agents/              # Agent 层：各自隔离
│   └── <agent_id>/
│       └── tool.json
└── projects/            # Project 层：项目内共享
    └── <project_id>/
        └── tool.json
```

## 各层可见范围

| 层级 | 可见范围 | 同名覆盖 |
|---|---|---|
| global | 所有 agent | 基础 |
| agents/<id> | 仅该 agent | 覆盖 global |
| projects/<id> | 项目成员 | 覆盖 agent + global |

## 查找顺序

```
Agent 请求工具 X
  → /opt/d-hub/<type>/projects/<project>/X  （有就返回）
  → /opt/d-hub/<type>/agents/<agent>/X      （有就返回）
  → /opt/d-hub/<type>/global/X              （有就返回）
  → 404
```

## 合并规则（读时计算，无缓存）

```
同名 tool → project > agent > global
不同名 tool → 全部合并，不存在冲突
```

每次请求实时读目录合并，文件变更立即生效。

## 示例：minis 在 project-a 中看到的 MCP 工具

```
来自 global：
  memory_search
  wiki_search
  files_read

来自 agents/minis：
  minis_custom_tool（覆盖 global 的同名工具）

来自 projects/project-a：
  code_review（覆盖 agent 的同名工具）

合并后：
  memory_search（global）
  wiki_search（global）
  files_read（global）
  code_review（project-a 覆盖）
  minis_custom_tool（minis 专属）
```

## 记忆命名空间（Mem0 user_id）

```
global:shared          → 共识层
global:<agent_id>      → Agent 层
global:project:<project_id>    → Project 层（项目内 Agent 共享）
```
