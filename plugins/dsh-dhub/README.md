# dsh-dhub — DSH Cordis 插件

让 DSH 通过 D-Hub 获得跨设备共享记忆、Wiki 与结构化 Agent 消息。

- **独立 Node 包**（`plugins/dsh-dhub/`），零运行时依赖（仅用 Node 内置 `fetch`，Node ≥ 18）。
- **只主动出站**连接 D-Hub，不要求 DSH 开放入站端口。
- 不把任意 shell 作为远程任务接口；`send` 只允许结构化消息。

## 目录

```
plugins/dsh-dhub/
├── package.json
├── README.md
├── cordis.patch.yml      # DSH profiles/Cordis 安装配置（占位符）
├── config.example.yaml   # 配置样例（占位符）
├── src/
│   ├── index.mjs         # createPlugin() 入口 + 生命周期
│   ├── config.mjs        # 配置加载
│   ├── connector.mjs     # Agent Connector 客户端（register/heartbeat/poll/ack/send）
│   ├── recall.mjs        # 记忆召回
│   ├── capture.mjs       # 会话捕获（敏感信息过滤）
│   ├── tools.mjs         # DSH 工具
│   └── http.mjs          # 有超时的 fetch 封装
└── tests/                # node --test 单元测试
```

## 安装（DSH profiles / Cordis）

```bash
dsh plugin --profile web add <本包路径或链接>
```

提供独立 `cordis.patch.yml`。真实 token 通过运行时环境变量提供，不入库。

## 配置（占位符）

```yaml
- insert:
    - id: dsh-dhub
      name: dsh-dhub
      config:
        dhubUrl: "https://example.invalid/dhub"
        agentId: "example-agent"
        tokenEnv: "DHUB_AGENT_TOKEN"
        recallEnabled: true
        captureEnabled: true
        connectorEnabled: true
        recallTokenBudget: 1800
        uploadMaxBytes: 20000
```

真实 `token` 必须通过受保护的 credentials 机制 / 运行时环境变量（`tokenEnv`）提供。

## 生命周期

`createPlugin()` 返回 `lifecycle` 对象，宿主 DSH 运行时按其真实钩子绑定：

| 生命周期 | 本插件行为 |
|---|---|
| `sessionStart` | 注册/恢复 Connector，启动心跳与轮询 |
| `preStep` | 基于当前输入召回相关记忆（注入带 source 的上下文块） |
| `turnEnd` | 增量上传会话结果（过滤敏感信息） |
| `shutdown` | flush pending queue，heartbeat=offline / 注销 |

> 版本说明：具体 DSH 钩子名因 DSH 运行时版本而异。本插件暴露**纯函数**与
> `createPlugin()` 工厂，不伪造可能不存在的钩子名；绑定方式见上方表格与
> `src/index.mjs` 注释。已针对 Cordis 模型实现，`cordis.patch.yml` 为独立安装文件。

## 记忆召回

- 依据当前输入 + 上下文构造查询（namespace / agent_id / project_id）。
- 结果带 source 归属注入，不污染稳定 system prompt。
- 无结果不注入空块；单次查询超时；结果缓存；token/字符预算。
- D-Hub 不可达时 DSH 继续正常工作（返回空）。

## 会话捕获

默认只上传：用户消息、助手最终正文、过滤/截断的工具结果摘要、明确的任务状态。
默认不上传：思考过程、原始凭据、环境变量值、密码、私钥、Cookie、
完整大二进制/日志、与任务无关的本地文件内容。

实现：增量上传、本地 pending queue、幂等、重试、最大 payload、
敏感信息过滤、D-Hub 不可达不阻塞 DSH 主循环。

## 工具

| 工具 | 说明 |
|---|---|
| `dhub_memory_search` | 搜索当前 scope 可见记忆 |
| `dhub_memory_remember` | 存储持久事实/决策/观察 |
| `dhub_wiki_search` | 搜索 Wiki 知识 |
| `dhub_wiki_read` | 读取 Wiki 页面 |
| `dhub_agent_send` | 发送结构化跨 Agent 消息/任务（**必须用户明确授权**） |
| `dhub_agent_status` | 查询 Connector 状态 |

安全约束：
- 删除记忆必须用户明确授权；
- 发送跨 Agent 消息/任务必须用户明确授权；
- 默认只能访问当前 Agent 有权限的 namespace；
- 不通过工具执行任意命令。

## 测试

```bash
cd plugins/dsh-dhub
npm test
```
