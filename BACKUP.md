# d-hub 备份与恢复手册

## 备份内容

| 数据 | 存储 | 备份方式 |
|---|---|---|
| 记忆（PostgreSQL） | :5432 | `pg_dump --format=custom` |
| MCP 配置 | /opt/d-hub/mcp/ | tar |
| 技能 | /opt/d-hub/skills/ | tar / git |
| Wiki | /opt/d-hub/wiki/ | tar / git |
| 文件 | /opt/d-hub/files/ | tar |
| Agent 注册表 | /opt/d-hub/config/ | tar |

## 备份方式

`/opt/d-hub/scripts/backup.sh` 调用受保护的备份 API：

```bash
set -a
. /opt/d-hub/config/dhub.env
set +a
DHUB_URL=http://127.0.0.1:10101 /opt/d-hub/scripts/backup.sh
```

成功备份后会自动删除超过 `DHUB_BACKUP_RETENTION_DAYS` 的旧备份，默认保留 7 天。

每日 02:00 的 systemd timer：
```
systemctl status dhub-backup.timer
journalctl -u dhub-backup.service
```

## 恢复

```bash
# 1. 通过 Dashboard 或 API 恢复文件归档
curl -X POST -H "Authorization: Bearer $DHUB_API_KEY" \
  "http://127.0.0.1:10101/backup/<backup-name>/restore"

# 2. 若备份包含 mem0.dump，服务会用事务式 pg_restore 一并恢复
# 3. 重启服务
sudo systemctl restart dhub
```

## 灾难恢复 Checklist

- [ ] 备份目录存在且非空
- [ ] pg_dump 无错误
- [ ] tar 无错误
- [ ] 恢复后 d-hub 健康检查通过
- [ ] Agent 重新注册成功
