# d-hub 部署指南（单进程版）

## 前置条件

- UG（192.168.5.242）Ubuntu 24.04
- Python 3.10+
- New-API 运行在 :3000（已有）

## 第一步：安装 PostgreSQL + pgvector

```bash
sudo apt install postgresql postgresql-contrib postgresql-server-dev-16
sudo systemctl enable --now postgresql

# 编译安装 pgvector
cd /tmp
git clone --depth 1 https://github.com/pgvector/pgvector.git
cd pgvector && make && sudo make install

# 创建数据库
sudo -u postgres psql -c "CREATE DATABASE mem0;"
sudo -u postgres psql -d mem0 -c "CREATE EXTENSION vector;"
sudo -u postgres psql -c "CREATE USER mem0 WITH PASSWORD '$(openssl rand -base64 32)';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE mem0 TO mem0;"
```

## 第二步：创建目录结构

```bash
sudo mkdir -p /opt/d-hub/{mcp/{global,agents,projects},skills/{global,agents,projects},wiki/{global,agents,projects},files/{global,agents,projects},config,logs,scripts}
sudo chown -R duanz:duanz /opt/d-hub
```

## 第三步：安装 Python 依赖

```bash
python3 -m venv /opt/d-hub/.venv
source /opt/d-hub/.venv/bin/activate
pip install mem0ai fastapi uvicorn httpx pydantic python-multipart whoosh
```

## 第四步：创建 d-hub 服务

位置：`/opt/d-hub/dhub/main.py`

```python
# 强模型参考 ARCHITECTURE.md 实现以下模块：
#   1. Agent Registry（JSON 文件存储）
#   2. MCP Router（三层合并 + JSON-RPC 转发）
#   3. Memory（mem0ai 库，三级命名空间）
#   4. Wiki（Markdown CRUD + whoosh 全文搜索）
#   5. Skills API（三级目录读写）
#   6. Files API（三级目录读写）
#   7. Agent Call Router（注册表 → 转发）
#   8. Sync（手动/定时触发）
#   9. Dashboard（HTML/JS 静态文件）
```

## 第五步：Systemd 服务

```bash
sudo tee /etc/systemd/system/dhub.service << 'EOF'
[Unit]
Description=d-hub Agent Coordination Layer
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=duanz
WorkingDirectory=/opt/d-hub
ExecStart=/opt/d-hub/.venv/bin/uvicorn dhub.main:app --host 0.0.0.0 --port 10101
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"
Environment="MEM0_DB_PASSWORD=your-password-here"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now dhub
```

## 第六步：验证

```bash
curl http://localhost:10101/health
# {"status":"ok","version":"0.1.0","modules":["mcp","memory","wiki","skills","files","registry","dashboard"]}
```

## 第七步：配置 Cron（仅语义同步）

```bash
crontab -e
```

```
# 每 4 小时同步记忆 ↔ Wiki（LLM 提炼）
0 */4 * * * /opt/d-hub/.venv/bin/python /opt/d-hub/scripts/sync-memory-wiki.py >> /opt/d-hub/logs/sync.log 2>&1

# 每日备份
0 2 * * * /opt/d-hub/scripts/backup.sh >> /opt/d-hub/logs/backup.log 2>&1
```

> MCP、Skills 配置无需 cron 同步。文件变更立即生效，d-hub 每次请求实时读目录合并。

## 验证清单

- [ ] PostgreSQL 运行 + pgvector 扩展启用
- [ ] 目录结构完整（mcp/skills/wiki/files 各三层）
- [ ] d-hub 服务运行（:10101）
- [ ] Agent 注册成功
- [ ] MCP 三层合并正常（/mcp/tools/list 返回正确）
- [ ] 记忆读写正常
- [ ] Wiki 读写正常
- [ ] Skills 读写正常
- [ ] 记忆↔Wiki 语义同步 cron 正常
- [ ] Dashboard 可访问（:10101/ui）