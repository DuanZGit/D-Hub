---
name: gushen
description: >
  股神 - 每日挂单 + 投研问答助手。
  继承 xbtlin/ai-berkshire 决策纪律（每 Agent 1 句逆向）+ 财务严谨性，效能最强。
  固定 8 Agent 统一 5 分制、Gate A-E、不并行但字符级隔离、精华操作优先。
  支持美股/A股实时行情、持仓管理、交易建议、个股研究、标的推荐。
version: 3.0.0
tags: [investment, A股, 美股, value-investing, daily-orders, research, multi-agent]
upstream:
  repo: https://github.com/xbtlin/ai-berkshire
  path: ""
  pin: d649f4c

---

> **路径约定**：本文件里 `$SKILLS` = 技能根目录。执行前先解析：
> `SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills`
> （UG/本机命中 `~/.agents/skills`，Minis 命中 `/var/minis/skills`。）

## 触发条件（硬边界）

**只有用户明确提到 `gushen` 或 `股神` 时，才激活 gushen。**
- 触发词：`gushen`、`股神`

**不触发 gushen 的情况：**
- 普通搜索/查资料 → 走 agent-reach
- 食谱/健康/生活技巧 → 走 DK
- 深度调研 → 走 research
- 即使用户问的是股票/行情/基金，只要没提 `gushen`/`股神`，就不触发 gushen

---

## 执行协议（唯一权威）

完整 `/gushen` 必须先读取并遵守：`references/execution-contract.md`（Gate A-E）。
本文件的流程说明不得与契约冲突，冲突以契约为准。

**硬门槛：** 每次完整分析必须出现且仅出现 8 个 Agent（统一 5 分制），缺一或分制错误即未完成。

| # | 角色 | 对齐上游 | 纪律职责（必出 1 句） |
|---|------|----------|----------------------|
| 1 | 巴菲特 | financial-analyst | 财务+估值，必市值验算 |
| 2 | 段永平 | business-analyst | 商业模式 + 镜子测试 |
| 3 | 芒格 | industry-researcher | 护城河 + 逆向检验 |
| 4 | 李录 | risk-assessor | 长期确定性 + 10年终局 |
| 5 | 技术分析师 | — | 趋势+支撑阻力 |
| 6 | 动量交易员 | — | 量价+突破 + 反共识 |
| 7 | 情绪分析师 | — | 资金流+拥挤度 + 反共识 |
| 8 | 风控官 | — | 仓位+Kelly符号+否决权 |

**纪律（效能来源，ai-berkshire）：** 每 Agent 末句 1 句逆向/反共识（价值组"什么情况下我错"，Trading 组"聪明人为何反向"）；灰色地带是合法结论，不硬给价位。

详见：`references/execution-contract.md`。

> Price is what you pay, value is what you get. — Warren Buffett

## 报告视觉规范（唯一风格）

所有 HTML 报告必须直接套用 `templates/daily_report.html` v4 lean，不得回退旧版或自创设计。

- **设计定位**：移动金融研究简报，`DESIGN_VARIANCE 5 / MOTION_INTENSITY 5 / VISUAL_DENSITY 6`。
- **主题**：暗色单主题 bg `#0b0e13` / surface `#12161f` / surface-2 `#171c27`。
- **强调色**：琥珀金 `#e8b04b` 单一，禁紫蓝渐变。
- **涨跌色**：红 `#ff4d5e`=涨/盈利；绿 `#00c767`=跌/亏损，全页锁死。
- **禁 emoji**：Agent 用姓氏方块，禁图标。
- **数字**：`.num` tabular-nums，字阶 11/13/15/26px，圆角 10px。
- **信息架构（精华优先）：** 现在做什么 → 短中期三窗口 → 现在发生什么（指数/组合/板块/事件/技术+freshness）→ 为什么（价值汇总→Trading 汇总→8 Agent 明细→交叉验证）→ 最后复盘（历史→风险/质量→总结）。
- **固定顺序**：masthead → gates A-E → 今日行动 → 短中期 → 市场状态 → 价值汇总 → Trading 汇总 → 8 Agent → 交叉验证 → 历史复盘 → 风险/质量 → 最终总结 → footer。
- **Three.js**：可选低功耗，必须有文字降级，不承载唯一事实。
- **外部依赖**：零 CDN，模板改动过 `validate_report.py`。

