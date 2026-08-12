# d-hub 实现状态

更新时间：2026-08-12

## 已实现

- FastAPI 单进程服务，端口 10101
- Agent 注册与 HTTP 代理调用
- MCP 三级配置实时合并、Streamable HTTP/stdio JSON-RPC 转发、远程工具 120 秒缓存
- 记忆命名空间与 mem0/pgvector 适配；缺模型配置时 JSON 降级
- Wiki Markdown CRUD、Whoosh 中英文全文索引、Git 自动提交与历史
- Skills 三级覆盖与增删改查
- Files 三级目录、上传下载删除、100 MiB 上传限制
- 记忆 ↔ Wiki 增量语义同步及同步历史
- 审计日志
- 备份、7 天默认保留策略与安全恢复
- 11 模块 Dashboard，可直接执行主要管理操作
- systemd 服务、同步/备份 timer 和 UG 一键安装脚本

## UG 部署

- 服务：`dhub.service`，enabled + active
- 地址：`http://192.168.5.242:10101`
- Dashboard：`http://192.168.5.242:10101/ui`
- PostgreSQL 16 + pgvector 0.6.0 已安装，数据库 `mem0`
- 当前记忆后端：JSON（New-API :3000 当前未监听，模型与 Key 未配置）
- 说明：实机验收写入了 `smoke` Agent、`projects/alpha` 测试记忆/Wiki/技能，保留作示例与运行证据
- systemd timer：每 4 小时语义同步；每天 02:00 完整备份（文件 + PostgreSQL pg_dump）

## 启用 mem0

编辑 `/opt/d-hub/config/dhub.env`：

```env
DHUB_MEMORY_BACKEND=mem0
NEW_API_KEY=...
DHUB_LLM_MODEL=...
DHUB_EMBED_MODEL=...
DHUB_EMBED_DIMS=1536
MEM0_DB_PASSWORD=...
```

并为 PostgreSQL 用户 `mem0` 设置同一个密码，随后执行：

```bash
sudo systemctl restart dhub
curl http://127.0.0.1:10101/health
```

## 验收结果

- 2026-08-12 本轮：Python 编译、Dashboard JavaScript 语法、Git diff、文件锁并发、备份保留及恢复回滚检查通过
- 当前工作环境未安装项目测试/运行依赖，因此本轮未重新执行 pytest、ruff 和浏览器实机验收
- 历史 UG 验收记录：health/register/memory/wiki/whoosh/skills/backup/ui/systemd/pgvector 通过

## 远端仓库

目标：`https://cnb.cool/duan_z/DHub`

当前设备没有 CNB HTTPS 凭据，尚未推送；配置 CNB token 或 SSH key 后可直接 push。
