> **路径约定**：本文件里 `$SKILLS` = 技能根目录。执行前先解析：
> `SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills`
> （UG/本机命中 `~/.agents/skills`，Minis 命中 `/var/minis/skills`。）

# Gushen 事件盘与财报日历

## 事件盘（Earnings Calendar）

Gushen 集成财报日历数据，用于识别事件驱动的交易机会。

### 数据源

| 数据源 | 覆盖市场 | 免费额度 | 备注 |
|--------|---------|---------|------|
| Finnhub API | 美股 | 60次/分钟 | 已配置，无需额外申请 |
| 东方财富 API | A股 | 无限制 | 网页抓取/API |

### 美股财报日历（Finnhub）

```bash
# 获取本周财报日历（通过环境变量 FINNHUB_KEY）
curl -s "https://finnhub.io/api/v1/calendar/earnings?from=$(date +%Y-%m-%d)&to=$(date -d '+7 days' +%Y-%m-%d)&token=$FINNHUB_KEY"
```

### A股财报日历（东方财富）

```bash
# 通过东方财富网页抓取
python3 $SKILLS/gushen/tools/cn_market.py earnings
```

### 事件驱动交易逻辑

当检测到以下事件时，LLM 结合多 Agent 分析给出交易建议：

| 事件类型 | 时间窗口 | 策略 |
|---------|---------|------|
| 财报发布（BMO） | 盘前1天-盘后1天 | 若预期超预期，盘前布局；若预期不及，规避 |
| 财报发布（AMC） | 盘后1天-次日盘前 | 盘后交易/次日开盘反应 |
| 政策发布 | 发布前1周-发布后3天 | 提前布局受益板块，发布后兑现 |
| 行业会议 | 会议前3天-会议后1天 | 关注催化剂量能变化 |
| 极端行情 | 当日 | 趋势延续/反转判断 |

## 美股与 A 股区分规则

### 数据源分离

| 维度 | 美股 | A 股 |
|------|------|------|
| 实时行情 | 腾讯财经 + Finnhub quote | 腾讯财经 + baostock 实时 |
| K 线数据 | Alpha Vantage（日 K） | baostock / 东方财富（日/周/月 K） |
| 财报日历 | Finnhub earnings calendar | 东方财富网页抓取 |
| 涨跌颜色 | 国际惯例：绿涨红跌 | A 股习惯：红涨绿跌 |
| 估值指标 | PS 替代 PE（科技股） | 传统 PE/PB/ROE |
| 资金面 | 机构持仓/ARK 变动 | 北向资金/龙虎榜/融资融券 |
| 交易时间 | 美东 9:30–16:00，盘前盘后 | 9:30–11:30 / 13:00–15:00（无盘后） |
| 汇率风险 | USD 计价 | 中概股需考虑 USD/CNY |

### 分析框架分离

- **美股**：优先 PS 估值、FCF、回购/股权激励、AI/云化趋势
- **A 股**：优先 PE/PB/ROE、分红率、政策导向、行业周期

### 输出区分

- 美股标的：显示美东时间、USD 计价、Green=Up/Red=Down
- A 股标的：显示北京时间、CNY 计价、Red=Up/Green=Down

