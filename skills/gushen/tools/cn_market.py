#!/usr/bin/env python3
"""
国内财经数据获取工具（不依赖墙外节点）
数据源优先级：
  1. stock-prices.on99.app（JSON API，字段最全）
  2. 腾讯财经 API（GBK，稳定）
  3. 新浪财经 API（GBK，备用）
支持：A股、美股、港股、指数
"""

import os
import urllib.request
import urllib.parse
import time
import urllib.error
import json
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

try:
    import baostock as bs
    BAOSTOCK_AVAILABLE = True
except ImportError:
    BAOSTOCK_AVAILABLE = False


class CNMarketData:
    """国内财经数据获取器"""
    
    def __init__(self):
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.cache_ttl = 5  # 秒
    
    def _get_cache(self, key: str) -> Optional[Any]:
        if key in self.cache:
            data, ts = self.cache[key]
            if (datetime.now() - ts).total_seconds() < self.cache_ttl:
                return data
        return None
    
    def _set_cache(self, key: str, value: Any):
        self.cache[key] = (value, datetime.now())
    
    def _tencent_request(self, symbols: List[str]) -> str:
        """腾讯财经 API 请求"""
        url = f"https://qt.gtimg.cn/q={','.join(symbols)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.qq.com/'
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('gbk')
    
    def _stock_prices_request(self, symbols: List[str]) -> str:
        """stock-prices.on99.app API 请求"""
        url = f"https://stock-prices.on99.app/quotes?symbols={','.join(symbols)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('utf-8')
    
    def _parse_stock_prices(self, raw: str) -> List[Dict[str, Any]]:
        """解析 stock-prices API 响应"""
        try:
            data = json.loads(raw)
            results = []
            for item in data.get('quotes', []):
                results.append({
                    'source': 'stock-prices',
                    'symbol': item.get('symbol', ''),
                    'name': item.get('name', ''),
                    'price': str(item.get('currentPrice', '')),
                    'prev_close': str(item.get('previousClosePrice', '')),
                    'open': str(item.get('openPrice', '')),
                    'volume': str(item.get('volume', '')),
                    'change': str(item.get('change', '')),
                    'change_pct': str(item.get('percentChange', '')),
                    'high': str(item.get('highPrice', '')),
                    'low': str(item.get('lowPrice', '')),
                    'time': item.get('regularMarketTime', ''),
                    'market_cap': str(item.get('marketCap', '')),
                    'pe': str(item.get('forwardPE', '')),
                    'pb': str(item.get('priceToBook', '')),
                    'dividend_yield': str(item.get('dividendYield', '')),
                })
            return results
        except Exception as e:
            print(f"[stock-prices] 解析失败: {e}")
            return []
    
    def _sina_request(self, symbols: List[str]) -> str:
        """新浪财经 API 请求（备用）"""
        # 新浪美股格式：gb_<代码>
        # 新浪A股格式：sh_<代码> / sz_<代码>
        sina_symbols = []
        for s in symbols:
            if s.startswith('us'):
                sina_symbols.append(f"gb_{s[2:]}")
            elif s.startswith('sh') or s.startswith('sz'):
                sina_symbols.append(s)
            else:
                sina_symbols.append(f"gb_{s}")
        
        url = f"https://hq.sinajs.cn/list={','.join(sina_symbols)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.sina.com.cn/'
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('gbk')
    
    def _parse_tencent(self, raw: str) -> List[Dict[str, Any]]:
        """解析腾讯财经响应"""
        results = []
        for line in raw.strip().split(';'):
            line = line.strip()
            if not line or '=' not in line:
                continue
            parts = line.split('=', 1)[1].strip('"').split('~')
            if len(parts) < 35:
                continue
            
            results.append({
                'source': 'tencent',
                'symbol': parts[2],
                'name': parts[1],
                'price': parts[3],
                'prev_close': parts[4],
                'open': parts[5],
                'volume': parts[6],
                'change': parts[31],
                'change_pct': parts[32],
                'high': parts[33],
                'low': parts[34],
                'time': parts[30],
                'market_cap': parts[45] if len(parts) > 45 else '',
                'pe': parts[39] if len(parts) > 39 else '',
                'pb': parts[43] if len(parts) > 43 else '',
            })
        return results
    
    def _parse_sina(self, raw: str) -> List[Dict[str, Any]]:
        """解析新浪财经响应"""
        results = []
        for line in raw.strip().split('\n'):
            line = line.strip()
            if not line or '=' not in line:
                continue
            var_name, value = line.split('=', 1)
            value = value.strip('"')
            parts = value.split(',')
            
            if len(parts) < 10:
                continue
            
            # 美股格式：名称,今开,昨收,当前价,最高,最低,时间,...
            # A股格式：名称,今开,昨收,当前价,最高,最低,日期,时间,...
            results.append({
                'source': 'sina',
                'symbol': var_name.replace('var hq_str_', ''),
                'name': parts[0],
                'price': parts[3],
                'prev_close': parts[2],
                'open': parts[1],
                'high': parts[4],
                'low': parts[5],
                'volume': '',
                'change': '',
                'change_pct': '',
                'time': parts[6] + ' ' + parts[7] if len(parts) > 7 else parts[6],
                'market_cap': '',
                'pe': '',
                'pb': '',
            })
        return results
    
    def get_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        """
        批量获取行情（国内优先）
        
        Args:
            symbols: 股票代码列表
                - 美股：GOOG, AAPL, NVDA
                - A股：sh000001, sz399001, sh600519
                - 港股：hk00700, hk09988
        
        Returns:
            行情数据字典
        """
        cache_key = f"quotes:{','.join(symbols)}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached
        
        # 尝试 stock-prices API（主要，字段最全）
        try:
            raw = self._stock_prices_request(symbols)
            results = self._parse_stock_prices(raw)
            if results:
                self._set_cache(cache_key, {'data': results, 'source': 'stock-prices'})
                return {'data': results, 'source': 'stock-prices'}
        except Exception as e:
            print(f"[stock-prices] 获取失败: {e}")
        
        # 尝试腾讯（备用）
        try:
            raw = self._tencent_request(symbols)
            results = self._parse_tencent(raw)
            if results:
                self._set_cache(cache_key, {'data': results, 'source': 'tencent'})
                return {'data': results, 'source': 'tencent'}
        except Exception as e:
            print(f"[tencent] 获取失败: {e}")
        
        # 尝试新浪（兜底）
        try:
            raw = self._sina_request(symbols)
            results = self._parse_sina(raw)
            if results:
                self._set_cache(cache_key, {'data': results, 'source': 'sina'})
                return {'data': results, 'source': 'sina'}
        except Exception as e:
            print(f"[sina] 获取失败: {e}")
        
        return {'data': [], 'source': 'none', 'error': '所有数据源均失败'}
    
    def get_us_quote(self, ticker: str) -> Dict[str, Any]:
        """获取美股实时行情"""
        symbols = [f"us{ticker}"]
        result = self.get_quotes(symbols)
        if result['data']:
            return result['data'][0]
        return {'error': '获取失败', 'ticker': ticker}
    
    def get_a_share_quote(self, code: str) -> Dict[str, Any]:
        """获取A股实时行情"""
        # 自动判断市场
        if code.startswith('6') or code.startswith('sh'):
            symbol = f"sh{code}" if code.isdigit() else code
        elif code.startswith('0') or code.startswith('3') or code.startswith('sz'):
            symbol = f"sz{code}" if code.isdigit() else code
        else:
            symbol = code
        
        result = self.get_quotes([symbol])
        if result['data']:
            return result['data'][0]
        return {'error': '获取失败', 'code': code}
    
    def get_index(self, code: str) -> Dict[str, Any]:
        """获取指数行情"""
        result = self.get_quotes([code])
        if result['data']:
            return result['data'][0]
        return {'error': '获取失败', 'code': code}
    
    def get_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        """批量快照"""
        return self.get_quotes(symbols)
    
    def get_kline(self, code: str, market: str = "CN", period: str = "101") -> List[Dict[str, Any]]:
        """
        获取K线数据
        
        Args:
            code: 股票代码
            market: 市场 "CN" 或 "US"
            period: K线周期
                "101" = 日K
                "102" = 周K
                "103" = 月K
                "1"   = 1分钟
                "5"   = 5分钟
                "15"  = 15分钟
                "30"  = 30分钟
                "60"  = 60分钟
        
        Returns:
            K线数据列表
        """
        cache_key = f"kline:{market}:{code}:{period}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached
        
        result = []
        
        if market == "CN":
            # A股K线：东方财富优先，失败回落 baostock（2026-09-03 接入）
            result = self._kline_cn_baostock(code, period)
            if result:
                self._set_cache(cache_key, result)
                return result
            # A股使用东方财富K线API
            # secid: 1=深圳 0=上海
            if code.startswith('6'):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"
            
            url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                   f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
                   f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                   f"&klt={period}&fqt=0&beg=20240101&end=20271231")
            
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://finance.eastmoney.com/'
                })
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode('utf-8'))
                    klines = data.get('data', {}).get('klines', [])
                    
                    for line in klines:
                        parts = line.split(',')
                        if len(parts) >= 7:
                            result.append({
                                'date': parts[0],
                                'open': float(parts[1]),
                                'close': float(parts[2]),
                                'high': float(parts[3]),
                                'low': float(parts[4]),
                                'volume': float(parts[5]),
                                'amount': float(parts[6]) if len(parts) > 6 else 0,
                            })
                    
                    self._set_cache(cache_key, result)
                    return result
            except Exception as e:
                print(f"[eastmoney kline] 获取失败: {e}")
        
        elif market == "US":
            # 美股K线：优先 Alpha Vantage，备用 yfinance
            symbol = code.upper()
            if symbol.startswith('US'):
                symbol = symbol[2:]
            
            # Alpha Vantage（免费 tier：25次/天，5次/分钟）
            try:
                av_key = os.environ.get('ALPHA_VANTAGE_KEY', '')
                if not av_key:
                    raise RuntimeError('ALPHA_VANTAGE_KEY not set')
                url = (f"https://www.alphavantage.co/query?"
                       f"function=TIME_SERIES_DAILY&symbol={symbol}&apikey={av_key}")
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://www.alphavantage.co/'
                })
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode('utf-8'))
                    ts = data.get('Time Series (Daily)', {})
                    for date, item in sorted(ts.items()):
                        result.append({
                            'date': date,
                            'open': float(item.get('1. open', 0)),
                            'close': float(item.get('4. close', 0)),
                            'high': float(item.get('2. high', 0)),
                            'low': float(item.get('3. low', 0)),
                            'volume': float(item.get('5. volume', 0)),
                            'amount': 0,
                        })
                    if result:
                        self._set_cache(cache_key, result)
                        return result
            except Exception as e:
                print(f"[alphavantage kline] 获取失败: {e}")

            # Yahoo V8 备用（免费无 Key，2026-09-03 接入）
            try:
                ysym = symbol if '.' in symbol else symbol
                s = self._yahoo_chart(ysym, range_='6mo', interval='1d')
                result = s
                self._set_cache(cache_key, result)
                return result
            except Exception as e:
                print(f"[yahoo kline] 获取失败: {e}")
            
            # 磁盘缓存回退：当天已成功获取过则复用
            try:
                cache_file = os.path.join(os.path.expanduser('~'), '.gushen_cache', f'{symbol}_kline.json')
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        cached = json.load(f)
                    if cached.get('date') == datetime.now().strftime('%Y-%m-%d'):
                        result = cached.get('data', [])
                        if result:
                            print(f"[cache] 使用缓存 K 线: {symbol} ({len(result)} 条)")
                            return result
            except Exception as e:
                print(f"[cache] 读取缓存失败: {e}")
            
            # yfinance 备用
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='3mo')
                if not hist.empty:
                    for idx, row in hist.iterrows():
                        result.append({
                            'date': idx.strftime('%Y-%m-%d'),
                            'open': float(row['Open']),
                            'close': float(row['Close']),
                            'high': float(row['High']),
                            'low': float(row['Low']),
                            'volume': float(row['Volume']),
                            'amount': 0,
                        })
                    if result:
                        self._set_cache(cache_key, result)
                        # 同时写入磁盘缓存
                        try:
                            os.makedirs(os.path.join(os.path.expanduser('~'), '.gushen_cache'), exist_ok=True)
                            with open(cache_file, 'w') as f:
                                json.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'data': result}, f)
                        except Exception:
                            pass
                        return result
            except Exception as e:
                print(f"[yfinance kline] 获取失败: {e}")
        
        return result
    

    @staticmethod
    def _yahoo_chart(sym: str, range_: str = "6mo", interval: str = "1d"):
        """Yahoo V8 chart 接口，返回与 get_kline 相同结构；sym 支持 ^VIX/^TNX/GOOG/000001.SS"""
        import urllib.request as _u
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
               f"?range={range_}&interval={interval}")
        req = _u.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with _u.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        res = data['chart']['result'][0]
        ts = res.get('timestamp', [])
        q = res['indicators']['quote'][0]
        out = []
        for i, t in enumerate(ts):
            c = q.get('close', [None])[i]
            if c is None:
                continue
            out.append({
                'date': time.strftime('%Y-%m-%d', time.gmtime(t)),
                'open': q.get('open', [None])[i] or c,
                'close': c,
                'high': q.get('high', [None])[i] or c,
                'low': q.get('low', [None])[i] or c,
                'volume': q.get('volume', [None])[i] or 0,
                'amount': 0,
            })
        return out

    @staticmethod
    def _kline_cn_baostock(code: str, period: str):
        """baostock A股日K兜底，代码 600519→sh.600519 / 000001→sz.000001"""
        try:
            import baostock as bs
            freq = {'101': 'd', '102': 'w', '103': 'm'}.get(period, 'd')
            if code.startswith(('sh', 'sz')):
                full = code[:2] + '.' + code[2:]   # 指数/带前缀代码
            else:
                full = ('sh.' if code.startswith('6') else 'sz.') + code
            import io, contextlib
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                bs.login()
            try:
                rs = bs.query_history_k_data_plus(
                    full, "date,open,close,high,low,volume,amount",
                    start_date='2024-01-01', end_date='2027-12-31',
                    frequency=freq, adjustflag='3')
                rows = []
                while rs.error_code == '0' and rs.next():
                    rows.append(rs.get_row_data())
            finally:
                with contextlib.redirect_stdout(io.StringIO()):
                    bs.logout()
            result = []
            for r_ in rows:
                try:
                    result.append({
                        'date': r_[0],
                        'open': float(r_[1]), 'close': float(r_[2]),
                        'high': float(r_[3]), 'low': float(r_[4]),
                        'volume': float(r_[5] or 0),
                        'amount': float(r_[6] or 0),
                    })
                except (ValueError, IndexError):
                    continue
            return result
        except Exception as e:
            print(f"[baostock kline] 获取失败: {e}")
            return []

    def market_extras(self) -> str:
        """免费宏观情绪包：VIX / 10Y / 三大指数（Yahoo V8，无 Key）"""
        lines = []
        for name, sym in [("VIX恐慌指数", "^VIX"), ("美债10Y", "^TNX"),
                          ("标普500", "^GSPC"), ("道琼斯", "^DJI"), ("纳斯达克综合", "^IXIC")]:
            try:
                d = self._yahoo_chart(sym, range_='5d', interval='1d')
                cur = d[-1]['close']
                prev = d[-2]['close'] if len(d) > 1 else cur
                chg = (cur - prev) / prev * 100
                lines.append(f"{name}: {cur:.2f} ({chg:+.2f}%)")
            except Exception as e:
                lines.append(f"{name}: DATA_INCOMPLETE ({e})")
        return "\n".join(lines)

    def volume_ma(self, sym: str, days: int = 20):
        """成交量均线（补 DATA_INCOMPLETE）：sym 如 GOOG / 000001.SS"""
        d = self._yahoo_chart(sym, range_='3mo', interval='1d')
        vols = [x['volume'] for x in d if x['volume']][-days:]
        cur = vols[-1] if vols else 0
        avg = sum(vols) / len(vols) if vols else 0
        return {'symbol': sym, 'volume': cur, f'volume_ma{days}': avg,
                'ratio': cur / avg if avg else 0, 'days': len(vols)}

    def dividends(self, sym: str, year: int = 1):
        """近 N 年分红次数（Yahoo events=div）"""
        import urllib.request as _u
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
               f"?range={year}y&interval=1mo&events=div")
        req = _u.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with _u.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        res = data['chart']['result'][0]
        ev = res.get('events', {}).get('dividends', {})
        return {'symbol': sym, 'count': len(ev),
                'total': round(sum(v['amount'] for v in ev.values()), 4)}

    def compare(self, symbols: List[str]) -> str:
        """对比多只股票（表格形式）"""
        result = self.get_quotes(symbols)
        if not result['data']:
            return "获取数据失败"
        
        lines = []
        lines.append(f"{'股票':<12} {'现价':>8} {'涨跌':>8} {'涨跌幅':>8} {'最高':>8} {'最低':>8}")
        lines.append("-" * 60)
        
        for item in result['data']:
            name = item.get('name', item.get('symbol', 'N/A'))[:10]
            price = item.get('price', 'N/A')
            change = item.get('change', 'N/A')
            change_pct = item.get('change_pct', 'N/A')
            high = item.get('high', 'N/A')
            low = item.get('low', 'N/A')
            lines.append(f"{name:<12} {price:>8} {change:>8} {change_pct:>7}% {high:>8} {low:>8}")
        
        return '\n'.join(lines)

    def get_industries(self) -> List[str]:
        """获取A股行业列表（基于 baostock）"""
        if not BAOSTOCK_AVAILABLE:
            return []
        try:
            bs.login()
            rs = bs.query_stock_industry()
            industries = set()
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                if row[3]:
                    industries.add(row[3])
            bs.logout()
            return sorted(list(industries))
        except Exception as e:
            print(f"[baostock] 获取行业列表失败: {e}")
            return []

    def screen_by_industry(self, industry: str, pe_max: float = None, pb_max: float = None, limit: int = 50) -> List[Dict[str, Any]]:
        """按行业筛选股票（支持模糊匹配，批量获取行情）"""
        if not BAOSTOCK_AVAILABLE:
            return []
        try:
            bs.login()
            rs = bs.query_stock_industry()
            candidates = []
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                if row[3] and (row[3] == industry or industry in row[3]):
                    candidates.append({'code': row[1], 'name': row[2], 'industry': row[3]})
            
            
            # 限制数量，避免请求过多
            candidates = candidates[:limit]
            
            # 批量获取行情
            codes = []
            code_map = {}
            for c in candidates:
                raw_code = c['code']
                # sh.600062 -> sh600062
                if '.' in raw_code:
                    formatted_code = raw_code.replace('.', '')
                elif raw_code.isdigit():
                    # 自动添加市场前缀
                    formatted_code = f"sh{raw_code}" if raw_code.startswith('6') else f"sz{raw_code}"
                else:
                    formatted_code = raw_code
                codes.append(formatted_code)
                code_map[formatted_code] = c
            
            # 分批获取，每批最多 50 只
            all_quotes = []
            batch_size = 50
            for i in range(0, len(codes), batch_size):
                batch = codes[i:i + batch_size]
                
                result = self.get_quotes(batch)
                
                
                
                all_quotes.extend(result.get('data', []))
            
            quote_map = {}
            for q in all_quotes:
                symbol = q.get('symbol', '')
                quote_map[symbol] = q
            
            # 同时建立带前缀的映射
            prefixed_map = {}
            for symbol, q in quote_map.items():
                prefixed_map[symbol] = q
                if symbol.isdigit():
                    prefixed = f"sh{symbol}" if symbol.startswith('6') else f"sz{symbol}"
                    prefixed_map[prefixed] = q
            
            
            
            results = []
            for formatted_code, stock in code_map.items():
                quote = prefixed_map.get(formatted_code, {})
                
                if quote and 'error' not in quote:
                    pe = float(quote.get('pe', 0) or 0)
                    pb = float(quote.get('pb', 0) or 0)
                    
                    if pe_max and pe > pe_max and pe > 0:
                        continue
                    if pb_max and pb > pb_max and pb > 0:
                        continue
                    results.append({
                        'code': stock['code'],
                        'name': stock['name'],
                        'industry': stock['industry'],
                        'price': quote.get('price', ''),
                        'pe': pe if pe > 0 else '-',
                        'pb': pb if pb > 0 else '-',
                        'change_pct': quote.get('change_pct', ''),
                    })
            
            bs.logout()
            return results
        except Exception as e:
            print(f"[baostock] 行业筛选失败: {e}")
            return []



