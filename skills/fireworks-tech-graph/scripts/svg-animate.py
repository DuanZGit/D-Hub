#!/usr/bin/env python3
"""给 fireworks-tech-graph 生成的 SVG 注入原生 CSS 动画。

效果：节点依次淡入 → 连线按 data-motion-stage 依次描边画出 → 箭头在所在线
画到末端时才出现 → 循环。

输出仍是单个自包含 SVG —— 无 GIF、无 ffmpeg、无外部依赖，缩放到任何尺寸都清晰。

用法:  svg-animate.py input.svg output.svg [周期秒数]
"""
import re
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
TOTAL = float(sys.argv[3]) if len(sys.argv) > 3 else 7.0
svg = src.read_text(encoding="utf-8")

# ── 1. 给 edge path 打上 pathLength=1（长度归一化，CSS 才知道描边进度）
def patch(m: re.Match) -> str:
    tag = m.group(0)
    if "pathLength" in tag:
        return tag
    if tag.endswith("/>"):                       # 自闭合：属性要插在斜杠之前
        return tag[:-2].rstrip() + ' pathLength="1"/>'
    return tag[:-1].rstrip() + ' pathLength="1">'

svg, n_edge = re.subn(r'<path[^>]*data-graph-role="edge"[^>]*>', patch, svg)

# ── 2. 收顺序与箭头引用
edges = sorted({(i, int(s)) for i, s in
                re.findall(r'<path id="([^"]+)"[^>]*data-motion-stage="(\d+)"', svg)},
               key=lambda x: (x[1], x[0]))
markers = {m.group(1): m.group(2) for m in
           re.finditer(r'<path\s+id="([^"]+)"[^>]*?marker-end="([^"]+)"[^>]*>', svg)}
nodes = re.findall(r'<g id="(node-[^"]+)"', svg)

# ── 3. 生成 CSS
css = ["/* injected: native CSS animation — node fade-in + edge draw-on + arrow on arrival */"]

for i, nid in enumerate(nodes):                  # 节点依次淡入
    t0, t1 = 0.05 * i, 0.05 * i + 0.45
    css.append(f"#{nid}{{opacity:0;animation:f-{nid} {TOTAL}s ease infinite}}"
               f"@keyframes f-{nid}{{0%,{t0/TOTAL*100:.1f}%{{opacity:0}}"
               f"{t1/TOTAL*100:.1f}%,86%{{opacity:1}}100%{{opacity:0}}}}")

for i, (eid, _stage) in enumerate(edges):
    t0 = 0.6 + i * 0.5                           # 描边起止
    t1 = t0 + 0.7
    mref = markers.get(eid)
    anim = f"d-{eid} {TOTAL}s linear infinite"
    if mref:
        anim += f",m-{eid} {TOTAL}s linear infinite"
    css.append(f"#{eid}{{stroke-dasharray:1;stroke-dashoffset:1;"
               f"marker-end:{mref or 'none'};animation:{anim}}}")
    css.append(f"@keyframes d-{eid}{{0%,{t0/TOTAL*100:.1f}%{{stroke-dashoffset:1}}"
               f"{t1/TOTAL*100:.1f}%,88%{{stroke-dashoffset:0}}100%{{stroke-dashoffset:1}}}}")
    if mref:                                     # 箭头：描边到末端之前不出现
        tm = max(0.0, t1 - 0.12)
        css.append(f"@keyframes m-{eid}{{0%,{tm/TOTAL*100:.1f}%{{marker-end:none}}"
                   f"{t1/TOTAL*100:.1f}%,88%{{marker-end:{mref}}}"
                   f"99.9%{{marker-end:{mref}}}100%{{marker-end:none}}}}")

svg = svg.replace("</style>", "\n".join(css) + "\n</style>", 1)
dst.write_text(svg, encoding="utf-8")
print(f"  {n_edge} 条边 / {len(nodes)} 个节点 / {len(markers)} 个箭头已注入 → {dst}")
