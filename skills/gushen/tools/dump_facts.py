#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_facts.py — GATE A 数据落盘

报告渲染前，先把「生成源」的原始数字冻结成 facts.json（作为被验对象的一个版本记录），
verify.py 再用【独立源】(Finnhub/Yahoo) 回验它。这样做的意义：
  1. 报告里的数字有可追溯出处，不是手打的
  2. 事后能审计「当时生成源到底给了什么」
  3. 交叉验证才成立（报告 ← 生成源 ← 独立源 三方对照）

用法：
  dump_facts.py GOOG NVDA JPM VZ QQQ SPY DIA > facts.json
  （A 股代码带 sh./sz. 前缀，如 sh.600519）
"""
import sys, os, json, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cn_market as cm
import deep

def main():
    syms = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]
    if not syms:
        print(json.dumps({"error": "用法: dump_facts.py <SYM> [SYM...]"}))
        return

    cn_syms, us_syms = [], []
    for s in syms:
        (cn_syms if (s.startswith(("SH.", "SZ.")) or s.isdigit()) else us_syms).append(s)

    m = cm.CNMarketData()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # 美东时间（EDT=UTC-4）。用带时区的对象，避免 asof_et 误标 +00:00
    EDT = datetime.timezone(datetime.timedelta(hours=-4), "EDT")
    et = now_utc.astimezone(EDT)
    facts = {"asof_utc": now_utc.isoformat(), "asof_et": et.isoformat(),
             "source": "tencent", "generated_by": "dump_facts.py",
             "quotes": {}, "volume": {}, "fundamentals": {}, "sentiment": {},
             "macro": {}, "data_incomplete": []}

    # --- 生成源报价（腾讯）---
    for s in us_syms:
        try:
            q = m.get_us_quote(s)
            if q and q.get("price"):
                facts["quotes"][s] = {"price": q["price"], "prev_close": q.get("prev_close")}
            else:
                facts["data_incomplete"].append(f"quote:{s}")
        except Exception:
            facts["data_incomplete"].append(f"quote:{s}")

    # --- A 股报价 ---
    for s in cn_syms:
        try:
            q = m.get_a_share_quote(s[-6:])
            if q and q.get("price"):
                facts["quotes"][s] = {"price": q["price"], "prev_close": q.get("prev_close")}
            else:
                facts["data_incomplete"].append(f"quote:{s}")
        except Exception:
            facts["data_incomplete"].append(f"quote:{s}")

    # --- 量能（腾讯K线，20日均量/量比）---
    for s in us_syms:
        try:
            v = m.volume_ma(s)
            if v:
                facts["volume"][s] = {"volume": v["volume"], "volume_ma20": v["volume_ma20"], "ratio": v["ratio"]}
        except Exception:
            facts["data_incomplete"].append(f"volume:{s}")
    for s in us_syms:
        try:
            facts["fundamentals"][s] = deep.fh_metric(s)
        except Exception:
            facts["data_incomplete"].append(f"fund:{s}")

    # --- 情绪面（Adanos 四源：Reddit/X/News/Polymarket；缺 key 或不配则降级，不阻断）---
    try:
        import importlib
        adanos = importlib.import_module("adanos")
        sent = adanos.sentiment(us_syms[:10])
        if isinstance(sent, dict) and "skipped" in sent:
            facts["sentiment"] = dict(sent)
        elif isinstance(sent, dict):
            facts["sentiment"] = {s: sent[s] for s in ("reddit", "x", "news", "polymarket")
                                  if isinstance(sent.get(s), dict) and "stocks" in sent[s]}
            facts["sentiment"]["sources_ok"] = sent.get("sources_ok")
            facts["sentiment"]["period_days"] = (sent.get("reddit") or {}).get("period_days")
    except Exception:
        facts["sentiment"] = {"error": "adanos 调用失败"}
        facts["data_incomplete"].append("sentiment:adanos")

    # --- 宏观（VIX/10Y/三大指数）---
    try:
        facts["macro"] = m.market_extras()
    except Exception:
        facts["data_incomplete"].append("macro")

    print(json.dumps(facts, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
