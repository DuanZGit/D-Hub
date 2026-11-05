# Gushen 执行契约（唯一权威）

## 1. 固定 8 Agent，统一 5 分制

巴菲特/段永平/芒格/李录 + 技术分析师/动量交易员/情绪分析师/风控官。缺一或分制错误即未完成。每 Agent 必出：`x/5 + 2 条数据绑定 + 1 句逆向/反共识 + 1 句结论`。

## 2. Gate A-E（先数据，后结论）

**Gate A · 数据与落盘（推荐 `workflow.py` 单入口）** — `workflow.py` 一键完成：持仓+指数 → `dump_facts.py > facts.json`（每数必源于此，幂等复用当日）→ `financial_rigor.py` 自动精算（growth/pe 自动算，不手填；中性情景即锚）直供 B/C；失败自动重试×3+旧文件兜底，不拖垮全流程。手动等价：指数/个股/持仓/K线(MA5/MA20/RSI/MACD/量比，缺口标 DATA_INCOMPLETE)；`portfolio.json` Decimal 精确；深层 `deep.py`；可选 `adanos.py` 四社群情绪写 `facts.sentiment`（缺 key 标 skipped 不阻断）；freshness（开盘>5分 STALE，>15分 DATA_INCOMPLETE 停决策）。

**Gate B · 价值组独立** — 巴菲特→段永平→芒格→李录，各带 1 句逆向"什么情况下我错"（段永平含镜子测试 ≤5 句说清生意）；禁 MA/RSI/量比。**必引** `financial_rigor` 精算：PE/ROE/股息一致性 + 三情景中性价。

**Gate C · Trading 组独立** — 技术分析师→动量交易员→情绪分析师→风控官，各带 1 句反共识"聪明人为何反向"（风控含 Kelly 符号纪律）；禁 PE/ROE/EPS。**必引** `financial_rigor` 精算：量价交叉 + 三情景区间作为支撑/阻力技术依据之一；美股情绪分析师必引 `adanos.py`（Reddit/X/News/Polymarket 的 buzz/mentions/多空比/trend_history），无 `ADANOS_KEY` 或 A 股降级 `deep.py north/flow`。

**Gate D · 交叉验证** — 共识点/分歧点/冲突点/取舍 + 反共识检查；价位双依据（价值=中性情景价+技术=均线/量价交叉支撑位）。

**Gate E · 综合决策+准出** — 四档：V≥4&T≥4 买入 / V≥3.5&T≥3 持有 / 任一否决→否决 / 其余灰色地带（合法留白）；随后 `validate_report.py` + `verify.py all` 两段校验，不过不得交付，结果写进数据质量栏。回测（`backtest.py`，支持 US/CN）为可选验证。

纪律：信息丰富度由 facts 字段齐全度定（A 反面检验/B 标置信度/C 转第一性原理）；8 条否决清单任一命中→灰色地带/否决。

## 3. 校验清单

- [ ] `data-gate/value-gate/trading-gate/cross-check/decision-gate` 齐全
- [ ] 8 Agent 标题齐全且 x/5，含逆向/反共识句
- [ ] 价值共识+Trading 共识+四项交叉齐全
- [ ] 操作建议四档之一，价位双依据

## 4. 报告层级

L1 现在做什么 → L2 短中期三窗口 → L3 现在发生什么（指数/组合/板块/事件/技术+freshness）→ L4 价值汇总→Trading 汇总→8 Agent 明细→交叉验证 → L5 历史复盘→风险与数据质量（含校验结果）→ 最终总结。移动端零横溢，每图配文字。
