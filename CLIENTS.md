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
      "url": "http://192.168.5.242:10101/mcp?agent_id=minis&project=project-a",
      "transport": "streamable-http",
      "headers": {"Authorization": "Bearer <DHUB_API_KEY>"}
    }
  }
}
```

启动时注册：
```bash
curl -X POST http://192.168.5.242:10101/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  -d '{"agent_id":"minis","host":"192.168.5.101","tools":["memory","wiki","mcp","files","skills"],"projects":["project-a","project-b"]}'
```

## Claude Code

```bash
claude mcp add dhub --transport http \
  "http://192.168.5.242:10101/mcp?agent_id=claude-code&project=project-a" \
  --header "Authorization: Bearer <DHUB_API_KEY>"
```

注册：
```bash
curl -X POST http://192.168.5.242:10101/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  -d '{"agent_id":"claude-code","host":"192.168.5.102","tools":["memory","wiki","mcp","code"],"projects":["project-a"]}'
```

## Codex

将以下配置加入 Codex MCP 配置；不要把 URL 放在 `--` 后当作本地 stdio 命令：

```toml
[mcp_servers.dhub]
url = "http://192.168.5.242:10101/mcp?agent_id=codex&project=project-a"
http_headers = { Authorization = "Bearer <DHUB_API_KEY>" }
```

## OpenClaw

```json
{
  "mcpServers": {
    "dhub": {
      "url": "http://192.168.5.242:10101/mcp?agent_id=openclaw&project=project-a",
      "transport": "streamable-http",
      "headers": {"Authorization": "Bearer <DHUB_API_KEY>"}
    }
  }
}
```

## 环境变量

```bash
export DHUB_URL="http://192.168.5.242:10101"
export DHUB_API_KEY="<安装脚本输出的密钥>"
export AGENT_ID="minis"
```

## Agent 互相调用示例

```bash
# Minis 调用 Claude Code
curl -X POST http://192.168.5.242:10101/agent/claude-code/call \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DHUB_API_KEY" \
  -d '{"method":"code.review","params":{"file":"/path/to/file.py","namespace":"projects/project-a"}}'
```
