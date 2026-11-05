#!/usr/bin/env python3
"""回测工具 v3 — 支持 CN/US，可选验证（不单独成 Gate），结果进数据质量栏。"""
import sys, json, os, argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cn_market import CNMarketData
from technical_indicators import TechnicalIndicators, KLine


class BacktestEngine:
    def __init__(self, code: str, start_date: str, end_date: str, market: str = "CN", initial_capital: float = 100000):
        self.code = code
        self.market = market
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.data = CNMarketData()

    def run(self):
        # US 前缀兼容：usAAPL / AAPL 均可，market=US 时自动处理
        kline_code = self.code
        if self.market == "US" and not self.code.lower().startswith("us"):
            kline_code = "us" + self.code
        # 统一走 kline 接口，自动 baostock/Yahoo 兜底
        try:
            klines = self.data.get_kline(kline_code, market=self.market, period="101")
        except TypeError:
            klines = self.data.get_kline(kline_code)
        filtered = [k for k in klines if self.start_date <= k['date'] <= self.end_date]
        if len(filtered) < 20:
            return {"error": "数据不足，无法回测", "code": self.code, "market": self.market}
        for i in range(20, len(filtered)):
            window = filtered[max(0, i-60):i]
            k_lines = [KLine(k['date'], k['open'], k['high'], k['low'], k['close'], k['volume']) for k in window]
            if len(k_lines) < 20:
                continue
            ti = TechnicalIndicators(k_lines)
            analysis = ti.analyze()
            current_price = filtered[i]['close']
            signal = self._generate_signal(analysis, current_price)
            lot = 1 if self.market == "US" else 100
            if signal == 'buy' and self.position == 0:
                shares = int(self.capital / current_price / lot) * lot
                if shares > 0:
                    self.capital -= shares * current_price
                    self.position = shares
                    self.trades.append({'date': filtered[i]['date'], 'action': 'buy', 'price': current_price, 'shares': shares, 'capital': round(self.capital, 2)})
            elif signal == 'sell' and self.position > 0:
                self.capital += self.position * current_price
                self.trades.append({'date': filtered[i]['date'], 'action': 'sell', 'price': current_price, 'shares': self.position, 'capital': round(self.capital, 2)})
                self.position = 0
        final_value = self.capital + self.position * filtered[-1]['close']
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        return {
            'code': self.code, 'market': self.market,
            'start_date': self.start_date, 'end_date': self.end_date,
            'initial_capital': self.initial_capital,
            'final_value': round(final_value, 2),
            'total_return': round(total_return, 2),
            'max_drawdown': round(self._calculate_max_drawdown(filtered), 2),
            'trade_count': len(self.trades),
            'win_rate': round(self._calculate_win_rate(), 2),
            'trades': self.trades
        }

    def _generate_signal(self, analysis, price):
        score = 0
        if analysis.get('trend') == 'bullish': score += 1
        elif analysis.get('trend') == 'bearish': score -= 1
        if analysis.get('golden_cross'): score += 1
        elif analysis.get('death_cross'): score -= 1
        if analysis.get('rsi_status') == 'oversold': score += 1
        elif analysis.get('rsi_status') == 'overbought': score -= 1
        latest = analysis.get('latest', 0)
        try:
            if price < analysis['boll']['lower'][latest]: score += 1
            elif price > analysis['boll']['upper'][latest]: score -= 1
        except Exception:
            pass
        if score >= 3: return 'buy'
        if score <= -3: return 'sell'
        return 'hold'

    def _calculate_max_drawdown(self, klines):
        max_value = self.initial_capital
        max_dd = 0
        for k in klines:
            cur = self.capital + self.position * k['close']
            if cur > max_value: max_value = cur
            dd = (max_value - cur) / max_value * 100 if max_value else 0
            if dd > max_dd: max_dd = dd
        return max_dd

    def _calculate_win_rate(self):
        if len(self.trades) < 2: return 0
        wins = total = 0
        for i in range(0, len(self.trades)-1, 2):
            if self.trades[i]['action'] == 'buy' and self.trades[i+1]['action'] == 'sell':
                if self.trades[i+1]['price'] > self.trades[i]['price']: wins += 1
                total += 1
        return wins / total * 100 if total else 0

def main():
    p = argparse.ArgumentParser(description="Gushen backtest — Gate G")
    p.add_argument("code", help="股票代码，如 600519 或 AAPL")
    p.add_argument("--start", dest="start", default="2024-01-01")
    p.add_argument("--end", dest="end", default="2024-12-31")
    p.add_argument("--market", default=None, choices=["CN", "US"], help="市场，默认 CN（us 前缀自动判 US）")
    p.add_argument("--capital", type=float, default=100000)
    args = p.parse_args()
    market = args.market or ("US" if args.code.lower().startswith("us") or args.code.isalpha() else "CN")
    code = args.code[2:] if market == "US" and args.code.lower().startswith("us") else args.code
    engine = BacktestEngine(code, args.start, args.end, market=market, initial_capital=args.capital)
    print(json.dumps(engine.run(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
