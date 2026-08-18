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

## 第二步：安装 d-hub

在源码目录执行安装脚本。脚本会创建目录、安装当前项目包及依赖、生成 Admin key、写入 systemd unit，并启用定时器：

```bash
sudo apt install python3-venv
./deploy/install.sh
```

如需手工安装 Python 包，必须安装项目本身，不能只安装依赖：

```bash
python3 -m venv /opt/d-hub/.venv
/opt/d-hub/.venv/bin/pip install '/path/to/D-Hub[memory]'
```

## 第三步：验证

```bash
curl -fsS http://localhost:10101/health
# {"status":"ok","version":"0.1.0","modules":["mcp","memory","wiki","skills","files","registry","dashboard"]}
curl -I http://localhost:10101/
# HTTP/1.1 307 Temporary Redirect，Location: /ui
systemctl status dhub --no-pager
```

浏览器访问 `http://192.168.5.242:10101/`，应自动跳转到 Dashboard。若仍返回
`{"detail":"Not Found"}`，说明端口上运行的不是当前版本；重新执行
`./deploy/install.sh`，再检查 `journalctl -u dhub -n 100 --no-pager`。

## 第四步：检查定时任务

```bash
systemctl list-timers 'dhub-*'
```

> MCP、Skills 配置无需定时同步。文件变更立即生效，d-hub 每次请求实时读目录合并。

## 验证清单

- [ ] PostgreSQL 运行 + pgvector 扩展启用
- [ ] 目录结构完整（mcp/skills/wiki/files 各三层）
- [ ] d-hub 服务运行（:10101）
- [ ] Agent 注册成功
- [ ] MCP 三层合并正常（/mcp/tools/list 返回正确）
- [ ] 记忆读写正常
- [ ] Wiki 读写正常
- [ ] Skills 读写正常
- [ ] 记忆↔Wiki 同步和每日备份 timer 正常
- [ ] Dashboard 可访问（:10101/ui）

## 迁移与回滚（v0.4.0）

### 迁移
- 默认记忆后端保持 mem0 / json 兼容路径，升级**不会自动切换**后端。
- 若要启用腾讯 adapter，需显式配置：
  ```env
  DHUB_MEMORY_BACKENDS=mem0,agent_memory
  DHUB_AGENT_MEMORY_URL=...
  DHUB_AGENT_MEMORY_API_KEY=...
  DHUB_AGENT_MEMORY_SERVICE_ID=...
  ```
- 旧 `/memory/*` API 完全兼容，无需改动客户端。

### 回滚
- 回滚到旧提交：
  ```bash
  git checkout <上一发布版本>
  sudo bash deploy/install.sh   # 或按实际部署方式重启
  ```
- 记忆数据（JSON fallback / mem0 / connector 队列）均持久化在 `DHUB_ROOT/data`，
  回滚代码不影响已有数据。
- 后端切换是显式配置，回滚后默认回到 mem0/json 路径。
