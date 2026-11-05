#!/usr/bin/env python3
"""
adanos.py — 美股情绪面数据源（Adanos Market Sentiment API）
补 gushen「情绪分析师/动量交易员」的跨社群情绪：Reddit / X / News / Polymarket
四源各给：buzz_score(热度) / mentions(提及) / sentiment_score / bullish_pct / trend

用法：
  adanos.py sentiment GOOG NVDA   # 四源 compare（4 req，tickers ≤10）
  adanos.py market                # 全市场情绪：Reddit + X（2 req）
  adanos.py explain GOOG          # 单标的新闻情绪解释（1 req）
  adanos.py trending [reddit]     # 热门榜挖掘候选（1 req）

配额：免费档 250 req/月、30 天回看、41 端点；raw mentions 与文本情感
（/sentiment/v1/analyze）为 Professional（$299/月）专属。
省配额：ADANOS_NO_SENTIMENT=1 时本工具整体跳过（供 workflow 集成）。

边界：仅美股（ticker ^[A-Za-z]{1,10}$）。A 股情绪仍走 deep.py north/flow（东财）。
key 查找：$ADANOS_KEY → ~/.config/agents/env → <skill>/.env（同 load_key.sh）
"""
import http.client
import json
import os
import re
import sys
import time

HOST = "api.adanos.org"
SOURCES = ("reddit", "x", "news", "polymarket")
TICKER_RE = re.compile(r"^\$?[A-Za-z]{1,10}$")
_QUOTA = {}  # 最近一次 API 响应的配额头快照


