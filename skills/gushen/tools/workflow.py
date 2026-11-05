#!/usr/bin/env python3
"""Gushen workflow — 单入口、幂等、可重试的稳定链路。

Gate A: dump_facts 落盘 → financial_rigor 自动精算(growth/pe 自动算)前置直供
重试3次 + 超时隔离 + 旧文件兜底，单点失败不拖垮全流程。

用法:
  python3 tools/workflow.py                    # 持仓+SPY/DIA，幂等复用当日
  python3 tools/workflow.py --force            # 强制重抓
  python3 tools/workflow.py --symbols GOOG NVDA
  python3 tools/workflow.py --scan             # 强制跑新机会扫描（现金>40% 默认自动扫）
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
PORT_CANDS = ["/var/minis/shared/portfolio/portfolio.json",
              str(Path.home() / "portfolio/portfolio.json"),
              str(Path.home() / ".agents/shared/portfolio/portfolio.json")]
WORKSPACE = Path(os.environ.get('WORKSPACE') or ('/var/minis/workspace' if os.path.isdir('/var/minis/workspace') else os.path.expanduser('~/workspace')))
PORTFOLIO = Path(os.environ.get('GUSHEN_PORTFOLIO') or next((c for c in PORT_CANDS if Path(c).is_file()), PORT_CANDS[-1]))

def sh(cmd, timeout=30, retries=2):
    last = None
    for i in range(retries+1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            # 成功或含 DATA_INCOMPLETE 都算有效输出
            if r.returncode == 0 or "DATA_INCOMPLETE" in (r.stdout or ""):
                return r
            last = r
        except subprocess.TimeoutExpired as e:
            # 包装为类 CompletedProcess，避免调用方崩溃
            class T: stdout=""; stderr=str(e); returncode=124
            last = T()
        if i < retries:
            time.sleep(1.5*(i+1))
    return last

def portfolio_symbols():
    try:
        d = json.loads(PORTFOLIO.read_text(encoding='utf-8'))
        return [h['code'] for h in d.get('portfolio',[]) if h.get('shares',0)>0]
    except: return ["GOOG","NVDA","JPM","VZ","QQQ","SGOV"]

def auto_params(fund, price):
    """growth/pe 自动算，不手填。保守为主，不用股价收益当增速。"""
    try: price = float(price)
    except: return None
    pe = fund.get('pe_ttm'); eps = fund.get('eps_ttm')
    if eps is None: return None
    pb = fund.get('pb_fy'); div = fund.get('div_per_share')
    # growth: 优先 eps_growth/rev_growth，否则保守 0.06（成熟）/ 0.10（高 ROE 成长）
    g_raw = fund.get('eps_growth')
    if g_raw is None: g_raw = fund.get('rev_growth')
    if g_raw is None:
        # 无增速数据时保守估计：高 ROE 成长股给 0.10，其余 0.06，不用 r26w 冒充
        roe = fund.get('roe_fy')
        try: g_raw = 0.10 if roe and float(roe) > 20 else 0.06
        except: g_raw = 0.06
    else:
        try: g_raw = float(g_raw)/100 if abs(float(g_raw))>1 else float(g_raw)
        except: g_raw = 0.06
    g_raw = max(-0.03, min(0.20, g_raw))
    g_neutral = round(g_raw, 3)
    g_opt = round(min(0.22, g_neutral+0.05), 3)
    g_pes = round(max(-0.02, g_neutral-0.05), 3)
    try: pe_n = float(pe)
    except: pe_n = 17
    pe_n = max(8, min(35, pe_n))
    pe_opt = round(pe_n*1.15,1); pe_pes = round(pe_n*0.85,1)
    bvps = None
    try:
        if pb and float(pb)>0: bvps = price/float(pb)
    except: pass
    return {"pe":pe_n,"eps":eps,"bvps":bvps,"div":div,"growth":[g_opt,g_neutral,g_pes],"pe_trip":[pe_opt,pe_n,pe_pes]}

def scan_pool(held):
    """自动筛候选池：MAG7 去重持仓 + QQQ 前十去重持仓 + 防御红利 2 只。纯静态名单，零网络调用。"""
    MAG7 = ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA"]
    QQQ_TOP10 = ["AAPL", "MSFT", "NVDA", "AVGO", "AMZN", "META", "GOOG", "COST", "NFLX", "TSLA"]
    DEFENSIVE = ["JNJ", "PG"]
    pool = []
    for s in MAG7 + QQQ_TOP10 + DEFENSIVE:
        if s not in held and s not in pool:
            pool.append(s)
    return pool


def cash_ratio(facts):
    """从 facts.quotes + portfolio.json 算现金占比。SGOV 市值/总市值。"""
    try:
        pf = json.loads(PORTFOLIO.read_text(encoding='utf-8'))
        shares = {h['code']: float(h.get('shares', 0) or 0) for h in pf.get('portfolio', [])}
    except Exception:
        return 0.0, 0.0, 0.0
    q = facts.get('quotes', {})
    try:
        sgov_mv = shares.get('SGOV', 0) * float(q.get('SGOV', {}).get('price', 0) or 0)
    except Exception:
        sgov_mv = 0.0
    tot = 0.0
    for code, sh in shares.items():
        if sh <= 0:
            continue
        try:
            tot += sh * float(q.get(code, {}).get('price', 0) or 0)
        except Exception:
            pass
    return (sgov_mv / tot if tot else 0.0), sgov_mv, tot


def main():
    p = argparse.ArgumentParser(description="Gushen workflow")
    p.add_argument('--symbols', nargs='*', default=None)
    p.add_argument('--out', default=str(WORKSPACE/"facts_20260903.json"))
    p.add_argument('--force', action='store_true', help='强制重抓，不复用缓存')
    p.add_argument('--scan', action='store_true', help='强制跑新机会扫描（否则按现金占比自动决定）')
    p.add_argument('--no-scan', action='store_true', help='跳过扫描（只跑持仓部分）')
    args = p.parse_args()
    syms = [s.upper() for s in (args.symbols or portfolio_symbols()+["SPY","DIA"])]
    seen=set(); uniq=[]
    for s in syms:
        if s not in seen: seen.add(s); uniq.append(s)
    syms=uniq
    out = Path(args.out)
    facts = None
    # 幂等：当日文件存在且非 --force 则直接复用（按文件 mtime 的 UTC 日期判定）
    if out.exists() and not args.force:
        try:
            mtime = datetime.fromtimestamp(out.stat().st_mtime, tz=timezone.utc).date()
            today = datetime.now(timezone.utc).date()
            if mtime == today:
                facts = json.loads(out.read_text(encoding='utf-8'))
                print(f"[workflow] 复用当日缓存 {out} (mtime {mtime})")
            else:
                print(f"[workflow] 缓存非当日({mtime} vs {today})，将重抓")
        except Exception as e:
            print(f"[workflow] 缓存读取失败: {e}")
            facts = None
    if facts is None:
        print(f"[workflow] Gate A 抓取: {syms}")
        r = sh([sys.executable, str(BASE/"dump_facts.py")] + syms, timeout=35, retries=2)
        raw = getattr(r, 'stdout', '') or ""
        if not raw or '{' not in raw:
            # 兜底：若旧 facts 存在则复用
            if out.exists():
                try:
                    facts = json.loads(out.read_text(encoding='utf-8'))
                    print(f"[workflow] 抓取无有效 JSON，兜底复用旧 facts: {out}")
                except: sys.exit(1)
            else:
                print(f"[workflow] dump_facts 失败: {(getattr(r,'stderr','') or raw)[:600]}")
                sys.exit(1)
        else:
            raw = raw[raw.find('{'):raw.rfind('}')+1]
            facts = json.loads(raw)
            out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"[workflow] facts 落盘 {out} quotes={list(facts.get('quotes',{}).keys())}")
    # Gate A 之后：financial_rigor 自动精算，前置直供
    rigor={}
    for sym in [s for s in syms if s in facts.get('quotes',{}) and s in facts.get('fundamentals',{})]:
        fund=facts['fundamentals'][sym]; price=facts['quotes'][sym].get('price')
        ap=auto_params(fund, price)
        if not ap or ap.get('eps') is None: continue
        cmd=[sys.executable, str(BASE/"financial_rigor.py"), "verify-valuation", "--price", str(price), "--eps", str(ap['eps'])]
        if ap.get('bvps'): cmd+=["--bvps", str(round(ap['bvps'],2))]
        if ap.get('div') and float(ap['div'] or 0)>0: cmd+=["--dividend", str(ap['div'])]
        r1=sh(cmd, timeout=15)
        cmd2=[sys.executable, str(BASE/"financial_rigor.py"), "three-scenario", "--price", str(price), "--eps", str(ap['eps']), "--shares", "12.5",
              "--growth", str(ap['growth'][0]), str(ap['growth'][1]), str(ap['growth'][2]),
              "--pe", str(ap['pe_trip'][0]), str(ap['pe_trip'][1]), str(ap['pe_trip'][2])]
        r2=sh(cmd2, timeout=15)
        rigor[sym]={"auto_params":ap, "valuation": (getattr(r1, "stdout", "") or "")[:1200],
                    "three_scenario": (getattr(r2, "stdout", "") or "")[:1800]}
    if rigor:
        facts['rigor']=rigor
        total=filled=0
        for f in facts.get('fundamentals',{}).values():
            for k in ["pe_ttm","eps_ttm","beta","roe_fy","w52_high"]:
                total+=1; filled+=1 if f.get(k) not in (None,"") else 0
        facts['richness']={"filled":filled,"total":total,"pct": round(filled/total*100,1) if total else 0}
        out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"[workflow] rigor {len(rigor)} 标的，丰富度 {facts['richness']['pct']}%（growth/pe 自动算，已前置为弹药）")
    # 准出（仅报告，不阻断）
    r=sh([sys.executable, str(BASE/"validate_contract.py")], timeout=10)
    if r and getattr(r,'stdout',None): print(r.stdout.strip()[:300])
    rep=WORKSPACE/"gushen_report_20260903.html"
    if rep.exists():
        r=sh([sys.executable, str(BASE/"validate_report.py"), str(rep)], timeout=10)
        if r and getattr(r,'stdout',None): print(r.stdout.strip()[:600])
    r=sh([sys.executable, str(BASE/"verify.py"), "all", str(out)], timeout=25)
    if r and getattr(r,'stdout',None): print(r.stdout.strip()[-800:] if len(r.stdout)>800 else r.stdout.strip())
    # 新机会扫描（自动筛 + 按现金来 + 频率跟现金走）
    if not args.no_scan:
        ratio, cash_mv, tot_mv = cash_ratio(facts)
        held = set(portfolio_symbols())
        do_scan = args.scan or ratio > 0.40
        if args.scan:
            print(f"[workflow] --scan 强制扫描（现金占比 {ratio*100:.1f}%）")
        elif ratio > 0.40:
            print(f"[workflow] 现金占比 {ratio*100:.1f}% >40%，自动扫描")
        else:
            print(f"[workflow] 现金占比 {ratio*100:.1f}% ≤40%，跳过扫描（--scan 可强制）")
        if do_scan:
            pool = scan_pool(held)
            # 单只上限 = 现金/4，且单票不超组合 10%；名额：>40% 可 2 只
            try:
                per_cap = cash_mv / 4 if cash_mv else 0
                combo_cap = tot_mv * 0.10 if tot_mv else 0
            except Exception:
                per_cap = combo_cap = 0
            print(f"[workflow] 候选池（去重持仓）: {pool}")
            print(f"[workflow] 仓位上限：单只 ≤ ${per_cap:.0f}（现金1/4）且 ≤ ${combo_cap:.0f}（组合10%），名额 ≤2 只")
            scan_facts = dict(facts.get('quotes', {}))
            import cn_market as _cm
            import deep as _deep
            scan_sent = {}
            try:
                import importlib
                _ad = importlib.import_module("adanos")
                _st = _ad.sentiment(pool)
                for _src in ("reddit", "x", "news", "polymarket"):
                    if isinstance(_st.get(_src), dict):
                        for _row in _st[_src].get("stocks") or []:
                            scan_sent.setdefault(_row["ticker"], {})[_src] = {k: _row.get(k) for k in ("buzz_score", "sentiment_score", "bullish_pct", "mentions")}
            except Exception as _e:
                print(f"[scan] adanos 情绪拉取失败: {str(_e)[:80]}（不阻断扫描）")
            screened = []
            for sym in pool:
                try:
                    mkt = _cm.CNMarketData()
                    q = mkt.get_us_quote(sym)
                    if not q or not q.get('price'):
                        print(f"[scan] {sym}: 无报价，跳过")
                        continue
                    try:
                        fund = _deep.fh_metric(sym)
                    except Exception:
                        fund = {}
                    rec = {}
                    try:
                        rec = _deep.fh_recommend(sym) or {}
                    except Exception:
                        rec = {}
                    surp = []
                    try:
                        surp = _deep.fh_eps_surprise(sym) or []
                    except Exception:
                        surp = []
                    try:
                        v = mkt.volume_ma(sym)
                        ratio_v = v.get('ratio') if isinstance(v, dict) else None
                    except Exception:
                        ratio_v = None
                    screened.append({
                        'code': sym, 'price': q.get('price'), 'prev_close': q.get('prev_close'),
                        'sentiment': scan_sent.get(sym, {}),
                        'pe_ttm': fund.get('pe_ttm'), 'roe_fy': fund.get('roe_fy'),
                        'eps_ttm': fund.get('eps_ttm'), 'beta': fund.get('beta'),
                        'div_per_share': fund.get('div_per_share'),
                        'volume_ratio': round(ratio_v, 2) if ratio_v else None,
                        'surprises': [x.get('surprise_pct') for x in (surp or [])][-4:],
                        'recommend': {k: rec.get(k) for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')},
                    })
                    print(f"[scan] {sym}: ${q.get('price')} PE {fund.get('pe_ttm')} 量比 {ratio_v} miss {[x for x in [y.get('surprise_pct') for y in (surp or [])][-2:] if x is not None and x < 0]}")
                except Exception as e:
                    print(f"[scan] {sym} 失败: {str(e)[:100]}")
            facts['scan'] = {
                'pool': pool, 'screened': screened,
                'caps': {'per_stock_usd': round(per_cap, 0), 'combo_pct': 10, 'max_names': 2},
                'cash_ratio': round(ratio, 4), 'cash_mv': round(cash_mv, 2), 'total_mv': round(tot_mv, 2),
            }
            out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"[workflow] scan 落盘 {len(screened)}/{len(pool)} 只初筛，取前 ≤2 只跑全量 Gate B/C/D（见 SKILL 新机会扫描）")
    print(f"[workflow] done. facts={out} rigor={len(rigor)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
