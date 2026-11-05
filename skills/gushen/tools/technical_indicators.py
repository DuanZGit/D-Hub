#!/usr/bin/env python3
"""
技术指标计算模块（纯Python实现，不依赖ta-lib等重型库）
支持：MA、EMA、MACD、RSI、KDJ、布林带、成交量均线
"""

import json
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class KLine:
    """K线数据"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class TechnicalIndicators:
    """技术指标计算器"""
    
    def __init__(self, klines: List[KLine]):
        """
        Args:
            klines: K线数据列表，按时间正序排列
        """
        self.klines = klines
        self.closes = [k.close for k in klines]
        self.highs = [k.high for k in klines]
        self.lows = [k.low for k in klines]
        self.volumes = [k.volume for k in klines]
        self.dates = [k.date for k in klines]
    
    def ma(self, period: int) -> List[float]:
        """移动平均线 (MA)"""
        result = [None] * len(self.closes)
        for i in range(period - 1, len(self.closes)):
            result[i] = sum(self.closes[i - period + 1:i + 1]) / period
        return result
    
    def ema(self, period: int) -> List[float]:
        """指数移动平均线 (EMA)"""
        result = [None] * len(self.closes)
        multiplier = 2 / (period + 1)
        
        # 第一个EMA值用SMA
        if len(self.closes) >= period:
            result[period - 1] = sum(self.closes[:period]) / period
            for i in range(period, len(self.closes)):
                result[i] = (self.closes[i] - result[i - 1]) * multiplier + result[i - 1]
        
        return result
    
    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
        """
        MACD指标
        Returns:
            {
                'dif': DIF线 (快线),
                'dea': DEA线 (慢线/信号线),
                'macd': MACD柱状图 (DIF-DEA)*2
            }
        """
        ema_fast = self.ema(fast)
        ema_slow = self.ema(slow)
        
        # DIF = EMA快 - EMA慢
        dif = [None] * len(self.closes)
        for i in range(len(self.closes)):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                dif[i] = ema_fast[i] - ema_slow[i]
        
        # DEA = DIF的EMA
        dea = [None] * len(self.closes)
        valid_dif = [(i, v) for i, v in enumerate(dif) if v is not None]
        if len(valid_dif) >= signal:
            start_idx = valid_dif[signal - 1][0]
            dea[start_idx] = sum(v for _, v in valid_dif[:signal]) / signal
            for idx in range(start_idx + 1, len(self.closes)):
                prev_idx = idx - 1
                if dea[prev_idx] is not None and dif[idx] is not None:
                    dea[idx] = (dif[idx] - dea[prev_idx]) * (2 / (signal + 1)) + dea[prev_idx]
        
        # MACD柱 = (DIF - DEA) * 2
        macd = [None] * len(self.closes)
        for i in range(len(self.closes)):
            if dif[i] is not None and dea[i] is not None:
                macd[i] = (dif[i] - dea[i]) * 2
        
        return {'dif': dif, 'dea': dea, 'macd': macd}
    
    def rsi(self, period: int = 14) -> List[float]:
        """相对强弱指标 (RSI)"""
        result = [None] * len(self.closes)
        if len(self.closes) < period + 1:
            return result
        
        gains = []
        losses = []
        
        for i in range(1, len(self.closes)):
            change = self.closes[i] - self.closes[i - 1]
            gains.append(max(0, change))
            losses.append(max(0, -change))
        
        # 第一个RSI用SMA
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        if avg_loss == 0:
            result[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[period] = 100 - (100 / (1 + rs))
        
        # 后续用EMA平滑
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                result[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                result[i + 1] = 100 - (100 / (1 + rs))
        
        return result
    
    def kdj(self, n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, List[float]]:
        """
        KDJ随机指标
        Args:
            n: RSV周期，默认9
            m1: K值平滑周期，默认3
            m2: D值平滑周期，默认3
        """
        k_values = [None] * len(self.closes)
        d_values = [None] * len(self.closes)
        j_values = [None] * len(self.closes)
        
        rsv_list = [None] * len(self.closes)
        
        for i in range(n - 1, len(self.closes)):
            high_n = max(self.highs[i - n + 1:i + 1])
            low_n = min(self.lows[i - n + 1:i + 1])
            
            if high_n == low_n:
                rsv_list[i] = 50.0
            else:
                rsv_list[i] = (self.closes[i] - low_n) / (high_n - low_n) * 100
        
        # K = SMA(RSV, m1)
        # D = SMA(K, m2)
        # J = 3*K - 2*D
        
        valid_rsv = [(i, v) for i, v in enumerate(rsv_list) if v is not None]
        if len(valid_rsv) >= m1:
            start_idx = valid_rsv[m1 - 1][0]
            k_values[start_idx] = sum(v for _, v in valid_rsv[:m1]) / m1
            for idx in range(start_idx + 1, len(self.closes)):
                prev_idx = idx - 1
                if k_values[prev_idx] is not None and rsv_list[idx] is not None:
                    k_values[idx] = (2 * k_values[prev_idx] + rsv_list[idx]) / 3
        
        valid_k = [(i, v) for i, v in enumerate(k_values) if v is not None]
        if len(valid_k) >= m2:
            start_idx = valid_k[m2 - 1][0]
            d_values[start_idx] = sum(v for _, v in valid_k[:m2]) / m2
            for idx in range(start_idx + 1, len(self.closes)):
                prev_idx = idx - 1
                if d_values[prev_idx] is not None and k_values[idx] is not None:
                    d_values[idx] = (2 * d_values[prev_idx] + k_values[idx]) / 3
        
        for i in range(len(self.closes)):
            if k_values[i] is not None and d_values[i] is not None:
                j_values[i] = 3 * k_values[i] - 2 * d_values[i]
        
        return {'k': k_values, 'd': d_values, 'j': j_values}
    
    def bollinger(self, period: int = 20, std_dev: float = 2.0) -> Dict[str, List[float]]:
        """
        布林带 (Bollinger Bands)
        Returns:
            {
                'upper': 上轨 (MA + std_dev * std),
                'middle': 中轨 (MA),
                'lower': 下轨 (MA - std_dev * std)
            }
        """
        middle = self.ma(period)
        upper = [None] * len(self.closes)
        lower = [None] * len(self.closes)
        
        for i in range(period - 1, len(self.closes)):
            slice_prices = self.closes[i - period + 1:i + 1]
            std = (sum((x - middle[i]) ** 2 for x in slice_prices) / period) ** 0.5
            upper[i] = middle[i] + std_dev * std
            lower[i] = middle[i] - std_dev * std
        
        return {'upper': upper, 'middle': middle, 'lower': lower}
    
    def volume_ma(self, period: int = 5) -> List[float]:
        """成交量移动平均"""
        result = [None] * len(self.volumes)
        for i in range(period - 1, len(self.volumes)):
            result[i] = sum(self.volumes[i - period + 1:i + 1]) / period
        return result
    
    def analyze(self) -> Dict[str, Any]:
        """
        完整技术分析
        Returns:
            包含所有指标的分析结果
        """
        macd = self.macd()
        kdj = self.kdj()
        boll = self.bollinger()
        
        # 最新值
        latest = len(self.closes) - 1
        
        # 趋势判断
        ma5 = self.ma(5)
        ma20 = self.ma(20)
        
        trend = "neutral"
        if ma5[latest] and ma20[latest]:
            if ma5[latest] > ma20[latest]:
                trend = "bullish"
            else:
                trend = "bearish"
        
        # 金叉死叉判断
        golden_cross = False
        death_cross = False
        
        if latest > 0 and macd['dif'] and macd['dea']:
            if macd['dif'][latest] and macd['dea'][latest]:
                if macd['dif'][latest - 1] and macd['dea'][latest - 1]:
                    if macd['dif'][latest - 1] < macd['dea'][latest - 1] and macd['dif'][latest] > macd['dea'][latest]:
                        golden_cross = True
                    elif macd['dif'][latest - 1] > macd['dea'][latest - 1] and macd['dif'][latest] < macd['dea'][latest]:
                        death_cross = True
        
        # 超买超卖判断
        rsi = self.rsi()
        rsi_status = "neutral"
        if rsi[latest]:
            if rsi[latest] > 70:
                rsi_status = "overbought"
            elif rsi[latest] < 30:
                rsi_status = "oversold"
        
        return {
            'dates': self.dates,
            'closes': self.closes,
            'ma5': ma5,
            'ma20': ma20,
            'macd': macd,
            'rsi': rsi,
            'kdj': kdj,
            'boll': boll,
            'volume_ma5': self.volume_ma(5),
            'trend': trend,
            'golden_cross': golden_cross,
            'death_cross': death_cross,
            'rsi_status': rsi_status,
            'latest': latest
        }
    
    def to_json(self) -> str:
        """导出JSON格式"""
        result = self.analyze()
        # 转换None为null
        return json.dumps(result, ensure_ascii=False, default=lambda x: None if x is None else x)


def main():
    """测试"""
    # 示例K线数据
    test_klines = [
        KLine("2024-01-01", 100, 105, 98, 102, 1000),
        KLine("2024-01-02", 102, 108, 101, 107, 1200),
        KLine("2024-01-03", 107, 110, 105, 108, 1100),
        KLine("2024-01-04", 108, 112, 106, 111, 1300),
        KLine("2024-01-05", 111, 115, 109, 114, 1400),
    ]
    
    ti = TechnicalIndicators(test_klines)
    print("MA5:", ti.ma(5))
    print("MACD:", ti.macd())
    print("RSI:", ti.rsi())
    print("KDJ:", ti.kdj())
    print("BOLL:", ti.bollinger())


if __name__ == "__main__":
    main()