def main():
    """命令行入口"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  cn_market.py quote <代码1> [代码2] ...")
        print("  cn_market.py compare <代码1> <代码2> ...")
        print("  cn_market.py us <代码>")
        print("  cn_market.py a <代码>")
        print()
        print("示例:")
        print("  cn_market.py quote usGOOG usAAPL")
        print("  cn_market.py compare GOOG AAPL MSFT")
        print("  cn_market.py us NVDA")
        print("  cn_market.py a 600519")
        return
    
    cmd = sys.argv[1]
    data = CNMarketData()
    
    if cmd == 'quote' or cmd == 'compare':
        symbols = sys.argv[2:]
        if not symbols:
            print("请提供股票代码")
            return
        
        # 自动添加前缀
        formatted = []
        for s in symbols:
            if s.isdigit() and len(s) == 6:
                formatted.append(f"sh{s}" if s.startswith('6') else f"sz{s}")
            elif not s.startswith(('us', 'sh', 'sz', 'hk')):
                formatted.append(f"us{s}")
            else:
                formatted.append(s)
        
        if cmd == 'compare':
            print(data.compare(formatted))
        else:
            result = data.get_quotes(formatted)
            for item in result['data']:
                print(json.dumps(item, ensure_ascii=False, indent=2))
    
    elif cmd == 'us':
        ticker = sys.argv[2] if len(sys.argv) > 2 else ''
        if not ticker:
            print("请提供美股代码，如: cn_market.py us AAPL")
            return
        print(json.dumps(data.get_us_quote(ticker), ensure_ascii=False, indent=2))
    
    elif cmd == 'a':
        code = sys.argv[2] if len(sys.argv) > 2 else ''
        if not code:
            print("请提供A股代码，如: cn_market.py a 600519")
            return
        print(json.dumps(data.get_a_share_quote(code), ensure_ascii=False, indent=2))
    
    elif cmd == 'extras':
        # 免费宏观情绪包：VIX / 10Y / 三大指数
        print(data.market_extras())

    elif cmd == 'volume':
        sym = sys.argv[2] if len(sys.argv) > 2 else ''
        if not sym:
            print("用法: cn_market.py volume GOOG 或 000001.SS")
            return
        print(json.dumps(data.volume_ma(sym), ensure_ascii=False, indent=2))

    elif cmd == 'div':
        sym = sys.argv[2] if len(sys.argv) > 2 else ''
        if not sym:
            print("用法: cn_market.py div VZ")
            return
        print(json.dumps(data.dividends(sym), ensure_ascii=False, indent=2))

    elif cmd == 'kline':
        code = sys.argv[2] if len(sys.argv) > 2 else ''
        if not code:
            print("请提供股票代码，如: cn_market.py kline 600519")
            return
        
        market = "CN"
        period = "101"
        
        # 解析参数
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--market' and i + 1 < len(args):
                market = args[i + 1]
                i += 2
            elif args[i] == '--period' and i + 1 < len(args):
                period = args[i + 1]
                i += 2
            else:
                i += 1
        
        klines = data.get_kline(code, market, period)
        print(json.dumps(klines, ensure_ascii=False, indent=2))
    
    elif cmd == 'industry':
        action = sys.argv[2] if len(sys.argv) > 2 else 'list'
        
        if action == 'list':
            industries = data.get_industries()
            if industries:
                print("\n".join(industries))
            else:
                print("获取行业列表失败，请检查 baostock 是否安装")
        
        elif action == 'screen':
            if len(sys.argv) < 4:
                print("用法: cn_market.py industry screen <行业名> [--pe-max 30] [--pb-max 5]")
                print("\n可用行业:")
                for ind in data.get_industries():
                    print(f"  {ind}")
                return
            
            industry = sys.argv[3]
            pe_max = None
            pb_max = None
            
            args = sys.argv[4:]
            i = 0
            while i < len(args):
                if args[i] == '--pe-max' and i + 1 < len(args):
                    pe_max = float(args[i + 1])
                    i += 2
                elif args[i] == '--pb-max' and i + 1 < len(args):
                    pb_max = float(args[i + 1])
                    i += 2
                else:
                    i += 1
            
            results = data.screen_by_industry(industry, pe_max, pb_max)
            if results:
                print(f"\n行业筛选结果：{industry}（{len(results)} 只）\n")
                print(f"{'代码':<12} {'名称':<10} {'现价':>8} {'PE':>8} {'PB':>8} {'涨跌幅':>8}")
                print("-" * 60)
                for r in results:
                    print(f"{r['code']:<12} {r['name']:<10} {r['price']:>8} {str(r['pe']):>8} {str(r['pb']):>8} {str(r['change_pct']):>7}%")
            else:
                print(f"行业 {industry} 没有符合条件的股票")
        
        else:
            print("用法:")
            print("  cn_market.py industry list")
            print("  cn_market.py industry screen <行业名> [--pe-max 30] [--pb-max 5]")
    
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
