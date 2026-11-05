#!/usr/bin/env bash
# ask-me 自检。
#
# 除 T1 外全部跑在 mktemp 造的假技能库上（ASKME_SKILL_ROOTS 改道），
# 不碰真实技能，跑完删掉本次产生的备份。
#
#   bash scripts/selftest.sh

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLY="$HERE/apply_modes.py"
SCAN="$HERE/scan_skills.py"
TMP="$(mktemp -d)"
BACKUPS="$HOME/.agents/backups"
START_TS="$(date +%s)"

pass=0; fail=0
ok(){ printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass + 1)); }
no(){ printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail + 1)); }
eq(){ if [ "$2" = "$3" ]; then ok "$1（$2）"; else no "$1：期望「$3」，实际「$2」"; fi; }

cleanup(){
  rm -rf "$TMP"
  # 只删本次自检产生的备份（按 mtime 晚于启动时刻判定，不会误伤历史备份）
  find "$BACKUPS" -maxdepth 1 -name 'skill-modes-*.tar.gz' -newermt "@$START_TS" -delete 2>/dev/null
}
trap cleanup EXIT

# ── 造隔离技能库 ────────────────────────────────────────────────────
LIB="$TMP/lib"
mk(){ # mk <名> <几天前> <额外 frontmatter 行>
  local d="$LIB/$1"; mkdir -p "$d"
  { printf -- '---\nname: %s\ndescription: 自检用假技能 %s\n' "$1" "$1"
    if [ -n "${3:-}" ]; then printf '%s\n' "$3"; fi
    printf -- '---\n\n# %s\n' "$1"; } > "$d/SKILL.md"
  if [ "$2" != "0" ]; then touch -d "$2 days ago" "$d/SKILL.md"; fi
}

echo "T1 扫描根覆盖"
# 不再硬编码根数量：不同机器装的 pi 包不同（user 根 1~2 个、package 根 3~5 个不等），
# 硬编码 6 会让自检永远假失败。只要求「≥2 个根且含 user 类」。
_root_out="$(python3 "$SCAN" --roots 2>&1)"
_root_n="$(printf '%s\n' "$_root_out" | grep -c .)"
if [ "${_root_n:-0}" -ge 2 ] && printf '%s\n' "$_root_out" | grep -q '^user'; then
  ok "扫描根覆盖 ${_root_n} 个（含 user 类）"
else
  no "扫描根异常：${_root_n} 个 / 输出：$(printf '%s' "$_root_out" | head -2 | tr '\n' ' ')"
fi

echo "T2 动作分类（升 / 降 / 搁置 / 跳过）"
mk ponytail    60 "disable-model-invocation: true"   # 在保留名单、当前显式 → 升为自动
mk old-drop    60 ""                                 # 不在名单、老技能     → 降为显式
mk fresh-new   0  ""                                 # 不在名单（不管新旧）  → 降为显式
mk already     60 "disable-model-invocation: true"   # 不在名单、老、已显式 → 无需动
mkdir -p "$LIB/broken"; printf 'no frontmatter here\n' > "$LIB/broken/SKILL.md"
mkdir -p "$LIB/noname"; printf -- '---\ndescription: 没有 name\n---\n正文\n' > "$LIB/noname/SKILL.md"

dry="$(ASKME_SKILL_ROOTS="$LIB" python3 "$APPLY" 2>&1)"
grep -qE "升为自动 +ponytail" <<<"$dry"  && ok "ponytail → 升为自动" || no "ponytail 判错了"
grep -qE "降为显式 +old-drop" <<<"$dry"  && ok "old-drop → 降为显式" || no "old-drop 判错了"
grep -qE "降为显式 +fresh-new" <<<"$dry" && ok "fresh-new → 降为显式（不看新旧）" || no "fresh-new 判错了"
grep -q  "跳过 2 个"          <<<"$dry"  && ok "坏 frontmatter / 缺 name → 跳过" || no "跳过计数不对"

echo "T3 --check 退出码"
ASKME_SKILL_ROOTS="$LIB" python3 "$APPLY" --check >/dev/null 2>&1; rc=$?
eq "未对齐时退出码" "$rc" "1"

echo "T4 --apply -v 真的写盘（回归：曾打印完就 return，静默不写）"
applied="$(ASKME_SKILL_ROOTS="$LIB" python3 "$APPLY" --apply -v 2>&1)"
grep -q "保留自动的明细" <<<"$applied" && ok "verbose 明细有打印" || no "verbose 明细没打印"
grep -q "已改 3 个，自验通过" <<<"$applied" && ok "写盘 + 自验通过" || no "写盘/自验异常：$(printf '%s' "$applied" | tail -2)"

echo "T5 frontmatter 改对了吗"
grep -q "disable-model-invocation" "$LIB/ponytail/SKILL.md" && no "ponytail 的 flag 没删掉" || ok "ponytail flag 已删（升为自动）"
grep -q "disable-model-invocation: true" "$LIB/old-drop/SKILL.md" && ok "old-drop flag 已加（降为显式）" || no "old-drop flag 没加上"
grep -q "disable-model-invocation: true" "$LIB/fresh-new/SKILL.md" && ok "fresh-new flag 已加（不在名单就降级）" || no "fresh-new 没被降级"
grep -q "^name: ponytail" "$LIB/ponytail/SKILL.md" && ok "原有 frontmatter 未被破坏" || no "frontmatter 被破坏"

echo "T6 幂等 + 对齐后退出码"
ASKME_SKILL_ROOTS="$LIB" python3 "$APPLY" --check >/dev/null 2>&1; rc=$?
eq "对齐后退出码" "$rc" "0"
second="$(ASKME_SKILL_ROOTS="$LIB" python3 "$APPLY" --apply 2>&1)"
grep -q "状态已对齐" <<<"$second" && ok "二次 --apply 无改动" || no "二次 --apply 又改了东西"

echo "T7 回滚安全网"
python3 - "$TMP" "$HERE" <<'PY' >/dev/null 2>&1
import io, sys, tarfile, pathlib
tmp, here = sys.argv[1], sys.argv[2]
sys.path.insert(0, here)
import apply_modes as am
t = pathlib.Path(tmp) / "evil.tar.gz"
with tarfile.open(t, "w:gz") as tar:
    data = b"should never land"
    info = tarfile.TarInfo("tmp/askme-evil-probe.txt"); info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
am.rollback(t)
PY
[ -f /tmp/askme-evil-probe.txt ] && no "越界成员被写出（安全网失效）" || ok "越界成员已拒绝"

echo "T8 无 pyyaml 时的退化解析"
if python3 -S -c "import yaml" >/dev/null 2>&1; then
  echo "  \033[33mSKIP\033[0m 本机 python3 -S 下仍能 import yaml，退化路径无法这样触发"
else
  deg="$(ASKME_SKILL_ROOTS="$LIB" python3 -S "$APPLY" 2>&1)"
  grep -q "用户级技能" <<<"$deg" && ok "退化解析仍能出报告" || no "退化解析崩了：$(printf '%s' "$deg" | tail -2)"
fi

echo "T9 INDEX.md 一致性"
idx="$(python3 "$SCAN" --check-index 2>&1 | head -1)"
[ "$idx" = "INDEX.md 已覆盖全部用户级技能。" ] && ok "无未登记项" || no "$idx"

echo
printf '通过 %d / 失败 %d\n' "$pass" "$fail"
[ "$fail" = "0" ]
