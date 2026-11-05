#!/usr/bin/env python3
"""把 fireworks 的横版 JSON 重排成手机竖版：容器内节点竖排，容器依次下移。"""
import json, sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
W = int(sys.argv[3]) if len(sys.argv) > 3 else 460
d = json.loads(src.read_text(encoding="utf-8"))

MARGIN, PAD_TOP, PAD_BOT, GAP, CONT_GAP, HEADER_H = 18, 40, 18, 68, 30, 116
NODE_H = 58
inner_w = W - 2 * MARGIN
node_w  = inner_w - 48
node_x  = MARGIN + 24

def inside(n, c):
    return (c["x"] - 3 <= n["x"] and n["x"] + n["width"]  <= c["x"] + c["width"] + 3 and
            c["y"] - 3 <= n["y"] and n["y"] + n["height"] <= c["y"] + c["height"] + 3)

conts = sorted(d["containers"], key=lambda c: c["y"])
used, groups = set(), []
for c in conts:
    mem = [n for n in d["nodes"] if n["id"] not in used and inside(n, c)]
    used.update(m["id"] for m in mem)
    groups.append((c, sorted(mem, key=lambda n: n["x"])))
rest = [n for n in d["nodes"] if n["id"] not in used]
if rest:
    groups.append((None, sorted(rest, key=lambda n: (n["y"], n["x"]))))

y = HEADER_H
for c, mem in groups:
    if c is None:
        for n in mem:
            n.update(x=node_x, y=y, width=node_w, height=NODE_H); y += NODE_H + GAP
        y += CONT_GAP; continue
    ch = PAD_TOP + len(mem) * NODE_H + max(0, len(mem) - 1) * GAP + PAD_BOT
    c.update(x=MARGIN, y=y, width=inner_w, height=ch)
    ny = y + PAD_TOP
    for n in mem:
        n.update(x=node_x, y=ny, width=node_w, height=NODE_H); ny += NODE_H + GAP
    y += ch + CONT_GAP

for a in d["arrows"]:                      # 竖排 → 全部走上下端口
    pass  # 保留原端口：动效引擎按方向约定校验 ingress=right

# 超长文字在窄画布下会溢出，粗估后截断
for _k in ("title", "subtitle"):
    _v = str(d.get(_k) or "")
    _limit = int(W / (7.6 if _k == "title" else 6.2))
    if len(_v) > _limit:
        d[_k] = _v[: _limit - 1].rstrip(" ,·") + "…"

d["width"]  = W
d["legend_orientation"] = "vertical"
d["legend_x"], d["legend_y"] = MARGIN, y - CONT_GAP + 6
d["footer_x"], d["footer_y"] = MARGIN, y - CONT_GAP + 6 + 150
d["height"] = int(y - CONT_GAP + 210)

dst.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"  {W}x{d['height']}  →  {dst}")
