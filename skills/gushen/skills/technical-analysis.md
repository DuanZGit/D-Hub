---
name: technical-analysis
description: >
  技术分析 skill。计算 MA/MACD/RSI/KDJ/布林带等经典指标，
  识别趋势、支撑/阻力、背离信号。基于纯Python实现，不依赖ta-lib。
triggers:
  - "技术分析"
  - "K线分析"
  - "MACD"
  - "RSI"
  - "布林带"
  - "支撑阻力"
  - "technical-analysis"
  - "趋势判断"
  - "金叉死叉"
---

> **路径约定**：本文件里 `$SKILLS` = 技能根目录。执行前先解析：
> `SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills`
> （UG/本机命中 `~/.agents/skills`，Minis 命中 `/var/minis/skills`。）

# 技术分析

## 触发条件

当用户提到以下场景时，使用此 skill：
- "帮我看看 [股票] 技术面怎么样"
- "[股票] 的 MACD/RSI 是多少？"
- "[股票] 现在是什么趋势？"
- "支撑位和阻力位在哪里？"
- 需要判断买卖时机

## 数据获取

```bash
# 获取K线数据
python3 $SKILLS/gushen/tools/cn_market.py kline 600519 --market CN
python3 $SKILLS/gushen/tools/cn_market.py kline 600519 --period 102  # 周K
```

## 指标计算

```python
from tools.technical_indicators import TechnicalIndicators, KLine

# 构造K线数据
klines = [
    KLine("2024-01-01", 100, 105, 98, 102, 1000),
    KLine("2024-01-02", 102, 108, 101, 107, 1200),
    ...
]

# 计算指标
ti = TechnicalIndicators(klines)

# 移动平均
ma5 = ti.ma(5)
ma20 = ti.ma(20)

# MACD
macd = ti.macd()  # dif, dea, macd

# RSI
rsi = ti.rsi(14)

# KDJ
kdj = ti.kdj()  # k, d, j

# 布林带
boll = ti.bollinger(20, 2)  # upper, middle, lower

# 完整分析
analysis = ti.analyze()
```

## 输出格式

```
## 技术分析报告：[公司名] ([代码])

### 趋势判断
- 长期趋势：[强势上涨 / 震荡 / 下跌]
- 中期趋势：[强势 / 弱势 / 中性]
- 短期趋势：[买入信号 / 卖出信号 / 观望]

### 关键指标
| 指标 | 当前值 | 信号 | 强度 |
|------|--------|------|------|
| MA5 | X | 金叉 | ⭐⭐⭐⭐ |
| MA20 | X | 多头排列 | ⭐⭐⭐⭐⭐ |
| MACD | 金叉 | 买入 | ⭐⭐⭐⭐ |
| RSI(14) | 58 | 中性 | ⭐⭐⭐ |
| KDJ | 45 | 中性 | ⭐⭐⭐ |
| BOLL | 中轨上方 | 偏多 | ⭐⭐⭐ |

### 支撑/阻力位
| 类型 | 价位 | 说明 |
|------|------|------|
| 阻力位1 | 1700 | 前期高点 |
| 阻力位2 | 1750 | 整数关口+布林上轨 |
| 支撑位1 | 1650 | MA20 |
| 支撑位2 | 1600 | 前期低点 |

### 背离信号
- [ ] 顶背离
- [ ] 底背离
- [ ] 无背离

### 成交量分析
- 最近5日均量：XXX
- 量比：X.X
- 量价配合：[良好 / 一般 / 背离]

### 综合判断
**技术面评分**：X/5

**结论**：[买入 / 持有 / 观望 / 卖出]

**关键观察点**：
1. [观察点1]
2. [观察点2]
```

## 使用示例

```bash
/technical-analysis --ticker AAPL --market US
/technical-analysis --ticker 600519 --market CN
```

## 注意事项

1. **技术分析是概率游戏**，没有100%准确的指标
2. **必须结合基本面**，技术面好的公司不一定值得买
3. **大环境优先**：牛市做多，熊市做空，震荡市高抛低吸
4. **避免过度交易**：不是每个信号都要操作
