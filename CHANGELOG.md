# Changelog

All notable changes to d-hub are documented here.

## [0.4.0] - unreleased

### Added
- **可插拔 MemoryBackend 架构**：新增 `MemoryService` 与后端协议
  （`Mem0Backend` / `JsonFallbackBackend`），路由/MCP/sync 不再直接调用 mem0。
  - 新增规范模型 `MemoryRecord` / `MemoryQuery` / `MemoryScope` / `MemoryPatch`。
  - 可选双写/双读评测（默认关闭，不改变默认 Mem0 结果）。
  - 新增 REST：`GET /memory/backends`、`GET /memory/health`、
    `GET/PATCH /memory/{id}`、`POST /memory/export`。
- **TencentDB Agent Memory adapter**：`TencentAgentMemoryBackend`（v3 数据面协议），
  带超时/有界重试/指数退避/熔断/幂等/secret 脱敏；未配置不阻塞启动。
  - 协议确认文档：`docs/tencentdb-agent-memory-protocol.md`。
  - fake server contract tests（无真实凭据）。
- **跨电脑 Agent Connector (v1)**：`ConnectorStore` + `/v1/connector/*`。
  - scoped token（一次性显示、只存 hash、可撤销、绑定 namespace/project/capability）。
  - 持久化队列、幂等、TTL、离线补投、dead-letter、审计。
  - API 文档：`docs/Connector API.md`。
- **DSH Cordis 插件**：`plugins/dsh-dhub/`（独立 Node 包，零运行时依赖）。
  - 生命周期 recall/capture/connector、六种工具、敏感信息过滤、离线降级。
- **离线检索评测**：`python -m dhub.memory_eval`；文档 `docs/memory-eval.md`。
- **跨平台连接文档**：`docs/DSH跨电脑连接.md`（LAN / VPN / HTTPS 反向代理，全占位符）。

### Changed
- `.env.example` 改为纯占位符（去除真实 URL/凭据）。
- metadata 中的自由文本 source 会归一化为合法 `MemorySource` 字面量。

### Migration / Rollback
- 默认记忆后端保持 mem0 / json 兼容路径，升级后不会自动切换后端。
- 若要启用腾讯 adapter，需显式配置 `DHUB_MEMORY_BACKENDS` 与 `DHUB_AGENT_MEMORY_*`。
- 回滚：切换回旧提交（见 DEPLOYMENT 的回滚说明）；旧 `/memory/*` API 兼容保留。

### NOT VERIFIED
- 真实 Tencent Agent Memory 服务（仅 fake server contract test）。
- 真实远程 DSH 联调（本地用模拟双设备流程）。
