#!/usr/bin/env python3
import re, sys
from pathlib import Path
AGENTS=["巴菲特","芒格","段永平","李录","技术分析师","动量交易员","情绪分析师","风控官"]
GATES=["data-gate","value-gate","trading-gate","cross-check","decision-gate"]
REQUIRED=["价值投资共识","Trading 共识","共识点","分歧点","冲突点","取舍逻辑"]
PLACEHOLDER_RE=re.compile(r"\[(?:评分|核心判断|关键判断|一句话|标的名称|股票名称|待填写|TODO)[^\]]*\]")
def fail(m): print("FAIL: "+m)
def main():
    if len(sys.argv)!=2: print("usage: validate_report.py REPORT.html",file=sys.stderr); return 2
    p=Path(sys.argv[1])
    if not p.is_file(): fail(f"file not found: {p}"); return 1
    t=p.read_text(encoding='utf-8',errors='replace')
    errs=[]
    for g in GATES:
        if g not in t: errs.append(f"missing gate marker: {g}")
        if f'data-gate="{g}"' not in t and f'id="{g}"' not in t: errs.append(f"missing structural gate marker: {g}")
    for a in AGENTS:
        if a not in t: errs.append(f"missing agent: {a}")
    if "基本面分析师" in t and "不使用" not in t: errs.append("legacy extra agent appears: 基本面分析师")
    for x in REQUIRED:
        if x not in t: errs.append(f"missing required section/text: {x}")
    # 统一 5 分制，按 Agent 卡边界检 /10 残留
    for a in AGENTS:
        for m in re.finditer(re.escape(a),t):
            # 取 Agent 卡窗口
            s=max(0,t.rfind('<div class="agent',0,m.start()))
            nearby=t[s:s+3500] if s>=0 else t[m.start():m.start()+3000]
            # 排除 VIX/10Y 等宏观缩写误伤
            cleaned=re.sub(r"VIX\s*/\s*10Y?", "", nearby)
            if re.search(r"/\s*10",cleaned): errs.append(f"legacy 10-point near {a}"); break
    for a in AGENTS:
        near=[]
        for m in re.finditer(re.escape(a),t):
            s=t.rfind('<div class="agent',0,m.start())
            if s>=0: near.append(t[s:s+3500])
        chunk="\n".join(near[:2])
        if chunk and not re.search(r"/\s*5",chunk): errs.append(f"agent has no 5-point score: {a}")
        if chunk and "结论" not in chunk and "agent-concl" not in chunk: errs.append(f"agent has no conclusion: {a}")
    # 纪律词：有即最好，无不拦（prompt 约束，不靠字数执法）
    ph=PLACEHOLDER_RE.findall(t)
    if ph: errs.append("unresolved placeholders: "+", ".join(sorted(set(ph))[:3]))
    hits=sum(1 for kws in [["ROE","roe"],["beta","Beta","β"],["评级","strongBuy"],["surprise","EPS","miss"],["52周","52W"],["量比","volume_ma","缩量"],["VIX","10Y"],["北向","资金流"]] if any(k in t for k in kws))
    if hits<6: errs.append(f"deep-data bindings insufficient: {hits}/8 (need >=6)")
    if errs:
        for e in errs: fail(e)
        print(f"REPORT_INVALID errors={len(errs)}"); return 1
    print(f"REPORT_VALID agents={len(AGENTS)} gates={len(GATES)} file={p}"); return 0
if __name__=="__main__": raise SystemExit(main())
