# 记忆检索离线评测（memory_eval）

D-Hub 提供离线检索评测命令，对比不同 MemoryBackend 的检索质量与性能。

## 命令

```bash
python -m dhub.memory_eval --dataset <path> --backends mem0,agent_memory --k 5
```

- `--dataset`：数据集 JSON 路径。
- `--backends`：逗号分隔的 backend 名（`mem0` / `agent_memory` / `json`）。
- `--k`：top-k。

## 数据集格式

```json
{
  "queries": [
    {"query": "...", "expected_keywords": ["a", "b"]},
    {"query": "...", "expected_ids": ["mem-1", "mem-2"], "namespace": "global", "agent_id": "shared"}
  ]
}
```

每条查询支持两种命中判定之一：

- `expected_keywords`：检索结果内容须包含全部关键词；
- `expected_ids`：检索结果 id 须出现在该列表。

可选字段 `namespace` / `agent_id` 用于限定检索范围（默认 `global` / `shared`）。

## 输出指标

每个 backend 输出：

- `top_k_hit_rate`：top-k 命中率；
- `mean_reciprocal_rank`：MRR；
- `mean_latency_ms`：平均延迟；
- `error_rate`：出错查询占比；
- `result_chars` / `result_tokens`：结果字符 / token 估算；
- `available`：backend 是否可用（未配置的远程 backend 标记为不可用）。

## 说明

- 只跑本地可用的 backend；未配置的远程 backend 报告为不可用，不报错。
- 真实远程服务不主动连接（除非通过环境变量配置）。
