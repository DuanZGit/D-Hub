# D-Hub 接入：让 Minis 能远程操控 Pi（Agent 注册 + 回调服务）

## 目标
D-Hub 在 UG（192.168.5.242:10101）。现在要把 Pi（本机 Termux，wlan0=192.168.5.10）
注册成 agent，并跑一个 HTTP 回调服务，这样 Minis（或任何 admin）可用
`POST /agent/pi/call` 远程向 Pin 下发指令、Pi 执行后返回结果。

## 一、注册 Agent

D-Hub 需要知道 Pi 的存在和回调地址。用 admin key 调：

```bash
# D-Hub admin key: /var/minis/workspace/d-hub/.dhub-admin-key（Minis 本机）
ADMIN_KEY=$(cat /var/minis/workspace/d-hub/.dhub-admin-key)
curl -sS -X POST http://192.168.5.242:10101/register \
  -H "Authorization: Bearer $ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{
    "agent_id": "pi",
    "host": "termux",
    "url": "http://192.168.5.10:4400/dhub",
    "tools": ["sync_wiki","upload_memory","sync_agents","read_local"],
    "projects": ["default"],
    "enabled": true
  }'
```

⚠️ 注意：**如果 Pi 已经用其它 agent_id 注册过，先 DELETE 旧条目**：
```bash
curl -sS -X DELETE http://192.168.5.242:10101/agents/<旧agent_id> \
  -H "Authorization: Bearer $ADMIN_KEY"
```

## 二、Pi 端回调服务（在 Termux 里跑）

Pi 用 Python 内置 http.server 起一个极简 HTTP 服务监听 192.168.5.10:4400。
收到 D-Hub 的 `{"method","params"}` 后按 method 分派执行。

```python
import json, subprocess, http.server, socketserver

DUZ_TOKEN = "REPLACE_WITH_DHUB_ADMIN_KEY"  # 回调鉴权（可选）

class H(http.server.BaseHTTPRequestHandler):
    def _ok(self, obj):
        body = json.dumps({"ok": True, "result": obj}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if DUZ_TOKEN:
            if self.headers.get("Authorization","") != f"Bearer {DUZ_TOKEN}":
                self.send_error(401); return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
        except Exception:
            self.send_error(400); return
        method = body.get("method")
        try:
            if method == "ping":
                self._ok({"pong": True})
            elif method == "read_wiki":
                self._ok({"pages": subprocess.run(["ls","wiki/"],capture_output=True,text=True).stdout.split()})
            else:
                self._ok({"unhandled": method, "params": body.get("params")})
        except Exception as e:
            self.send_error(500, e.__str__())
    def log_message(self, *a): pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("0.0.0.0", 4400), H) as httpd:
    httpd.serve_forever()
```

## 三、验证链路（Minis 侧发起）

注册 + 服务起来后，Minis 就可以：

```bash
curl -sS -X POST http://192.168.5.242:10101/agent/pi/call \
  -H "Authorization: Bearer $ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"method":"ping","params":{}}'
# 期望返回 {"result":{"pong":true}, "source_agent":"pi"}
```

## 四、Pi 需要暴露的 method（D-Hub 同步任务会调这些）

- `ping` — 连通检查
- `read_wiki` — 列出本地 OKF wiki 页面
- `sync_wiki` — 把本地 wiki（含 frontmatter 和 [[wikilink]]）分批 PUT 到 D-Hub `agents/pi` 命名空间
- `upload_memory` — 把 AGENTS.md 作为持久上下文页推 wiki；把可提取的决策/知识点推 memory
- `sync_sessions` — 增量推会话转录（已有，可复用）
