#!/usr/bin/env python3
"""
gushen 深层数据工具 — 给 8 Agent 补弹药
数据源：Finnhub 深层（免费key）+ 东财资金流（push2 活着）+ baostock 财务
用法：
  deep.py fund GOOG        # 美股基本面包：ROE/beta/PE/PS/股息 + 评级 + EPS surprise → 巴菲特/芒格
  deep.py flow 600519      # A股主力资金流（近10日）→ 情绪/动量
  deep.py north            # 北向资金最新 → A股情绪
  deep.py cnfund sh.600519 # A股财务包：盈利/成长/分红 → 价值组
  deep.py all GOOG         # 美股全套
  deep.py allcn 600519     # A股全套
"""
import json, os, sys, io, contextlib, urllib.request

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.eastmoney.com/"}
FH = os.environ.get("FINNHUB_KEY", "")

def _get(url, headers=UA, timeout=12, retries=3):
    """东财系接口间歇性拒连，3 次重试"""
    import time
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def _n(v, nd=2):
    """None-safe float"""
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None

# ============ Finnhub 深层 ============
def fh_metric(sym):
    d = json.loads(_get(f"https://finnhub.io/api/v1/stock/metric?symbol={sym}&metric=all&token={FH}"))
    m = d.get("metric", {})
    return {
        "beta": _n(m.get("beta"), 3),
        "roe_fy": _n(m.get("roeRfy")), "roa_fy": _n(m.get("roaRfy")),
        "pe_ttm": _n(m.get("peTTM")), "pe_fy": _n(m.get("peAnnual")),
        "eps_ttm": _n(m.get("epsTTM")),
        "ps_fy": _n(m.get("psAnnual")), "pb_fy": _n(m.get("pbAnnual")),
        "ev_ebitda": _n(m.get("evToEbitdaTtm")),
        "gross_margin": _n(m.get("grossMarginTtm")), "net_margin": _n(m.get("netProfitMarginTtm")),
        "fcf_margin": _n(m.get("fcfMarginTtm")),
        "rev_growth": _n(m.get("revenueGrowthTtm")), "eps_growth": _n(m.get("epsGrowthTtm")),
        "div_yield": _n(m.get("dividendYieldIndicatedAnnual")), "div_per_share": _n(m.get("dividendPerShareAnnual")),
        "payout_ratio": _n(m.get("payoutRatioTtm")),
        "w52_high": _n(m.get("52WeekHigh")), "w52_low": _n(m.get("52WeekLow")),
        "w52_return": _n(m.get("52WeekPriceReturnDaily")),
        "ret_5d": _n(m.get("5DayPriceReturnDaily")), "ret_13w": _n(m.get("13WeekPriceReturnDaily")),
        "ret_26w": _n(m.get("26WeekPriceReturnDaily")),
        "vol_10d_ma_m": _n(m.get("10DayAverageTradingVolume")),
        "analyst_target_mean": _n(m.get("targetMeanPrice")), "analyst_count": m.get("analystCount"),
        "recommend_mean": _n(m.get("recommendMean")),
    }

def fh_recommend(sym):
    d = json.loads(_get(f"https://finnhub.io/api/v1/stock/recommendation?symbol={sym}&token={FH}"))
    if not d:
        return None
    e = d[0]
    return {"period": e.get("period"), "strongBuy": e.get("strongBuy"), "buy": e.get("buy"),
            "hold": e.get("hold"), "sell": e.get("sell"), "strongSell": e.get("strongSell")}

def fh_eps_surprise(sym):
    d = json.loads(_get(f"https://finnhub.io/api/v1/stock/earnings?symbol={sym}&token={FH}"))
    out = []
    for e in d[-4:]:
        out.append({"period": e.get("period"), "est": _n(e.get("epsEstimate")),
                    "actual": _n(e.get("epsActual")), "surprise_pct": _n(e.get("surprisePercent"))})
    return out

def us_fund(sym):
    r = {"symbol": sym}
    try: r["fundamentals"] = fh_metric(sym)
    except Exception as e: r["fundamentals"] = f"FAIL {e}"
    try: r["recommendations"] = fh_recommend(sym)
    except Exception as e: r["recommendations"] = f"FAIL {e}"
    try: r["eps_surprise_4q"] = fh_eps_surprise(sym)
    except Exception as e: r["eps_surprise_4q"] = f"FAIL {e}"
    return r

