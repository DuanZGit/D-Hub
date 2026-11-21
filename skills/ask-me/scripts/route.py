#!/usr/bin/env python3
"""按一句话诉求取前 N 个候选技能。

不做全库回忆，只做关键词打分：诉求切词 → 命中累加（按全局稀有度加权）→ 排序取前 N。
毫秒级，结果稳定可复现，不需要向量库。

用法：
  route.py "画个架构图"              # 前 5 条，紧凑表
  route.py "画个架构图" --top 3      # 换条数
  route.py "画个架构图" --json       # 结构化，供程序消费
  route.py "画个架构图" --explain    # 附带每条命中了哪些词

索引不存在时会提示先跑 build_index.py。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parent / "index.json"
TRIGGERS_PATH = Path(__file__).resolve().parent / "triggers.json"

STOP_ZH = {
    "技能", "用户", "使用", "可以", "需要", "支持", "处理", "生成", "用于", "提供",
    "通过", "进行", "相关", "内容", "任务", "文件", "时候", "不要", "不是", "这个",
    "什么", "怎么", "如何", "以及", "或者", "并且", "已经", "如果", "因为", "所以",
    "帮我", "一下", "一个", "这个", "那个", "现在", "然后", "还有", "就是",
    "方案", "问题", "东西", "情况", "方面", "部分", "时候", "方法", "方式", "地方",
    "事情", "过程", "结果", "效果", "样子", "意思",
    "要不", "要不要", "是不是", "有没有", "能不能", "行不行", "好不好", "对不对",
    "我把", "帮我把", "把这段", "这样", "那样", "一点", "点儿", "然后", "还有",
}
EDGE_CHARS = set("的了着过个把被和与或就都也还又很太更最不没在是有这那我你他她它们")

STOP_EN = {
    "the", "and", "for", "with", "you", "this", "that", "are", "was", "has", "have",
    "not", "but", "can", "will", "when", "from", "your", "use", "used", "using",
}

RE_EN = re.compile(r"[a-zA-Z][a-zA-Z0-9_.\-]{2,}")
RE_ZH_RUN = re.compile(r"[\u4e00-\u9fff]+")

NAME_BONUS = 8.0     # 诉求里直接报出技能名
PRODUCT_BONUS = 2.0  # 诉求里出现产物类型（报告 / 讲解页 / 代码…）
LONG_GRAM_W = 1.5    # 3 字词比 2 字词更判别，加权
MANUAL_W = 3.0       # 人工触发词表的命中权重（人写的触发词比描述里的偶然词可靠得多）
MUTED_W = 0.15       # 家族内共有词的权重："百炼""模型"对「该不该用百炼」零信息
BM25_B = 0.75        # 长度归一强度：技能词表越长，命中越不唬人
MIN_SCORE = 8.0      # 低于此分就是没对口技能：凑一个 3 分的答案比说“没有”更坑人

# 从聊天里粘过来的噪声：脱敏占位符、图片标记、安全前缀
RE_NOISE = re.compile(r"(@mx_[a-z_]+|__SECRET_[A-Z0-9_]+__|\{\{[^}]{1,64}\}\}|\[Image:[^\]]{0,120}\])")

# 口语 → 书面词：用户说「搜一下」，描述里写的是「搜索」「检索」
SYNONYMS: dict[str, tuple[str, ...]] = {
    "搜": ("搜索", "检索"),
    "查": ("搜索", "检索", "查询"),
    "找": ("搜索", "查找", "检索"),
    "抓": ("抓取", "提取", "爬"),
    "爬": ("抓取", "爬取"),
    "读": ("正文", "阅读", "抽取"),
    "讲": ("解释", "讲解"),
    "解释": ("讲解", "说明"),
    "懂": ("解释", "理解"),
    "图": ("图表", "示意图", "架构图"),
    "画": ("图表", "示意图", "绘制"),
    "代码": ("编程", "实现", "重构"),
    "改": ("修改", "重构", "调整"),
    "写": ("编写", "实现", "生成"),
    "报": ("报告",),
    "记": ("记忆", "记录"),
    "选": ("选择", "推荐", "选型"),
    "哪个": ("选择", "对比", "推荐"),
    "推荐": ("选型", "对比"),
    "慢": ("性能", "优化"),
    "卡": ("性能", "排查"),
    "错": ("报错", "调试", "排查"),
    "崩": ("报错", "排查"),
}


def query_tokens(text: str) -> set[str]:
    """诉求切词：2–3 字中文 gram + 英文标识符。"""
    out: set[str] = set()
    for run in RE_ZH_RUN.findall(text):
        n = len(run)
        for size in (2, 3):
            for i in range(n - size + 1):
                gram = run[i : i + size]
                if gram[0] in EDGE_CHARS or gram[-1] in EDGE_CHARS:
                    continue
                if gram not in STOP_ZH:
                    out.add(gram)
    out |= {t.lower() for t in RE_EN.findall(text) if t.lower() not in STOP_EN}

    # 口语扩展：原文里出现了某个口词，就把对应书面词补进候选
    for spoken, formal in SYNONYMS.items():
        if spoken in text:
            out.update(formal)
    return out


def load_index(path: Path) -> dict:
    if not path.is_file():
        print(f"没有索引：{path}\n先跑 python3 {path.parent / 'build_index.py'}", file=sys.stderr)
        raise SystemExit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"索引读不出来（{exc}），重跑 build_index.py：{path}", file=sys.stderr)
        raise SystemExit(2) from exc
    for key in ("total", "skills"):
        if key not in data:
            print(f"索引缺字段 {key}，重跑 build_index.py：{path}", file=sys.stderr)
            raise SystemExit(2)
    return data


def load_triggers(path: Path) -> dict[str, list[str]]:
    """人工触发词表。缺文件不致命：自动索引自己也能跑，只是口语召回差一点。"""
    if not path.is_file():
        print(f"提示：没找到 {path.name}，只用自动索引", file=sys.stderr)
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"提示：{path.name} 读不出来（{exc}），跳过", file=sys.stderr)
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, list)}


def score_all(data: dict, query: str, manual: dict[str, list[str]] | None = None) -> list[dict]:
    toks = query_tokens(query)
    q_low = query.lower()
    total = data["total"]

    # df 现算：不存进索引，省一半体积；117 个技能累加一次是毫秒级
    df: dict[str, int] = {}
    for row in data["skills"]:
        for kw in row["kw"]:
            df[kw] = df.get(kw, 0) + 1

    def idf(kw: str) -> float:
        return math.log((total + 1) / (df.get(kw, 0) + 0.5))

    def weight(kw: str) -> float:
        w = LONG_GRAM_W if len(kw) >= 3 else 1.0
        d = df.get(kw, 0)
        if d >= total * 0.45:   # 遍地都是的词降权，不能让“图”“搜索”决定排序
            w *= 0.4
        elif d <= 1:            # 只在一个技能里出现过 → 多半是那句描述的偶然片段，不可靠
            w *= 0.5
        return w

    manual = manual or {}
    muted_map = data.get("muted") or {}
    results: list[dict] = []
    avg_kw = (sum(len(r["kw"]) for r in data["skills"]) / len(data["skills"])) or 167.0
    for row in data["skills"]:
        kwset = set(row["kw"])
        hits = toks & kwset
        fam = row["name"].split("-")[0]
        muted = set(muted_map.get(fam, ()))
        raw = sum(weight(k) * idf(k) * (MUTED_W if k in muted else 1.0) for k in hits)

        # BM25 式的长度归一：d-reach 548 个词、bailian-gen 365 个，而平均 167。
        # 不归一的话描述长的技能先天空赢——任何一句话都能从它那儿撞到一个词。
        norm = max(0.5, 1 - BM25_B + BM25_B * (len(kwset) / avg_kw))
        score = raw / norm

        # 人工词表里写的是短语（"先写测试""上次说的"），三个字以上切词切不出来，
        # 所以直接在原句上找子串，不靠 token 集合。精确信号不参与长度归一。
        mhits = {k for k in manual.get(row["name"], []) if k in query}
        if mhits:
            score += sum(MANUAL_W * (LONG_GRAM_W if len(k) >= 3 else 1.0) * idf(k) for k in mhits)
            hits = hits | mhits

        # 多个词同时吐合比单个罕见词更可信；但只算没被家族抑制的词
        effective = {k for k in hits if k not in muted} if muted else hits
        if len(effective) > 1:
            score *= 1 + 0.25 * (len(effective) - 1)

        name = row["name"].lower()
        if name and (name in q_low or name.replace("-", "") in q_low.replace("-", "").replace(" ", "")):
            score += NAME_BONUS

        for prod in row.get("product", []):
            if prod != "—" and prod in query:
                score += PRODUCT_BONUS
                break

        if score > 0:
            results.append(
                {
                    "name": row["name"],
                    "score": round(score, 2),
                    "mode": row["mode"],
                    "product": "/".join(row.get("product", [])),
                    "hits": sorted(hits, key=lambda k: -idf(k))[:6],
                    "path": row["path"],
                }
            )

    # 同族抑制：bailian-cli / bailian-gen / bailian-* 这类共享十几个词，
    # 不抑制就会把前 10 名全刷成一个家族。用户要的是 1-2 个答案，同族只需最高分那条。
    best_by_family: dict[str, float] = {}
    for r in results:
        fam = r["name"].split("-")[0]
        if fam not in best_by_family or r["score"] > best_by_family[fam]:
            best_by_family[fam] = r["score"]
    for r in results:
        fam = r["name"].split("-")[0]
        if r["score"] < best_by_family[fam]:
            r["score"] *= 0.35
            r["family_muted"] = True

    results.sort(key=lambda r: (-r["score"], r["name"]))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="按诉求路由到候选技能")
    ap.add_argument("query", nargs="+", help="用户的话，原样贴进来")
    ap.add_argument("--top", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--explain", action="store_true", help="显示每条命中的词")
    ap.add_argument("--index", default=str(INDEX_PATH))
    args = ap.parse_args()

    query = RE_NOISE.sub(" ", " ".join(args.query)).strip()
    data = load_index(Path(args.index))
    manual = load_triggers(TRIGGERS_PATH)
    all_results = score_all(data, query, manual)
    results = [r for r in all_results if r["score"] >= MIN_SCORE]

    if args.json:
        print(json.dumps({"query": query, "count": len(results), "results": results[: args.top]},
                         ensure_ascii=False, indent=1))
        return 0

    if not results:
        best = all_results[0] if all_results else None
        if best:
            print(f"「{query}」→ 无对口技能（最高只有 {best['score']} 分，门槛 {MIN_SCORE}）。")
            print(f"  最近沾边的是 {best['name']}，但没到门槛就别勉强——直接做。")
        else:
            print(f"「{query}」→ 无命中。换个说法，或用 scan_skills.py --grep 直接找名字。")
        return 0

    print(f"# 「{query}」→ {len(results)} 个命中，前 {min(args.top, len(results))} 条\n")
    for i, r in enumerate(results[: args.top], 1):
        flag = "显式" if r["mode"] == "explicit" else "自动"
        line = f"{i}. {r['name']:<28} [{flag}] {r['product']}  {r['score']}"
        print(line)
        if args.explain:
            print(f"      命中：{' / '.join(r['hits'])}")
        print(f"      {r['path']}")

    if len(results) > args.top:
        print(f"\n（另有 {len(results) - args.top} 条，--top 放宽）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