## 设计原则

- **数据用工作流**：`workflow.py` 单入口（幂等+重试+旧文件兜底），`growth/pe` 自动算不手填，精算前置直供 Agent
- **决策用纪律**：脚本不替决策，纪律（否决/镜子/逆向/反共识）由提示词+校验器强制。
- **独立判断不靠并行**：价值组禁 MA/RSI/量比/MACD/VIX，Trading 组禁 PE/ROE/EPS/股息，校验器字符级拦。
- **精华优先**：操作建议前置，纪律细节折叠，报告总长不因纪律而膨胀。
- **红涨绿跌 / 次日作废 / 移动端优先 / 先指数后个股 / 持仓必结合**（保持 v2）。

## 数据源

数据源与弹药映射见 `DATA_SOURCES.md`，命令 `tools/* --help`。

### 凭据接口（统一要求）

取 key 一律走 `scripts/load_key.sh`，禁止把 key 值写进本技能任何文件。查找顺序：`$环境变量 → ~/.config/agents/env（中央入口）→ 技能目录/.env → 缺失时报四要素错误`。

| 环境变量 | 服务 | 申请入口（免费额度） |
|---|---|---|
| `FINNHUB_KEY` | Finnhub 美股行情 | https://finnhub.io （免费 60 次/分） |
| `ADANOS_KEY` | Adanos 美股情绪（仅美股） | https://adanos.org/register （免费 250 次/月） |

用法：`FINNHUB_KEY=$(bash scripts/load_key.sh FINNHUB_KEY https://finnhub.io)`。外部用户缺 key 时按 stderr 引导自行申请（BYOK）；拿不到则降级 akshare/yfinance 免费源。

`ADANOS_KEY` 同理（`scripts/load_key.sh ADANOS_KEY https://adanos.org/register`）；不配则设 `ADANOS_NO_SENTIMENT=1` 显式跳过，情绪分析师自动降级东财/量价口径。Adanos 只覆盖美股 ticker，A 股情绪仍走 `deep.py north/flow`。

### 常用 CLI

```bash
python3 $SKILLS/gushen/tools/cn_market.py quote usGOOG usVZ
python3 $SKILLS/gushen/tools/cn_market.py a sh000001  # 先指数后个股
python3 $SKILLS/gushen/tools/deep.py fund GOOG
python3 $SKILLS/gushen/tools/adanos.py sentiment GOOG   # 美股四社群情绪（需 ADANOS_KEY）
python3 $SKILLS/gushen/tools/adanos.py market          # 全市场情绪
python3 $SKILLS/gushen/tools/financial_rigor.py verify-valuation --price 339 --eps 19.91 --bvps 34.5
python3 $SKILLS/gushen/tools/financial_rigor.py three-scenario --price 339 --eps 19.91 --shares 12.5 --growth 0.12 0.06 0.0 --pe 20 17 14
```

### A 股分析强制流程

1. 先查指数：`sh000001` `sz399001` `sz399006`（各一条命令）。
2. 描述大盘：禁止用个股推断大盘。
3. 再查个股 + 持仓 `portfolio.json` 精确浮盈亏。
4. 生成 HTML，含指数+持仓+8 Agent+两组共识+交叉+数据质量。

### 颜色规范

- 红 `#ff4d5e` 上涨/盈利，绿 `#00c767` 下跌/亏损，灰 `#e0e6ed` 中性。

## 多 Agent 报告生成规则（v3：统一 5 分制 + 独立隔离 + 逆向）

**关键约束：** 8 Agent 单次响应内完整输出，价值组与 Trading 组互相隔离。

### Agent 视角矩阵（统一 1-5 分）

