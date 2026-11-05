#!/usr/bin/env python3
"""把用户级技能的「自动 / 显式」状态对齐到配置。幂等，可重复跑。

为什么要它
----------
把低频技能设成 disable-model-invocation 能让它们从每轮的系统提示里消失
（实测整份技能目录约 6500 tokens/轮），但有两件事会把改动冲掉：

  1. `upro init ... --global` 会重写 uupm 那 7 个技能的 SKILL.md
  2. `npx impeccable update` 会重写 impeccable 的 SKILL.md

所以把名单固化成脚本，update 之后跑一次 `--apply` 就恢复。不要手改
frontmatter —— 手改的下一次 update 就丢，而且没人记得改过什么。

名单怎么来的
------------
判定标准（2026-10-04 用户定）：**看这个技能需不需要模型主动触发**，不看使用频次、
更不看装了多久。

  需要主动触发 —— 用户会用自然语言表达这个需求，但不会记得技能名。
    例：「画个架构图」→ fireworks-tech-graph；「做个云南攻略」→ trip-planner。
    → 进 KEEP_AUTO（保持自动），否则它永远不会被想起来。

  不需要主动触发 —— 用户自己会打名字，或只在特定场合点名调用。
    例：DK「仅由用户手动调用（dk/DK）」、gushen、各类被点名的工作流。
    → 降为显式（省每轮 description 开销）。

判据是「用户的请求会不会自然落到这个技能上」，不是「它好不好用」，也不是「它新不新」。

用法
----
    python3 apply_modes.py            # 干跑：只报告会改哪些，不写盘
    python3 apply_modes.py --apply     # 备份后执行，并自验
    python3 apply_modes.py --check     # 只看当前状态是否已对齐（退出码 0/1，可进巡检）
    python3 apply_modes.py --apply -v  # 执行 + 打印保留名单的理由

不在 KEEP_AUTO 里的技能会被降为显式 —— 所以**装完新技能要立即判断它该不该在名单里**
（判据见下），别拖；拖的代价是它被降级后，你再想用就得手打全名。

隔离测试：ASKME_SKILL_ROOTS=/tmp/fake-skills（冒号分隔）可把扫描根整体改道。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # 退化：只抓 name 和 flag，本脚本只需要这两个
    yaml = None

# ── 配置 ────────────────────────────────────────────────────────────
KEEP_AUTO: dict[str, str] = {
    # 每条的值就是它的触发词：用户会这样说，但不会报技能名。
    # 2026-10-22 按 90 天 pi 会话实测收紧：75 个技能只有 8 个被真正 read 过，
    # 其余降为显式（仍可 /ask-me 找到）。这里只留「靠自动触发才起作用」的那批，
    # 与 live 现状保持一致——否则跑一次 apply_modes 就会把降级又升回去。
    # 要恢复某个技能自动注入：把它加回本表，再跑 `python3 apply_modes.py --apply`。
    "d-reach": "搜/查/爬/抓/读",
    "gushen": "股票/行情/投研",
    "ponytail": "写码压量/最简",
    "code-review": "review 分支/PR",
    "show-me": "解释/讲清楚/看不懂",
    "lieflat-less-ai-tone": "去 AI 味改写",
    "taste": "设计/前端/重设计",
    "reverse-engineer-anything": "逆向/拆包/复刻",
    "openviking-docs": "OV 文档/配置",
    "impeccable": "前端界面设计",
    # 入口技能自己藏起来就等于没了 —— 用户不会手打 /ask-me 才来找技能
    "ask-me": "不知道该用哪个技能/有什么技能能用",
}

BACKUP_ROOT = Path.home() / ".agents" / "backups"
FLAG = "disable-model-invocation"


def default_roots() -> list[Path]:
    """用户级技能根。ASKME_SKILL_ROOTS（冒号分隔）可整体改道，隔离测试用。"""
    override = os.environ.get("ASKME_SKILL_ROOTS")
    if override:
        return [Path(p).expanduser() for p in override.split(":") if p.strip()]
    agent_dir = Path(os.environ.get("PI_AGENT_DIR") or os.path.expanduser("~/.pi/agent"))
    return [Path.home() / ".agents" / "skills", agent_dir / "skills"]


# ── frontmatter 读写 ────────────────────────────────────────────────
def split_frontmatter(text: str) -> tuple[str | None, str, str]:
    """返回 (frontmatter 原文或 None, 正文, 原始文本)。"""
    m = re.match(r"^---\n(.*?)\n---[ \t]*\n?", text, re.S)
    if not m:
        return None, text, text
    return m.group(1), text[m.end() :], text


def parse_meta(fm: str) -> tuple[dict, str | None]:
    """解析 frontmatter，返回 (meta, 错误)。无 pyyaml 时退化为正则。"""
    if yaml is None:
        out: dict[str, str] = {}
        for line in fm.splitlines():
            m = re.match(r"^(name|" + re.escape(FLAG) + r"):\s*(.+)$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("\"'")
        return out, None
    try:
        data = yaml.safe_load(fm)
    except Exception as exc:  # 格式坏掉不能把整次巡检带崩
        return {}, str(exc)
    return (data if isinstance(data, dict) else {}), None


def is_pending(row: dict) -> bool:
    """要写盘的动作。跳过只提示，不算。"""
    return not row.get("skip") and row.get("action") != "ok"


def is_explicit(meta: dict) -> bool:
    return str(meta.get(FLAG, "")).strip().lower() == "true"


def add_flag(fm: str) -> str:
    """在 frontmatter 末尾追加 FLAG。块标量安全：追加的是顶级 key。"""
    return f"{fm}\n{FLAG}: true"


def remove_flag(fm: str) -> str:
    return re.sub(rf"(?m)^{re.escape(FLAG)}:.*\n?", "", fm)


# ── 主流程 ──────────────────────────────────────────────────────────
def scan(extra_keep: set[str], roots: list[Path] | None = None) -> list[dict]:
    """扫出所有用户级技能的当前状态与期望动作。"""
    rows: list[dict] = []
    for root in (default_roots() if roots is None else roots):
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            fm, body, _ = split_frontmatter(text)
            if fm is None:
                rows.append({"path": skill_md, "skip": "无 frontmatter", "name": skill_md.parent.name})
                continue
            meta, err = parse_meta(fm)
            if err:
                rows.append({"path": skill_md, "skip": f"YAML 解析失败: {err}", "name": skill_md.parent.name})
                continue
            if not meta.get("name"):
                rows.append({"path": skill_md, "skip": "缺 name", "name": skill_md.parent.name})
                continue

            name = str(meta["name"])
            dirname = skill_md.parent.name
            keep = name in KEEP_AUTO or dirname in KEEP_AUTO or name in extra_keep or dirname in extra_keep
            now_explicit = is_explicit(meta)

            if now_explicit == (not keep):
                action, new_fm = "ok", fm
            elif keep:
                action, new_fm = "升为自动", remove_flag(fm)
            else:
                action, new_fm = "降为显式", add_flag(fm)

            rows.append(
                {
                    "path": skill_md,
                    "name": name,
                    "dirname": dirname,
                    "keep": keep,
                    "now_explicit": now_explicit,
                    "action": action,
                    "new_fm": new_fm,
                    "desc_len": len(" ".join(str(meta.get("description") or "").split())),
                }
            )
    return rows


def describe(rows: list[dict], verbose: bool) -> None:
    pending = [r for r in rows if is_pending(r)]
    skipped = [r for r in rows if r.get("skip")]
    keep_n = sum(1 for r in rows if r.get("keep"))
    exp_n = sum(1 for r in rows if r.get("now_explicit"))
    saved = sum(r.get("desc_len", 0) for r in pending if r["action"] == "降为显式")

    print(f"用户级技能 {len(rows) - len(skipped)} 个：当前自动 {len(rows) - len(skipped) - exp_n} / 显式 {exp_n}")
    print(f"名单内保留自动 {keep_n} 个，其余降级\n")

    if not pending:
        print("状态已对齐，无需改动。")
    else:
        print(f"待改动 {len(pending)} 个（降级可省 {saved} 字符描述）：")
        for r in sorted(pending, key=lambda x: (x["action"], -x.get("desc_len", 0))):
            print(f"  {r['action']:6}  {r['name']:32} {r.get('desc_len', 0):4} 字符  {r['path']}")

    if verbose:
        print("\n保留自动的明细：")
        for r in sorted(rows, key=lambda x: x.get("name", "")):
            if r.get("keep"):
                reason = KEEP_AUTO.get(r.get("name", "")) or KEEP_AUTO.get(r.get("dirname", "")) or "临时保留"
                print(f"  {r.get('name','?'):32} {reason}")

    if skipped:
        print(f"\n跳过 {len(skipped)} 个（格式问题，未动）：")
        for r in skipped:
            print(f"  {r['path']}  —  {r['skip']}")


def backup(paths: list[Path]) -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = BACKUP_ROOT / f"skill-modes-{ts}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for p in paths:
            # 用相对路径存，回滚时能对回原位
            tar.add(p, arcname=str(p).lstrip("/"))
    return out


def rollback(snapshot: Path) -> None:
    """按备份逐个成员恢复。逐成员校验，不用 extractall：
    它对归档内部的绝对路径 / .. 一路放行，而那正是 tar 提取的经典漏洞面。
    """
    import tarfile as tf

    restored = 0
    with tf.open(snapshot, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            target = Path("/" + member.name.lstrip("/"))
            # 只准写回 ~/.agents 与 ~/.pi 两棵树下，别的一律不碰
            resolved = target.resolve()
            roots = [str(Path.home() / ".agents"), str(Path.home() / ".pi")]
            if not any(str(resolved).startswith(r + "/") for r in roots):
                print(f"  跳过越界成员：{member.name}")
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(src.read())
            restored += 1
    print(f"回滚完成：恢复 {restored} 个文件")


def main() -> int:
    ap = argparse.ArgumentParser(description="对齐技能自动/显式状态（幂等）")
    ap.add_argument("--apply", action="store_true", help="写盘；默认只干跑")
    ap.add_argument("--check", action="store_true", help="只看是否已对齐，不列明细")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印保留名单的理由")
    ap.add_argument("--keep", action="append", default=[], metavar="NAME", help="额外保留为自动（可重复）")
    args = ap.parse_args()

    rows = scan(set(args.keep))

    if args.check:
        pending = [r for r in rows if is_pending(r)]
        print(f"{'未对齐' if pending else '已对齐'}：待改动 {len(pending)} 个")
        return 1 if pending else 0

    if args.verbose:
        describe(rows, True)

    if not args.apply:
        if not args.verbose:
            describe(rows, False)
        print("\n（干跑，未写盘。加 --apply 执行）")
        return 0

    pending = [r for r in rows if is_pending(r)]
    if not pending:
        print("状态已对齐，无需改动。")
        return 0

    snapshot = backup([r["path"] for r in pending])
    print(f"备份：{snapshot}")

    failures: list[str] = []
    for r in pending:
        fm, body, _ = split_frontmatter(r["path"].read_text(encoding="utf-8", errors="replace"))
        try:
            r["path"].write_text(f"---\n{r['new_fm']}\n---\n{body}", encoding="utf-8")
        except OSError as exc:
            failures.append(f"{r['path']}: {exc}")

    # 自验：重扫一遍，任何一条没对上就整批回滚
    after = scan(set(args.keep))
    bad = [r for r in after if is_pending(r)]
    if failures or bad:
        print(f"自验失败（{len(failures) + len(bad)} 处），回滚到 {snapshot}")
        rollback(snapshot)
        return 1

    print(f"已改 {len(pending)} 个，自验通过。")
    print(f"回滚命令：tar xzf {snapshot} -C /")
    return 0


if __name__ == "__main__":
    sys.exit(main())
