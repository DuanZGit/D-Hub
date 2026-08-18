# DSH 跨电脑连接

本文档说明如何让**不同电脑**上的 DSH 通过各自的 dsh-dhub 插件连接到**同一个
D-Hub**，从而共享记忆、Wiki、状态与结构化 Agent 消息。所有方案只写**通用部署
方案与占位符**，不含任何真实 IP、域名、端口、账号或凭据。

## 拓扑

```text
远程电脑 DSH → DSH 插件 → HTTPS/VPN → D-Hub
                                      ├─ Memory
                                      ├─ Wiki
                                      ├─ Agent Connector
                                      └─ Audit
```

- D-Hub API 接受**入站**连接（DSH 主动连过来）。
- DSH 插件只做**主动出站**连接；DSH 本身不需要入站暴露。
- 管理 API 与 Agent API 权限不同：管理接口走 `DHUB_ADMIN_KEY`，Agent 走 scoped token。

## 一、同一局域网

```text
DHUB_URL=http://<dhub-lan-host>:<port>
```

- 仅适用于**受信任局域网**。
- 建议仍使用 scoped token（见 `docs/Connector API.md` 的 register 流程）。
- 示例（占位符）：

```bash
export DHUB_URL="http://<dhub-lan-host>:10101"
export DHUB_AGENT_TOKEN="<scoped-token>"
```

## 二、异地电脑

### 方案 1：VPN / Tailscale / WireGuard（推荐）

异地电脑与 D-Hub 处于同一虚拟私有网络，DSH 插件直接使用内网地址出站连接。

```text
DHUB_URL="http://<vpn-internal-host>:10101"
```

优点：加密、无需暴露公网端口、路由简单、延迟可控。

### 方案 2：HTTPS 反向代理（可用）

用 HTTPS 反向代理把 D-Hub 暴露到公网，**必须**：

- 启用 TLS；
- 使用 scoped token（不要共用管理员 key）；
- 限制路由（只代理 D-Hub 的 Agent/Connector 路径，不暴露管理台）；
- 做速率限制与访问控制。

```text
DHUB_URL="https://<proxy-host>/dhub"
```

### 方案 3：直接暴露 D-Hub 管理接口（不推荐）

不作为默认示例。除非在受控、有严格 ACL 与 TLS 的专用网络，否则避免直接暴露
D-Hub 管理接口到公网。

## 三、DSH 插件出站连接要点

- 只出站，不要求 DSH 开放入站端口；
- 所有 endpoint / TLS / proxy / VPN / 端口都通过配置表达；
- token 通过受保护的 credentials 机制或运行时环境变量提供，不入库、不写示例。

## 四、通用部署顺序

1. 部署一个 D-Hub（见 `DEPLOYMENT.md`），获得 `DHUB_ADMIN_KEY`。
2. 用 `POST /v1/connector/register` 为每台电脑的 DSH 创建 Connector Agent，
   获得一次性 scoped token。
3. 在各电脑 DSH 上安装 `dsh-dhub` 插件（见 `plugins/dsh-dhub/README.md`），
   配置 `dhubUrl` + `agentId` + `tokenEnv`（真实 token 走运行时环境变量）。
4. 设置网络（LAN / VPN / HTTPS 反向代理之一）。
5. 验证：`GET /v1/connector/status` 能看到各 agent 状态为 online；
   跨设备 `dhub_agent_send` / `dhub_agent_status` 可互通。

## 五、安全边界提醒

- 删除记忆 / 发送跨 Agent 消息都需用户明确授权；
- 普通 Agent 只能访问授权 namespace；
- `send` 只允许结构化消息，不执行任意命令；
- 若未来要执行任务，必须作为 DSH 自己的用户审批和安全策略输入，
  不得由 D-Hub 绕过 DSH 执行。
