#!/usr/bin/env python3
"""建技能路由索引：把每个技能压成「名字 + 触发词 + 产物」的一行。

只读 SKILL.md，不改任何技能文件。输出 index.json（就放在本脚本旁边）。

索引的作用是把「让模型扫全库、自己回忆」换成「先离线算好，在线只取前 5 条」：
一百多个技能全塞进上下文会互相稀释，最合适的那个反而沉底。

触发词从三处来：
  ① 描述里写明的「触发词：A / B / C」
  ② 引号里的短语（「画个架构图」这类用户原话）
  ③ 描述与正文前若干字切出的 2–3 字中文 n-gram + 英文标识符，按全局稀有度筛

用法：
  build_index.py             # 重建索引
  build_index.py --stats     # 只报统计，不写文件
  build_index.py --out PATH  # 换输出位置
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_skills as ss  # noqa: E402

READ_LIMIT = 8000          # 每个 SKILL.md 最多读这么多字符，正文尾部对路由没价值
BODY_KW_MAX = 120          # 正文贡献的关键词上限（描述的不限，它才是触发场景）
GRAM_RANGE = (2, 3)        # 中文 n-gram 长度

# 高频无意义片段：出现在几乎每个技能描述里，留着只会拉高噪声
STOP_ZH = {
    "技能", "用户", "使用", "可以", "需要", "支持", "处理", "生成", "用于", "提供",
    "通过", "进行", "相关", "内容", "任务", "文件", "时候", "不要", "不是", "这个",
    "什么", "怎么", "如何", "以及", "或者", "并且", "已经", "如果", "因为", "所以",
    "这些", "那些", "自己", "我们", "他们", "当前", "指定", "默认", "自动", "直接",
    "方案", "问题", "东西", "情况", "方面", "部分", "时候", "方法", "方式", "地方",
    "事情", "过程", "结果", "效果", "样子", "意思",
    "要不", "要不要", "是不是", "有没有", "能不能", "行不行", "好不好", "对不对",
    "我把", "帮我把", "把这段", "这样", "那样", "一点", "点儿", "然后", "还有",
}
STOP_EN = {
    "the", "and", "for", "with", "you", "this", "that", "are", "was", "has", "have",
    "not", "but", "can", "will", "when", "from", "your", "use", "used", "using",
    "skill", "skills", "md", "true", "false", "none", "http", "https", "www", "com",
}

# 产物类型：命中就给这个技能贴一个「交回什么」的标签
PRODUCT_RULES: list[tuple[str, str]] = [
    ("讲解页", r"\.html|讲解页|交互页|可视化页面|网页|展示页|原型|幻灯片|ppt"),
    ("图", r"\.svg|示意图|架构图|图表|diagram|流程图|拓扑"),
    ("报告", r"报告|研报|分析报告|摘要报告"),
    ("代码", r"代码|补丁|diff|重构|实现方案|单元测试|测试用例"),
    ("检索", r"搜索|检索|抓取|爬取|正文提取|查询结果"),
    ("文档", r"文档|笔记|markdown|说明书|README"),
    ("数据", r"\.csv|数据集|表格数据|json 快照|索引"),
    ("音视频", r"视频|音频|字幕|配音|转写"),
    ("记忆", r"记忆|记忆库|长期上下文|归档"),
    ("配置", r"配置|部署|安装|容器|systemd|nginx|代理规则"),
]

RE_TRIGGER = re.compile(r"触发词[:：]\s*([^\n。]{2,120})")
RE_QUOTED = re.compile(r"[「『“\"]([^」』”\"]{2,24})[」』”\"]")
RE_EN = re.compile(r"[a-zA-Z][a-zA-Z0-9_.\-]{2,}")
# 边界虚词：2–3 gram 首尾是这些时丢掉，「个方案」「把这段」这类跨词边界的假词会永久污染索引
EDGE_CHARS = set("的了着过个把被和与或就都也还又很太更最不没在是有这那我你他她它们")

RE_ZH_RUN = re.compile(r"[\u4e00-\u9fff]+")


def zh_grams(text: str) -> set[str]:
    """中文连续串切 2–3 gram，去掉纯停用片段。"""
    out: set[str] = set()
    for run in RE_ZH_RUN.findall(text):
        n = len(run)
        for size in range(GRAM_RANGE[0], GRAM_RANGE[1] + 1):
            for i in range(n - size + 1):
                gram = run[i : i + size]
                if gram[0] in EDGE_CHARS or gram[-1] in EDGE_CHARS:
                    continue
                if gram in STOP_ZH:
                    continue
                out.add(gram)
    return out


def en_tokens(text: str) -> set[str]:
    return {t.lower() for t in RE_EN.findall(text) if t.lower() not in STOP_EN}


def explicit_triggers(text: str) -> set[str]:
    """描述里明写的触发词 + 引号短语，优先级最高。"""
    out: set[str] = set()
    for block in RE_TRIGGER.findall(text):
        for piece in re.split(r"[/、|，,\s]+", block):
            piece = piece.strip()
            if 2 <= len(piece) <= 16:
                out.add(piece)
    for phrase in RE_QUOTED.findall(text):
        phrase = phrase.strip()
        if 2 <= len(phrase) <= 16:
            out.add(phrase)
    return out


def products(text: str) -> list[str]:
    hits = [label for label, pat in PRODUCT_RULES if re.search(pat, text, re.IGNORECASE)]
    return hits[:2] if hits else ["—"]


def collect(agent_dir: Path) -> tuple[list[dict], list[str]]:
    """扫全部技能，返回 (原始条目, 警告)。"""
    roots: list[tuple[str, Path]] = []
    seen_roots: set[Path] = set()

    def add_root(scope: str, path: Path) -> None:
        real = path.resolve()
        if real in seen_roots:
            return
        seen_roots.add(real)
        roots.append((scope, path))

    for scope, template in ss.ROOTS:
        path = ss.expand(template, agent_dir)
        if path:
            add_root(scope, path)
    for path in ss.package_roots(agent_dir):
        add_root("package", path)

    rows: list[dict] = []
    warnings: list[str] = []
    by_name: dict[str, dict] = {}

    for scope, root in roots:
        for skill_md in ss.skill_files(root):
            if skill_md.parent.name.startswith("."):
                continue
            try:
                text = skill_md.read_text(encoding="utf-8", errors="replace")[:READ_LIMIT]
            except OSError as exc:
                warnings.append(f"{skill_md}: {exc}")
                continue
            meta = ss.parse_frontmatter(text)
            name = str(meta.get("name") or "").strip()
            if not name:
                continue
            desc = " ".join(str(meta.get("description") or "").split())
            body = text
            head = desc + " " + body

            # 描述是人工写的触发场景，全部保留；正文只留最稀有的那批，避免长文霸榜
            kw = explicit_triggers(desc) | zh_grams(desc) | en_tokens(desc)
            body_kw = zh_grams(text) | en_tokens(text)
            real = str(skill_md.resolve())

            entry = {
                "name": name,
                "path": real,
                "mode": "explicit" if meta.get("disable-model-invocation") else "auto",
                "scope": scope,
                "desc": desc[:160],
                "product": products(text),
                "kw": sorted(kw),
                "bkw": sorted(body_kw),
            }
            prev = by_name.get(name)
            if prev is None:
                by_name[name] = entry
                continue
            # 同名多份：保留路径更短的那份（少一层软链），另一份只在内容不同时告警
            if len(real) < len(prev["path"]):
                by_name[name] = entry
            if prev["kw"] != entry["kw"]:
                warnings.append(f"重名技能 {name}：两份内容不同，取路径更短者")

    rows = list(by_name.values())
    return rows, warnings


def build(rows: list[dict]) -> dict:
    """正文关键词按全局稀有度裁一刀；描述关键词全部保留。不存 df 表，路由时现算。"""
    df: dict[str, int] = {}
    for row in rows:
        for kw in set(row["kw"]) | set(row["bkw"]):
            df[kw] = df.get(kw, 0) + 1

    for row in rows:
        desc_kw = set(row.pop("kw"))
        body_kw = sorted(set(row.pop("bkw")), key=lambda k: (df.get(k, 0), -len(k)))[:BODY_KW_MAX]
        row["kw"] = sorted(desc_kw | set(body_kw))

    return {
        "version": 3,
        "built_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "total": len(rows),
        "gram_range": list(GRAM_RANGE),
        "skills": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="建技能路由索引")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "index.json"))
    ap.add_argument("--stats", action="store_true", help="只报统计，不写文件")
    args = ap.parse_args()

    agent_dir = Path(os.environ.get("PI_AGENT_DIR") or os.path.expanduser("~/.pi/agent"))
    rows, warnings = collect(agent_dir)
    if not rows:
        print("没扫到任何技能，检查 PI_AGENT_DIR 或扫描根。", file=sys.stderr)
        return 1

    data = build(rows)
    n_kw = sum(len(r["kw"]) for r in data["skills"])
    n_explicit = sum(1 for r in data["skills"] if r["mode"] == "explicit")

    print(f"技能 {data['total']} 个（显式 {n_explicit} / 自动 {data['total'] - n_explicit}）")
    print(f"关键词 {n_kw} 个，平均每个技能 {n_kw // max(data['total'], 1)} 个")

    if warnings:
        print("\n警告：")
        for w in warnings[:10]:
            print("  " + w)

    if args.stats:
        return 0

    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n写入 {out}（{out.stat().st_size / 1024:.1f} KB）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