def _key():
    k = os.environ.get("ADANOS_KEY", "")
    if not k:
        for f in (os.path.expanduser("~/.config/agents/env"),
                  os.path.expanduser("~/.config/agents/env.local"),
                  os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")):
            try:
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("ADANOS_KEY="):
                            k = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except OSError:
                pass
            if k:
                break
    return k


def _missing_key():
    sys.stderr.write(
        "[adanos] 缺少 ADANOS_KEY —— 本次降级：无跨社群情绪数据（美股其余链路不受影响）\n"
        "  1. 申请: https://adanos.org/register （免费档 250 req/月，够日报用）\n"
        "  2. 写入: echo 'ADANOS_KEY=sk_live_xxx' >> ~/.config/agents/env  (chmod 600)\n"
        "  3. 不配: 设 ADANOS_NO_SENTIMENT=1 显式跳过，情绪 Agent 按东财/量价口径\n")
    return None


def _fetch(path, params=None):
    """返回 (status, obj)；网络异常返回 (None, err_str)。HTTPSConnection 固定 host+443。
    顺手记录 Adanos 配额响应头到 _QUOTA（供调用方附在输出里）。"""
    key = _key()
    if not key:
        return None, "NO_KEY"
    qs = ""
    if params:
        qs = "?" + "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
    target = path if path.startswith("/") else "/" + path
    last = None
    for i in range(3):  # 间歇性超时/5xx 重试，与 deep.py 同策略
        try:
            conn = http.client.HTTPSConnection(HOST, timeout=12)
            conn.request("GET", target + qs,
                         headers={"X-API-Key": key, "User-Agent": "gushen-skill"})
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", errors="replace")
            for h in ("X-RateLimit-Limit-Monthly", "X-RateLimit-Remaining-Monthly",
                      "X-RateLimit-Reset-Monthly", "X-Account-Type"):
                v = resp.getheader(h)
                if v:
                    _QUOTA[h] = v
            conn.close()
            if resp.status >= 400:
                return resp.status, body[:160]
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body[:160]
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    return None, f"NET {last}"


def _quota():
    """最近一次调用的配额快照（无则为空 dict）"""
    return dict(_QUOTA)


def _err(code, body):
    """HTTP 错误码 → 人话"""
    m = {401: "key 无效/被吊销", 403: "超出账号回看上限（免费 30 天）",
         422: "参数不合法（日期窗/代码格式）", 429: "触发速率限制（免费 250 req/月）",
         404: "无数据（该标的/时段无情绪数据）", 503: "explain 推理服务暂不可用"}
    return {"error": f"HTTP {code}", "why": m.get(code, body[:120])}


def _row(stock):
    """统一四源字段口径（各源独有字段也保留）"""
    r = {k: stock.get(k) for k in ("ticker", "company_name", "buzz_score", "trend",
                                   "sentiment_score", "bullish_pct", "bearish_pct")}
    r["mentions"] = stock.get("mentions", stock.get("trade_count"))
    for extra in ("unique_posts", "unique_tweets", "source_count", "subreddit_count",
                  "total_upvotes", "market_count", "trade_count", "unique_traders",
                  "total_liquidity"):
        if stock.get(extra) is not None:
            r[extra] = stock.get(extra)
    if isinstance(stock.get("trend_history"), list):
        r["trend_history"] = stock["trend_history"][-7:]
    return r


def sentiment(symbols):
    """四源 compare：4 req 拉 ≤10 只。symbols=原始列表"""
    if os.environ.get("ADANOS_NO_SENTIMENT") == "1":
        return {"skipped": "ADANOS_NO_SENTIMENT=1"}
    if not _key():
        _missing_key()
        return {"skipped": "no_ADANOS_KEY"}
    syms = [s.lstrip("$").upper() for s in symbols]
    bad = [s for s in syms if not TICKER_RE.match(s)]
    if bad:
        return {"error": f"非美股代码 {bad}", "why": "Adanos 仅覆盖美股 ticker（^[A-Za-z]{1,10}$）",
                "fallback": "A 股情绪用 deep.py flow/north（东财）"}
    syms = syms[:10]
    out: dict = {"symbols": syms}
    for src in SOURCES:
        st, d = _fetch(f"/{src}/stocks/v1/compare", {"tickers": ",".join(syms)})
        if st == 200 and isinstance(d, dict):
            out[src] = {"period_days": d.get("period_days"),
                        "stocks": [_row(s) for s in (d.get("stocks") or [])]}
        else:
            out[src] = _err(st, d) if st else {"error": str(d)[:80]}
    filled = sum(1 for s in SOURCES if isinstance(out.get(s), dict) and "stocks" in out[s])
    out["sources_ok"] = f"{filled}/4"
    q = _quota()
    if q:
        out["quota"] = q
    return out


def market():
    """全市场情绪：reddit + x（2 req）"""
    if os.environ.get("ADANOS_NO_SENTIMENT") == "1":
        return {"skipped": "ADANOS_NO_SENTIMENT=1"}
    if not _key():
        _missing_key()
        return {"skipped": "no_ADANOS_KEY"}
    out: dict = {}
    for src in ("reddit", "x"):
        st, d = _fetch(f"/{src}/stocks/v1/market-sentiment")
        if st == 200 and isinstance(d, dict):
            out[src] = {k: d.get(k) for k in
                        ("buzz_score", "trend", "mentions", "sentiment_score",
                         "bullish_pct", "bearish_pct", "active_tickers")}
            out[src]["drivers"] = [{"ticker": x.get("ticker"), "mentions": x.get("mentions"),
                                    "buzz_score": x.get("buzz_score")}
                                   for x in (d.get("drivers") or [])[:8]]
        else:
            out[src] = _err(st, d) if st else {"error": str(d)[:80]}
    return out


def explain(sym):
    """新闻源单标的解释（1 req；免费档可用，404=数据不足）"""
    if not _key():
        _missing_key()
        return {"skipped": "no_ADANOS_KEY"}
    sym = sym.lstrip("$").upper()
    if not TICKER_RE.match(sym):
        return {"error": f"非法 ticker {sym}", "why": "Adanos 仅美股 ^[A-Za-z]{1,10}$"}
    st, d = _fetch(f"/news/stocks/v1/stock/{sym}/explain")
    if st == 200 and isinstance(d, dict):
        return {"ticker": sym, "explanation": d.get("explanation"),
                "company_name": d.get("company_name"), "cached": d.get("cached")}
    return _err(st, d) if st else {"error": str(d)[:80]}


def trending(src="reddit", typ="stock"):
    """热门榜（1 req），用于候选挖掘"""
    if not _key():
        _missing_key()
        return {"skipped": "no_ADANOS_KEY"}
    if src not in SOURCES:
        return {"error": f"source 须为 {'/'.join(SOURCES)}"}
    st, d = _fetch(f"/{src}/stocks/v1/trending", {"type": typ, "limit": 20})
    if st == 200 and isinstance(d, dict):
        items = d.get("stocks") or d.get("tickers") or []
        return {"source": src, "type": typ,
                "items": [{"ticker": x.get("ticker"), "company_name": x.get("company_name"),
                           "buzz_score": x.get("buzz_score"), "trend": x.get("trend"),
                           "mentions": x.get("mentions"), "sentiment_score": x.get("sentiment_score")}
                          for x in items[:20]]}
    return _err(st, d) if st else {"error": str(d)[:80]}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("sentiment", "market", "explain", "trending"):
        print(__doc__)
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]
    try:
        if cmd == "sentiment":
            if not args:
                out: dict = {"error": "用法: adanos.py sentiment GOOG [NVDA ...]（≤10 只）"}
            else:
                out = sentiment(args)
        elif cmd == "market":
            out = market()
        elif cmd == "explain":
            if not args:
                out = {"error": "用法: adanos.py explain GOOG"}
            else:
                out = explain(args[0])
        else:
            out = trending(args[0] if args else "reddit",
                           args[1] if len(args) > 1 else "stock")
    except Exception as e:
        out = {"error": str(e)[:120], "hint": "Adanos 免费档配额/回看有限，失败不阻断主流程"}
    if isinstance(out, dict) and "quota" not in out:
        q = _quota()
        if q:
            out["quota"] = q
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