# ============ 东财资金流（push2 仍活着，与挂掉的 push2his 不同域）============
def em_flow(code):
    if code.startswith(("sh", "sz")):
        num = code[2:]
        secid = ("1." if code.startswith("sh") else "0.") + num
    else:
        secid = ("1." if code.startswith("6") else "0.") + code
    url = (f"https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}"
           f"&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&lmt=10&klt=101")
    d = json.loads(_get(url))
    kl = d.get("data", {}).get("klines", [])
    out = []
    for line in kl:
        p = line.split(",")
        # f51日期 f52主力 f53小单 f54中单 f55大单 f56超大单 (元)
        out.append({"date": p[0], "main_net": _n(p[1], 0), "small": _n(p[2], 0),
                    "mid": _n(p[3], 0), "big": _n(p[4], 0), "super": _n(p[5], 0)})
    return {"code": code, "days": len(out), "flow": out}

def em_north():
    url = "https://push2.eastmoney.com/api/qt/kamt.rtmin/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56"
    d = json.loads(_get(url))
    s2n = d.get("data", {}).get("s2n", [])
    if not s2n:
        return {"north": "DATA_INCOMPLETE"}
    last = s2n[-1].split(",")
    return {"time": last[0], "raw_fields": last[1:6],
            "note": "字段为沪股通/深股通分钟级净流入序列(元), 平台披露口径以交易所为准"}

# ============ baostock A股财务 ============
def _bs_rows(query_fn):
    import baostock as bs
    with contextlib.redirect_stdout(io.StringIO()):
        bs.login()
        try:
            rs = query_fn(bs)
            rows = []
            while rs.error_code == '0' and rs.next():
                rows.append(dict(zip(rs.fields, rs.get_row_data())))
        finally:
            with contextlib.redirect_stdout(io.StringIO()):
                bs.logout()
    return rows

def cn_fund(code):
    if not code.startswith(("sh.", "sz.")):
        code = ("sh." if code.startswith("6") else "sz.") + code
    r = {"code": code}
    try:
        rows = _bs_rows(lambda bs: bs.query_profit_data(code=code, year=2025, quarter=3))
        if rows:
            f = rows[-1]
            r["profit_2025q3"] = {"roe_avg": _n(f.get("roeAvg"), 4), "net_margin": _n(f.get("npMargin"), 4),
                                  "gross_margin": _n(f.get("gpMargin"), 4), "net_profit": _n(f.get("netProfit"), 0),
                                  "eps_ttm": _n(f.get("epsTTM"))}
    except Exception as e:
        r["profit_2025q3"] = f"FAIL {e}"
    try:
        rows = _bs_rows(lambda bs: bs.query_growth_data(code=code, year=2025, quarter=3))
        if rows:
            g = rows[-1]
            r["growth_2025q3"] = {k: _n(v, 4) for k, v in g.items() if k.startswith("YOY")}
    except Exception as e:
        r["growth_2025q3"] = f"FAIL {e}"
    try:
        rows = _bs_rows(lambda bs: bs.query_dividend_data(code=code, year="2025", yearType="operate"))
        r["dividends_2025"] = [{"cash_ps": _n(x.get("dividCashPsBeforeTax"), 4),
                                "pay_date": x.get("dividPayDate")} for x in rows]
    except Exception as e:
        r["dividends_2025"] = f"FAIL {e}"
    return r

# ============ 汇总入口 ============
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        if cmd == "fund" or cmd == "all":
            if not arg: raise ValueError("需要股票代码")
            out = us_fund(arg.upper())
        elif cmd == "flow":
            out = em_flow(arg) if arg else {"error": "需要代码"}
        elif cmd == "north":
            out = em_north()
        elif cmd == "cnfund":
            if not arg: raise ValueError("需要代码")
            out = cn_fund(arg)
        elif cmd == "allcn":
            if not arg: raise ValueError("需要代码")
            out = {**cn_fund(arg)}
            try: out["flow"] = em_flow(arg)
            except Exception as e: out["flow"] = f"DATA_INCOMPLETE ({str(e)[:40]})"
            try: out["north"] = em_north()
            except Exception as e: out["north"] = f"DATA_INCOMPLETE ({str(e)[:40]})"
        else:
            out = {"error": f"unknown cmd {cmd}"}
    except Exception as e:
        out = {"error": str(e)[:120], "hint": "东财系接口间歇性拒连属常态，稍后重试或改用其他子命令"}
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
