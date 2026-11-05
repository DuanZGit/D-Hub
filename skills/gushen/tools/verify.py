#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — 数值真实性抽检（GATE D，对标上游 report_audit 思路，但适配日报）

原理：日报的报价/量能来自「腾讯」源（cn_market）。要验证报告里的数字是否真实，
必须用【独立于生成源】的信源回验，否则是自己查自己。本工具用 Finnhub + Yahoo
两个独立源交叉核对报告 quotes，全程 Decimal（不用 float，避免小数点隐患）。

判决口径（可配 --tol，默认 1%）：
  PASS      报告值与 ≥1 个独立源偏差 ≤ tol，且独立源彼此 ≤ tol
  CONFLICT  两个独立源彼此偏差 > tol（信源打架，非报告之过）→ 人工复核，不判报告错
  FAIL      报告值与【所有】独立源偏差都 > tol（报告数字与市面对不上）
  MISSING   无任何独立源可用 → 标 DATA_INCOMPLETE，不得当作通过

用法：
  verify.py price facts.json        # 校验报告价格 vs 独立源
  verify.py pe    facts.json        # 校验 PE-TTM vs Finnhub（口径差异大，warn 阈值默认 15%）
  verify.py all   facts.json

facts.json 由 GATE A 落盘（见 dump_facts.py），结构：
{
  "asof": "2026-09-02T14:05:00-04:00",
  "source": "tencent",
  "quotes":       {"GOOG": {"price": 334.13, "prev_close": 332.04}},
  "fundamentals": {"GOOG": {"pe_ttm": 17.31}}
}
"""
import sys, os, json
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cn_market as cm          # 腾讯源（生成源）+ Yahoo 兜底
import deep                     # Finnhub

def D(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None

def fmt(v, nd=2):
    if v is None:
        return None
    return float(Decimal(str(v)).quantize(D("1." + "0" * nd)))

def pct_dev(a, b):
    """a 相对 b 的百分比偏差绝对值"""
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b) * Decimal("100")

def finnhub_quote(sym):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={sym}&token={deep.FH}"
        d = json.loads(deep._get(url))
        c = D(d.get("c"))
        return c if (c and c > 0) else None
    except Exception:
        return None

def yahoo_price(sym):
    try:
        y = cm.CNMarketData._yahoo_chart(sym, "5d", "1d")
        if isinstance(y, list) and y:
            return D(y[-1].get("close"))
        if isinstance(y, dict):
            return D(y.get("price") or y.get("close"))
        return None
    except Exception:
        return None

def verify_price(facts, tol):
    quotes = facts.get("quotes", {})
    details, conflicts, fails, missing = [], [], [], []
    for sym, q in quotes.items():
        rep = D(q.get("price"))
        if rep is None:
            continue
        srcs = {}
        fh = finnhub_quote(sym)
        yh = yahoo_price(sym)
        if fh: srcs["finnhub"] = fh
        if yh: srcs["yahoo"] = yh
        if not srcs:
            missing.append(sym); continue
        devs = {k: pct_dev(rep, v) for k, v in srcs.items()}
        ok = any(d is not None and d <= tol for d in devs.values())
        # 独立源之间是否打架
        conflict = False
        if len(srcs) >= 2:
            vs = list(srcs.values())
            conflict = pct_dev(vs[0], vs[1]) is not None and pct_dev(vs[0], vs[1]) > tol
        dev_str = {k: (f"{float(v):.2f}%" if v is not None else None) for k, v in devs.items()}
        rec = {"symbol": sym, "report": float(rep),
               "independent": {k: float(v) for k, v in srcs.items()},
               "dev": dev_str}
        if conflict:
            rec["verdict"] = "CONFLICT"; conflicts.append(sym)
        elif ok:
            rec["verdict"] = "PASS"
        else:
            rec["verdict"] = "FAIL"; fails.append(sym)
        rec["detail"] = f"report={float(rep):.2f} " + " ".join(f"{k}={float(v):.2f}({dev_str[k]})" for k, v in srcs.items())
        details.append(rec)
    return {
        "price_checks": details,
        "passed": [r["symbol"] for r in details if r["verdict"] == "PASS"],
        "conflicts": conflicts, "fails": fails, "missing": missing,
        "tolerance_pct": float(tol),
    }

def verify_pe(facts, warn):
    """内部一致性检查（非独立交叉——美股无第二免费 PE 源）。
    用 report_price ÷ eps_ttm 反算 implied PE，对比报告展示的 pe_ttm。
    偏差超阈值 → 说明字段映射/单位/取数错位（自伤型 bug），不是信源分歧。
    TTM 时点差本身会带 ~3% 噪声，故阈值放宽。"""
    out, warns = [], []
    for sym, f in facts.get("fundamentals", {}).items():
        rep = D(f.get("pe_ttm"))
        price = D((facts.get("quotes", {}).get(sym) or {}).get("price"))
        eps = D(f.get("eps_ttm"))
        if rep is None:
            continue
        rec = {"symbol": sym, "report_pe": float(rep)}
        if price is None or eps in (None, 0) or eps < 0:
            rec["verdict"] = "NO_IMPLIED"; out.append(rec); continue
        implied = price / eps
        d = pct_dev(rep, implied)
        rec["implied_pe"] = float(implied.quantize(D("0.01")))
        rec["dev_pct"] = (round(float(d), 1) if d is not None else None)
        if d is not None and d > warn:
            rec["verdict"] = "PE_WARN"; warns.append(sym)
        else:
            rec["verdict"] = "OK"
        out.append(rec)
    return {"pe_consistency": out, "pe_warns": warns}

PORT_CANDS = ["/var/minis/shared/portfolio/portfolio.json",
              os.path.expanduser("~/portfolio/portfolio.json"),
              os.path.expanduser("~/.agents/shared/portfolio/portfolio.json")]
PORTFOLIO = os.environ.get('GUSHEN_PORTFOLIO') or next((c for c in PORT_CANDS if os.path.isfile(c)), PORT_CANDS[-1])

def portfolio_math(facts):
    """组合账本，全程 Decimal（QQQ 0.0677 股 × 价格这类小数不能再带 float 噪声）。
    只依赖 facts.json 里已过交叉验证的价格，不另取数。"""
    try:
        pf = json.load(open(PORTFOLIO))
    except Exception:
        return {"portfolio": None, "note": "portfolio.json 读取失败"}
    fee = D(str(pf.get("transaction_fee_per_trade", 0)))
    rows, tot_mv, tot_cost = [], D(0), D(0)
    for h in pf.get("portfolio", []):
        sym = h["code"]
        shares = D(str(h["shares"])); cost = D(str(h["cost"]))
        if not shares or shares == 0:
            continue  # 已清仓（shares=0）：不占市值，也不需要现价，跳过
        price = D((facts.get("quotes", {}).get(sym) or {}).get("price")) if facts.get("quotes", {}).get(sym) else None
        mv = (shares * price) if price is not None else None
        cost_basis = shares * cost
        pnl = (mv - cost_basis) if mv is not None else None
        pnl_pct = (pnl / cost_basis * 100) if (pnl is not None and cost_basis) else None
        if mv is not None: tot_mv += mv
        tot_cost += cost_basis
        rows.append({
            "code": sym, "shares": fmt(shares, 4),
            "cost": fmt(cost, 4),
            "price": (fmt(price) if price is not None else None),
            "market_value": (fmt(mv) if mv is not None else None),
            "pnl": (fmt(pnl) if pnl is not None else None),
            "pnl_pct": (fmt(pnl_pct) if pnl_pct is not None else None),
        })
    tot_pnl = tot_mv - tot_cost
    tot_pnl_pct = (tot_pnl / tot_cost * 100) if tot_cost else None
    return {
        "holdings": rows,
        "total_market_value": fmt(tot_mv),
        "total_cost_basis": fmt(tot_cost),
        "total_pnl": fmt(tot_pnl),
        "total_pnl_pct": fmt(tot_pnl_pct),
        "fee_per_trade": fmt(fee),
        "note": "Decimal 精确账本；金额未含手续费（fee_per_trade 供手工扣减）",
    }

def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    cmd, path = sys.argv[1], sys.argv[2]
    tol = Decimal(sys.argv[sys.argv.index("--tol")+1]) if "--tol" in sys.argv else Decimal("1")
    warn = Decimal(sys.argv[sys.argv.index("--warn")+1]) if "--warn" in sys.argv else Decimal("15")
    try:
        facts = json.load(open(path))
    except Exception as e:
        print(json.dumps({"error": f"facts.json 读取失败: {e}"}, ensure_ascii=False)); 
        print("AUDIT_FAIL errors=1"); sys.exit(1)

    result = {}
    if cmd in ("price", "all"):
        result.update(verify_price(facts, tol))
    if cmd in ("pe", "all"):
        result.update(verify_pe(facts, warn))
    if cmd in ("portfolio", "all"):
        result["portfolio"] = portfolio_math(facts)

    n_fail = len(result.get("fails", []))
    n_conf = len(result.get("conflicts", []))
    n_miss = len(result.get("missing", []))
    n_pe_w = len(result.get("pe_warns", []))
    # facts 缺价导致组合算不出的持仓，计入 missing（账本不完整 = 不可交付）
    if cmd in ("portfolio", "all") and isinstance(result.get("portfolio"), dict):
        for r in result["portfolio"].get("holdings", []):
            if r.get("price") is None:
                n_miss += 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    errors = n_fail + n_miss
    if errors:
        print(f"AUDIT_FAIL errors={errors} conflicts={n_conf} pe_warns={n_pe_w}")
        sys.exit(1)
    if n_conf or n_pe_w:
        print(f"AUDIT_PASS_WITH_WARNINGS conflicts={n_conf} pe_warns={n_pe_w}")
    else:
        print("AUDIT_PASS")

if __name__ == "__main__":
    main()