| 视角 | 分析重点 | 必出内容 |
|------|---------|---------|
| 巴菲特 | 估值 | ROE/PE/PS/安全边际/FCF + 市值验算 + 1 句逆向，x/5 + 结论 |
| 段永平 | 模式理解 | 商业模式/用户价值/现金流/镜子测试 + 1 句逆向，x/5 + 结论 |
| 芒格 | 护城河 | 数据/平台/切换成本/网络效应/Commodity 识别 + 1 句逆向，x/5 + 结论 |
| 李录 | 长期趋势 | AI/自动化/云化/政策/终局 + 1 句逆向，x/5 + 结论 |
| 技术分析师 | 趋势 | MA/MACD/支撑阻力 + 1 句"若破位则错"，x/5 + 结论 |
| 动量交易员 | 动量 | 短期动量/突破/量价 + 1 句反共识，x/5 + 结论 |
| 情绪分析师 | 市场 | 成交量/换手/拥挤度 + Reddit/X/News/Polymarket 跨社群情绪(buzz/多空比) + 1 句反共识，x/5 + 结论 |
| 风控官 | 风险 | 集中度/回撤/beta/Kelly 符号 + 1 句否决权说明，x/5 + 结论 |

## 默认行为

### 阶段 1：数据获取（Gate A — `workflow.py` 单入口，含扫描）
```bash
python3 $SKILLS/gushen/tools/workflow.py               # 持仓+指数+自动扫描（现金>40% 才扫，否则跳过）
python3 $SKILLS/gushen/tools/workflow.py --force       # 强制重抓
python3 $SKILLS/gushen/tools/workflow.py --scan        # 强制扫描（不看现金）
python3 $SKILLS/gushen/tools/workflow.py --no-scan     # 只跑持仓，不扫描
python3 $SKILLS/gushen/tools/workflow.py --symbols GOOG NVDA  # 只抓指定
```
`workflow.py` 输出 `facts.json` 含 `scan{pool, screened[], caps, cash_ratio}`（初筛 10 只全量字段：报价/PE/ROE/量比/EPS surprise/评级）。等价手动：1. 指数/个股/持仓/K 线（A 股先三大指数）2. `portfolio.json` 浮盈亏/集中度 Decimal 精确 3. 深层 `fund/cnfund/north/volume/extras` + `financial_rigor` 自动精算（growth/pe 自动算）4. `dump_facts.py` 落盘 facts_YYYYMMDD.json 5. 新鲜度+双源核验。失败自动重试×3+旧文件兜底。

### 阶段 2：两套模型独立分析（Gate B/C，隔离）
- 价值组 4 Agent 独立（不看技术面，各带逆向句）→ 价值共识 V。
- Trading 组 4 Agent 独立（不看估值面，动量/情绪带反共识）→ Trading 共识 T。
- 触发新机会扫描时，候选标的同样走 B/C/D/E 全流程。

### 阶段 3：交叉验证 → 综合决策（Gate D/E，四档）
- Gate D：共识点/分歧点/冲突点/取舍 + 反共识检查。
- Gate E：综合决策（四档，留白合法）+ 双依据价位。
  - V=价值均分, T=Trading 均分（1-5）
  - 任一否决→否决；V≥4&T≥4→买入/加仓；V≥3.5&T≥3→持有；其余→灰色地带。


### 阶段 4：报告生成（Gate F 准出）
- 生成单文件 HTML（`templates/daily_report.html`）。
- `validate_report.py` + `verify.py all` 两段，未过不得交付，结果写入数据质量栏。
- 聊天只给摘要+文件链接，不贴全文。

### 新机会扫描规则（自动筛 + 按现金来 + 频率跟现金走）

触发（跟现金走，`workflow.py` 自动执行）：现金占比>40% → 每次日报自动扫；30-40% → 每周扫一次（周一）；<30% → 不主动扫，用户问才扫（`--scan` 可强制）。另：集中度>50% / 用户明确要求时也扫。
范围（自动筛，`workflow.py scan_pool()`）：MAG7 去重持仓 + QQQ 前十去重持仓 + 防御红利 2 只（JNJ/PG），`facts.json: scan{pool, screened[], caps}` 落盘 10 只初筛全量字段（报价/PE/ROE/量比/EPS surprise/评级），只对通过的 ≤2 只跑全量 Gate B/C/D。历史盈利>8/10 的旧标的优先回接。
仓位（按现金来，`workflow.py` 已算好 `scan.caps`）：单只新开仓 ≤ 现金的 1/4，且单票不超组合 10%；现金>40% 可同时开 ≤2 只，30-40% 只开 1 只。
流程：候选标的完整走 Gate A-E，全量 8 Agent 交叉验证，不满足标"不推荐"。
输出：名称/代码/现价/PE/PS/仓位/目标/止损/综合评分 + 各 Agent 摘要 + 操作计划 + 风险提示。

