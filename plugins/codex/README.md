# Codex 插件：会话同步到 D-Hub

Codex（OpenAI Codex CLI）会话结束时，自动把会话转录单向推送到 D-Hub。

## 原理

- 用 Codex 原生 **hooks** 机制，监听 `SessionEnd` 事件
- 事件触发后，hook 脚本（纯 Python，零依赖）读取 `transcript_path` 指向的 JSONL 会话文件
- 解析出消息（role + content），增量上传到 D-Hub 的 `POST /sessions` + `POST /sessions/{id}/messages`

## 安装

### 1. 拷贝文件

```bash
mkdir -p ~/.codex/hooks
cp plugins/codex/dhub_sync.py ~/.codex/hooks/
cp plugins/codex/hooks.json ~/.codex/hooks.json   # 或合并进 ~/.codex/config.toml
chmod +x ~/.codex/hooks/dhub_sync.py
```

> 也可以直接合并进 `~/.codex/config.toml` 的 `[hooks]` 表，二选一即可（两者同时存在会告警）。

### 2. 配置环境变量

```bash
export DHUB_URL="http://duanz.xin:47222"        # D-Hub 地址
export DHUB_API_KEY="<admin 或 agent key>"       # 鉴权
export DHUB_NAMESPACE="agents/codex"             # 目标命名空间
export DHUB_AGENT_ID="codex"                     # agent 标识
```

建议写进 `~/.bashrc` / `~/.zshrc`，否则 hook 子进程读不到。

### 3. 信任 hook

首次运行时 Codex 会提示 review 新的 hook，在 CLI 里执行：

```
/hooks
```

找到 `dhub_sync.py`，确认信任。之后每次会话结束自动同步。

## 验证

结束一次 Codex 会话后，检查 D-Hub：

```bash
curl "http://<d-hub>:10101/sessions?namespace=agents/codex" \
  -H "Authorization: Bearer $DHUB_API_KEY"
```

## 增量与状态

- 状态文件 `~/.codex/.dhub-sync.json` 记录每个 transcript 的远程 session id 和已上传行数
- 重跑/续传不会重复上传
- 删除状态文件会重新创建会话并全量上传

## 注意

- `SessionEnd` 默认超时 1 秒、上限 3 秒，所以 hook 用 `async: true` 后台运行，`timeout: 30` 给足上传时间
- `transcript_path` 是 Codex 提供的便捷字段，格式非稳定接口；本脚本只提取 `role` + `content`，对其他字段做宽容解析
