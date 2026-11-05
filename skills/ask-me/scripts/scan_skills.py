#!/usr/bin/env python3
"""which-skill 扫描器：列出本机全部已安装技能（名称 / 触发方式 / 描述）。

只读，不写任何文件。默认输出紧凑文本表，供模型看完直接做推荐。

用法：
  scan_skills.py                 # 全量文本表
  scan_skills.py --json          # 结构化输出
  scan_skills.py --grep 设计      # 按名称+描述过滤（不区分大小写）
  scan_skills.py --check-index   # 额外报出未登记进 INDEX.md 的技能
  scan_skills.py --roots         # 只列扫描根与各自数量
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # 退化：无 pyyaml 时用简易解析
    yaml = None

DESC_MAX = 240

# 扫描根：(标签, 路径模板)。~ 与 <agent> 由 main() 展开。
ROOTS: list[tuple[str, str]] = [
    ("user", "<agent>/skills"),
    ("user", "~/.agents/skills"),
    ("project", "./.pi/skills"),
    ("project", "./.agents/skills"),
]


def expand(template: str, agent_dir: Path) -> Path | None:
    """展开 ~ 和 <agent>；相对路径按 cwd 解析。"""
    if template.startswith("./"):
        path = Path.cwd() / template[2:]
    else:
        path = Path(os.path.expanduser(template.replace("<agent>", str(agent_dir))))
    return path if path.is_dir() else None


def package_roots(agent_dir: Path) -> list[Path]:
    """pi 包自带的技能：npm 包下 skills/* 与 plugins/*/。"""
    found: list[Path] = []
    npm = agent_dir / "npm" / "node_modules"
    if npm.is_dir():
        found += sorted(npm.glob("*/skills"))
        found += sorted(npm.glob("*/plugins/*"))
    return [p for p in found if p.is_dir()]


def skill_files(root: Path) -> list[Path]:
    """root 自身的 SKILL.md（包直接当技能目录时）加上各子目录的 SKILL.md。"""
    files: list[Path] = []
    if (root / "SKILL.md").is_file():
        files.append(root / "SKILL.md")
    files += sorted(root.glob("*/SKILL.md"))
    return files


def parse_frontmatter(text: str) -> dict:
    """取 SKILL.md 头部 YAML。解析失败返回空 dict，不抛异常。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    raw = text[3:end]
    if yaml is not None:
        try:
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    # 退化解析：只抓 name / description 的单行值
    out: dict[str, str] = {}
    for line in raw.splitlines():
        m = re.match(r"^(name|description):\s*(.+)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def clean_desc(value: object) -> str:
    """压平空白 + 截断，保证一行一条。"""
    text = " ".join(str(value or "").split())
    return text[:DESC_MAX] + ("…" if len(text) > DESC_MAX else "")


def scan(agent_dir: Path, roots: list[tuple[str, Path]]) -> list[dict]:
    """遍历所有根，收集技能。同名技能全部保留，供调用方发现冲突。"""
    skills: list[dict] = []
    for scope, root in roots:
        for skill_md in skill_files(root):
            if skill_md.parent.name.startswith("."):
                continue
            try:
                meta = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if not meta.get("name"):
                continue
            skills.append(
                {
                    "name": str(meta["name"]),
                    "dir": skill_md.parent.name,
                    "mode": "explicit" if meta.get("disable-model-invocation") else "auto",
                    "scope": scope,
                    "root": str(root),
                    "description": clean_desc(meta.get("description")),
                }
            )
    return skills


def index_names(roots: list[tuple[str, Path]]) -> set[str]:
    """从各 user 根下的 INDEX.md 表格第一列抽出已登记的技能名。"""
    names: set[str] = set()
    for _scope, root in roots:
        candidate = root / "INDEX.md"
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\|\s*~{0,2}([A-Za-z0-9_.\-]+)~{0,2}\s*\|", line)
            if m and m.group(1) not in {"技能", "---"}:
                names.add(m.group(1))
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描本机全部已安装技能")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--grep", metavar="PAT", help="按名称+描述过滤（忽略大小写）")
    ap.add_argument("--check-index", action="store_true", help="报出未登记进 INDEX.md 的技能")
    ap.add_argument("--roots", action="store_true", help="只列扫描根与数量")
    ap.add_argument("--desc-max", type=int, default=DESC_MAX, help=f"描述截断长度（默认 {DESC_MAX}）")
    args = ap.parse_args()

    agent_dir = Path(os.environ.get("PI_AGENT_DIR") or os.path.expanduser("~/.pi/agent"))

    roots: list[tuple[str, Path]] = []
    seen_roots: set[Path] = set()

    def add_root(scope: str, path: Path) -> None:
        real = path.resolve()
        if real in seen_roots:  # cwd 就在家目录时 ~/.agents/skills 与 ./.agents/skills 会撞车
            return
        seen_roots.add(real)
        roots.append((scope, path))

    for scope, template in ROOTS:
        path = expand(template, agent_dir)
        if path:
            add_root(scope, path)
    for path in package_roots(agent_dir):
        add_root("package", path)

    if args.roots:
        for scope, path in roots:
            print(f"{scope:8} {len(skill_files(path)):3}  {path}")
        return 0

    skills = scan(agent_dir, roots)

    if args.grep:
        pat = re.compile(re.escape(args.grep), re.IGNORECASE)
        skills = [s for s in skills if pat.search(s["name"]) or pat.search(s["description"])]

    # 同名冲突：pi 加载时先到先得，这里只提示
    seen: dict[str, int] = {}
    for s in skills:
        seen[s["name"]] = seen.get(s["name"], 0) + 1

    if args.check_index:
        # 只校对用户级技能：包内与项目级本来就不登记在 INDEX.md
        registered = index_names(roots)
        user_skills = [s for s in skills if s["scope"] == "user"]
        missing = [s["name"] for s in user_skills if s["name"] not in registered and s["dir"] not in registered]
        if not args.json:
            if missing:
                print(f"未登记进 INDEX.md 的用户级技能（{len(missing)} 个）：{', '.join(missing)}\n")
            else:
                print("INDEX.md 已覆盖全部用户级技能。\n")

    if args.json:
        print(json.dumps({"count": len(skills), "skills": skills}, ensure_ascii=False, indent=1))
        return 0

    print(f"# 本机已安装技能 {len(skills)} 个（扫描根 {len(roots)} 处）\n")
    by_root: dict[tuple[str, str], list[dict]] = {}
    for s in skills:
        by_root.setdefault((s["scope"], s["root"]), []).append(s)

    for (scope, root), items in by_root.items():
        print(f"## {scope} · {root} ({len(items)})")
        for s in items:
            flag = "显式" if s["mode"] == "explicit" else "自动"
            dup = "  ← 重名" if seen[s["name"]] > 1 else ""
            print(f"- {s['name']} [{flag}]{dup}")
            if s["description"]:
                print(f"    {s['description']}")
        print()

    print("图例：[自动] 模型可自行调用；[显式] 只有输入 /skill:名字 才触发。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # 输出被 head / less 截断是正常用法
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
