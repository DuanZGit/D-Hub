#!/usr/bin/env python3
"""为 D-Hub 每个包生成一张 1200x630 封面图（docs/covers/<slug>.png）。

pi.dev 画廊读 package.json 的 `pi.image`；README 顶部也用同一张图。
纯 PIL + Noto Sans CJK，无外部依赖。
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "covers")
CJK_BOLD = "/home/duanz/.local/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"
CJK_REG = "/home/duanz/.local/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"
MONO = "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf"

W, H = 1200, 630
BG_TOP = (15, 21, 38)
BG_BOT = (26, 32, 56)

# slug: (title_zh, subtitle_zh, accent, glyph)
COVERS = {
    "auto-name": ("自动会话命名", "消息涨到阈值，标题自己改名", "#6ee7b7", "A"),
    "d-live": ("实时内心独白", "把思考与工具调用写成进度播报", "#a78bfa", "~"),
    "d-split": ("会话按切点拆分", "聊偏了，一刀切成两个独立会话", "#f472b6", "|"),
    "goal-guard": ("目标守卫", "把本次目标钉进系统提示", "#34d399", "◎"),
    "pi-cmd-guard": ("命令硬拦截", "会打印密钥的命令，根本发不出去", "#f87171", "▮"),
    "pi-web-patch-keeper": ("补丁守夜人", "pi-web 升级冲掉的本地补丁自动重放", "#fbbf24", "◇"),
    "skill-search": ("技能按需检索", "技能目录不必常驻，留一个查询入口", "#60a5fa", "☰"),
    "skill-trigger": ("技能触发门禁", "该走统一路由的时候，别绕过去", "#38bdf8", "⌁"),
    "sol-pi-stats": ("Token 状态栏", "省下的上下文，常驻显示出来", "#c084fc", "%"),
    "d-restart": ("安全重启", "重启前记下谁在干活，起来再叫醒", "#2dd4bf", "↻"),
}


def hexrgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.truetype(path, size)


def gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        c = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def decorate(img: Image.Image, accent: tuple[int, int, int]) -> None:
    """低透明度网格 + 右上角光斑，避免纯色单调。"""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, W, 48):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 8), width=1)
    for y in range(0, H, 48):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 8), width=1)
    for r, a in ((360, 26), (280, 34), (200, 44)):
        d.ellipse([W - 300 - r, -r + 190, W - 300 + r, r + 190], fill=accent + (a,))
    img.alpha_composite(layer) if img.mode == "RGBA" else img.paste(
        Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"), (0, 0)
    )


def badge(d: ImageDraw.ImageDraw, x: int, y: int, text: str, accent) -> None:
    f = font(MONO, 22)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([x, y, x + tw + 32, y + 42], radius=21, outline=accent + (150,), width=2)
    d.text((x + 16, y + 8), text, font=f, fill=accent)


def cover(slug: str, title: str, sub: str, accent_hex: str, glyph: str) -> str:
    accent = hexrgb(accent_hex)
    base = gradient(W, H).convert("RGBA")
    decorate(base, accent)
    d = ImageDraw.Draw(base)

    # 左侧主色竖条
    d.rounded_rectangle([64, 96, 72, 534], radius=4, fill=accent)

    badge(d, 96, 96, "PI PACKAGE  ·  D-HUB", accent)

    f_title = font(CJK_BOLD, 84)
    d.text((96, 196), title, font=f_title, fill=(240, 244, 255))

    f_sub = font(CJK_REG, 32)
    d.text((100, 320), sub, font=f_sub, fill=(150, 162, 190))

    f_pkg = font(MONO, 26)
    d.text((100, 452), f"npm  @duanz/pi-{slug}", font=f_pkg, fill=(120, 132, 160))
    f_install = font(MONO, 24)
    d.text((100, 492), f"pi install npm:@duanz/pi-{slug}", font=f_install, fill=accent)

    # 右侧大字标记
    f_glyph = font(MONO, 300)
    tw = d.textlength(glyph, font=f_glyph)
    d.text((W - 150 - tw, 180), glyph, font=f_glyph, fill=accent + (46,))

    # 底部签名
    f_sig = font(MONO, 20)
    d.text((100, 560), "github.com/DuanZGit/D-Hub", font=f_sig, fill=(96, 106, 130))

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{slug}.png")
    base.convert("RGB").save(path, "PNG", optimize=True)
    return path


if __name__ == "__main__":
    for slug, (t, s, a, g) in COVERS.items():
        print(cover(slug, t, s, a, g))
