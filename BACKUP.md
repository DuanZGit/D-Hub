# d-hub 备份与恢复手册

## 备份内容

| 数据 | 存储 | 备份方式 |
|---|---|---|
| 记忆（PostgreSQL） | :5432 | pg_dump |
| MCP 配置 | /opt/d-hub/mcp/ | tar |
| 技能 | /opt/d-hub/skills/ | tar / git |
| Wiki | /opt/d-hub/wiki/ | tar / git |
| 文件 | /opt/d-hub/files/ | tar |
| Agent 注册表 | /opt/d-hub/config/ | tar |

## 备份脚本

`/opt/d-hub/scripts/backup.sh`：

```bash
#!/bin/bash
set -e
DATE=$(date +%Y%m%d)
BACKUP_DIR="/opt/d-hub/backups/$DATE"
mkdir -p "$BACKUP_DIR"

# 1. PostgreSQL
sudo -u postgres pg_dump mem0 > "$BACKUP_DIR/mem0.sql"

# 2. 文件目录（mcp/skills/wiki/files/config）
tar -czf "$BACKUP_DIR/data.tar.gz" \
  -C /opt/d-hub mcp skills wiki files config

# 3. 保留最近 7 天
find /opt/d-hub/backups/ -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;

echo "Backup OK: $BACKUP_DIR"
```

cron：
```
0 2 * * * /opt/d-hub/scripts/backup.sh >> /opt/d-hub/logs/backup.log 2>&1
```

## 恢复

```bash
# 1. 恢复数据库
sudo -u postgres psql mem0 < /path/to/mem0.sql

# 2. 恢复文件
tar -xzf /path/to/data.tar.gz -C /opt/d-hub

# 3. 重启
sudo systemctl restart dhub
```

## 灾难恢复 Checklist

- [ ] 备份目录存在且非空
- [ ] pg_dump 无错误
- [ ] tar 无错误
- [ ] 恢复后 d-hub 健康检查通过
- [ ] Agent 重新注册成功