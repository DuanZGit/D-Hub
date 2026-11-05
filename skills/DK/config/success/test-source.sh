#!/bin/bash
# test-source 通用测试爬取脚本(模板)
# 方法: Jina Reader (r.jina.ai) — 零 key,通用 fallback
# URL: 任意公开网页
# 状态: ✅ 可用
# 固化时间: 2026-06-10 (改写 2026-06-14)
#
# 用法:
#   bash test-source.sh <URL>
#
# 这是个"能跑就能证明 jina 通了"的最简测试,实际固化时建议改用:
#   bash scripts/knowledge-fix.sh <源名> <标题> <URL> jina

if [ -z "$1" ]; then
  echo "用法: bash $0 <URL>"
  echo "示例: bash $0 https://en.wikipedia.org/wiki/Maillard_reaction"
  exit 1
fi

TARGET_URL="$1"
echo "URL: $TARGET_URL"
echo "---"
echo ""

curl -sL --connect-timeout 15 --max-time 60 \
  -H "Accept: text/markdown" \
  -H "X-Return-Format: markdown" \
  -A "Mozilla/5.0 (compatible; DK-Skill/1.0)" \
  "https://r.jina.ai/$TARGET_URL"
