# D-Hub Skill

让 agent 高效使用 D-Hub 的速查 skill。遵循 [Agent Skills 标准](https://agentskills.io/specification)（Claude Code / Codex / Pi 通用）。

## 为什么用 skill 而不是写进 AGENTS.md

Skill 是**渐进式披露**：只有 `description`（几十字）常驻 context，完整指令**只在相关任务时加载**。写进 AGENTS.md / system prompt 会让每次对话都背着完整 D-Hub 用法，浪费 token。

## 安装

把 `dhub/` 目录拷到对应 agent 的 skills 目录：

| Agent | 目录 |
|---|---|
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` 或项目 `.agents/skills/` |
| Pi | `~/.pi/agent/skills/` 或 `~/.agents/skills/` |
| Cursor | `~/.cursor/skills/` |
| Minis | `/var/minis/skills/` |

```bash
# 通用：从 GitHub 下载
mkdir -p ~/.agents/skills/dhub
curl -fsSL -o ~/.agents/skills/dhub/SKILL.md \
  https://raw.githubusercontent.com/DuanZGit/D-Hub/master/skills/dhub/SKILL.md
```

> 提示：`~/.agents/skills/` 是 Claude Code、Codex、Pi 三家的公共目录（Pi 还支持在 settings.json 里引用别家的 skills 目录），装一处多处可用。

## 验证

问 agent："帮我搜一下 D-Hub 里关于 X 的记忆"，它应该直接调 `dhub_memory_search` 或按 curl 模板发请求，而不是反复读文档试探。

## 配套

- 会话自动同步见 [../plugins/](../plugins/)（Codex hooks / Pi extension）
- 数据通道 MCP 见 [AGENT_INTEGRATION.md](../../AGENT_INTEGRATION.md)