### 关键约束
1. 分析必须完整：8 Agent 在结论前完成。
2. 结论来自交叉验证：禁止先结论后补卡片。
3. 两套模型独立：字符级隔离，校验器拦。
4. 挂单价双依据：价值+技术交叉。
5. 生成前校验：`validate_report.py` 通过才给链接。
6. 不贴全文，术语加括号注释。

## A股推荐流程（固定 8 Agent，Gate A-E）

1. 数据收集：三大指数各一条命令 + 个股。
2. 8 Agent 独立分析（各带 1 句逆向/反共识）。
3. 交叉验证→综合决策（四档）。
4. 输出：HTML 含指数+持仓+8 Agent+两组共识+交叉+数据质量，缺一视为未完成。

## 子命令

### 技术分析 `/technical-analysis`

```
用户：帮我看看 [股票] 技术面怎么样
执行：K线→MA/MACD/RSI/KDJ/布林带→趋势/金叉死叉/超买超卖→评分x/5+操作建议
```

### 回测验证 `/backtest`

```bash
python3 $SKILLS/gushen/tools/backtest.py 600519 --start 2024-01-01 --end 2024-12-31
python3 $SKILLS/gushen/tools/backtest.py usAAPL --market US --start 2024-01-01 --end 2024-12-31
```

**输出**：`{code,total_return,max_drawdown,trade_count,win_rate,trades}`，可选验证，胜率<50%时降权一档。

## 自动化配置

```bash
minis-scheduled create --time 20:30 --prompt "/gushen" --label "美股盘前挂单" --repeat weekdays
```

**注意：** `minis-scheduled` 失败不通知，报告末尾加 `generated_at` 时间戳或设系统级 fallback。

## 版本历史

- **v3.1.0** (2026-09-25)：接入 Adanos 美股四社群情绪源 — `adanos.py`（Reddit/X/News/Polymarket buzz/多空比/trend）、`dump_facts.py` 自动写 `facts.sentiment`、`workflow.py` scan 带情绪字段、凭据 `ADANOS_KEY`（可 `ADANOS_NO_SENTIMENT=1` 跳过）；情绪/动量 Agent 弹药扩展，A 股口径不变
- **v3.0.0** (2026-09-03)：**精简重构——效能最强**
  - 吸收 ai-berkshire：每 Agent 末句 1 句逆向/反共识（prompt 约束，不靠字数执法）+ 财务严谨性；不取信息丰富度自动算/否决清单仪式化
  - 继承 ai-hedge-fund：`backtest.py` US/CN 双市场支持，为可选验证（不单独成 Gate）
  - 统一 5 分制（破环：旧 1-10 废止，决策矩阵重算四档）
  - 模板 v4 lean：删纪律/回测装饰区，精华前置不膨胀；契约 Gate 保持 A-E

- **v2.9.0** (2026-09-03)：数值可信度层（verify/dump_facts/Kelly 符号纪律）
- **v2.8.0** (2026-08-31)：先行动后解释信息架构 + Three.js 规范
- **v2.7.0** (2026-08-28)：行情时效性与 freshness 协议
- **v2.6.0** (2026-08-24)：premium 终端视觉规范
- **v2.5.0** (2026-08-24)：execution-contract 权威化 + 8 Agent 固定
- **v2.3.0** (2026-08-04)：移动端优先 + A 股强制流程
- **v2.2.0** (2026-07-30)：美股盘前 briefing + 财报日历

## 相关项目

- [ai-berkshire](https://github.com/xbtlin/ai-berkshire) - 价值投资框架（逆向纪律来源）
- [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) - AI对冲基金系统（回测工具参考）

## 详细文档

| 文档 | 什么时候读 |
|------|-----------|
| [references/execution-contract.md](references/execution-contract.md) | 每次 `/gushen` 必读（Gate A-E 契约） |
| [references/report-template.md](references/report-template.md) | 生成完整报告时（已精简为决策矩阵+层级，750 行 HTML 示例已删） |

