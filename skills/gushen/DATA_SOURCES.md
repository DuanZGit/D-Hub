# Gushen 数据源 → 字段 → Agent 映射

| 数据源 | 字段 | 供给 Agent |
|--------|------|------------|
| `cn_market.py` 腾讯 | 实时价/涨跌/量比/K线(MA5/MA20/RSI/MACD) | 技术/动量/情绪 |
| `deep.py fund` Finnhub | ROE/PE/PS/PB/股息/β/52周/评级/EPS surprise | 巴菲特/芒格/段永平/风控 |
| `deep.py cnfund` baostock | ROE/净利率/毛利/YoY/分红 | 李录(价值组) |
| `deep.py north/flow` 东财 | 北向/主力资金(间歇性) | 情绪/动量 |
| `adanos.py` Adanos API | 美股跨社群情绪：Reddit/X/News/Polymarket 的 buzz/mentions/多空比(bullish_pct)/trend_history | 情绪/动量 |
| `financial_rigor.py` | PE/ROE/股息验算 + 多源交叉 + 三情景中性价 | 全 Agent 锚点 |
| `dump_facts.py` | 聚合落盘 facts.json | 报告唯一数源 |
| `verify.py` | 三源交叉价格校验 | Gate F 准出 |

> 详情 `SKILL.md`，命令 `tools/* --help`。

## Adanos 接入说明（2026-09-25）

- **定位**：美股情绪增量源，仅 Reddit/X/News/Polymarket 四社群 ticker 情绪（`api.adanos.org`，X-API-Key）。**A 股不覆盖**——A 股情绪仍走东财 north/flow。
- **入口**：`tools/adanos.py sentiment GOOG [NVDA...]`（四源 compare，tickers ≤10，4 req）/ `market`（全市场 reddit+x）/ `explain GOOG`（新闻源解释）/ `trending reddit`（候选挖掘）。
- **集成**：`dump_facts.py` 自动写 `facts.sentiment`（≤10 只/次，4 req）；`workflow.py` scan 初筛 10 只带 `sentiment` 字段。
- **降级**：无 `ADANOS_KEY` 或 `ADANOS_NO_SENTIMENT=1` → stderr 四要素引导 + facts 标 `skipped`，主流程不阻断。
- **配额**：免费档 250 req/月、30 天回看；raw mentions 与文本情感 `/sentiment/v1/analyze` 为 Professional $299/月专属。完整日报约 8 req（dump_facts 4 + scan 4）。
- **发现来源**：OpenStock（github.com/Open-Dev-Society/OpenStock）的商业实现，此处只调 Adanos API，未引入其 AGPL 代码。
