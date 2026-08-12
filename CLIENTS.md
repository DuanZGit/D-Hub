# d-hub 客户端接入

## 统一地址

```
http://192.168.5.242:10101
```

每个 agent 只需配这一个地址。

## Minis

Minis 的 MCP 配置指向 d-hub：

```json
{
  "mcpServers": {
    "dhub": {
      "url": "http://192.168.5.242:10101/mcp",
      "transport": "streamable-http"
    }
  }
}
```

启动时注册：
```bash
curl -X POST http://192.168.5.242:10101/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"minis","host":"192.168.5.101","tools":["memory","wiki","mcp","files","skills"],"projects":["project-a","project-b"]}'
```

## Claude Code

```bash
claude mcp add dhub --transport http http://192.168.5.242:10101/mcp
```

注册：
```bash
curl -X POST http://192.168.5.242:10101/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"claude-code","host":"192.168.5.102","tools":["memory","wiki","mcp","code"],"projects":["project-a"]}'
```

## Codex

```bash
codex mcp add dhub -- http://192.168.5.242:10101/mcp
```

## OpenClaw

```bash
claw mcp add dhub http://192.168.5.242:10101/mcp
```

## 环境变量

```bash
export DHUB_URL="http://192.168.5.242:10101"
export AGENT_ID="minis"
```

## Agent 互相调用示例

```bash
# Minis 调用 Claude Code
curl -X POST http://192.168.5.242:10101/agent/claude-code/call \
  -H "Content-Type: application/json" \
  -d '{"method":"code.review","params":{"file":"/path/to/file.py","namespace":"projects/project-a"}}'
```