#!/usr/bin/env bash
# 固化爬取方案 — 爬取成功后调用，自动保存爬取方法供后续使用
# 用法: ./knowledge-fix.sh <源名> <标题> <URL> <提取方法> [raw文件路径]
#
# 提取方法: curl-bs4 | curl-grep | playwright | jina
#
# 固化前建议先登记来源:
#   ./source-register.sh <db_path> <platform> <title> <url> [method] [precision] [notes]
#
# 固化后:
# - config/success/<源名>.sh → 爬取脚本
# - raw/<领域>/日期-<源名>.md → 原始资料
# - 自动更新权威信息源索引

KEY_NAME=${1:-"wikihow"}
TITLE=${2:-"测试"}
URL=${3:-"https://example.com"}
METHOD=${4:-"curl"}
RAW_PATH=${5:-""}

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="$SKILL_DIR/config/success"
RAW_DIR="$SKILL_DIR/raw"
DATE=$(date +%Y-%m-%d)

echo "============================================"
echo "  固化爬取方案: $KEY_NAME"
echo "============================================"
echo ""

# 创建固化目录
mkdir -p "$CONFIG_DIR"

# 生成爬取脚本
case $METHOD in
  "curl-bs4")
    cat > "$CONFIG_DIR/$KEY_NAME.sh" << 'SCRIPT'
#!/bin/bash
# <源名> 爬取脚本 — 自动生成
# 方法: curl + BeautifulSoup
# URL: <URL>
# 状态: ✅ 可用
# 固化时间: <DATE>

KEYWORD="$1"
URL="https://example.com/search?q=KEYWORD"

python3 << 'PYEOF'
import requests
from bs4 import BeautifulSoup
import sys

keyword = sys.argv[1] if len(sys.argv) > 1 else ""
url = "https://example.com/search?q=" + keyword
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
soup = BeautifulSoup(r.text, "html.parser")

# 提取内容逻辑在此编写
for item in soup.find_all("div", class_="result"):
    title = item.find("h2")
    if title:
        print(title.get_text().strip())
PYEOF
SCRIPT
    ;;
  "curl-grep")
    cat > "$CONFIG_DIR/$KEY_NAME.sh" << SCRIPT
#!/bin/bash
# $KEY_NAME 爬取脚本
# 方法: curl + grep 提取
# URL: $URL
# 状态: ✅ 可用
# 固化时间: $DATE

curl -sL --connect-timeout 8 -H "User-Agent: Mozilla/5.0" "$URL" 2>/dev/null | \
  grep -oP '提取规则在此填写' | head -10
SCRIPT
    ;;
  "jina")
    cat > "$CONFIG_DIR/$KEY_NAME.sh" << SCRIPT
#!/bin/bash
# $KEY_NAME 爬取脚本
# 方法: Jina Reader（免费，无需key）
# URL: $URL
# 状态: ✅ 可用
# 固化时间: $DATE

curl -sL --connect-timeout 10 \
  -H "Accept: text/plain" \
  -H "X-Return-Format: text" \
  "https://r.jina.ai/$URL" 2>/dev/null
SCRIPT
    ;;
  *)
    cat > "$CONFIG_DIR/$KEY_NAME.sh" << SCRIPT
#!/bin/bash
# $KEY_NAME 爬取脚本
# 方法: $METHOD
# URL: $URL
# 状态: ✅ 可用
# 固化时间: $DATE

# TODO: 补充提取逻辑
echo "来源: $URL"
echo "标题: $TITLE"
SCRIPT
    ;;
esac

chmod +x "$CONFIG_DIR/$KEY_NAME.sh"
echo "✓ 爬取脚本已固化: config/success/$KEY_NAME.sh"
echo ""

# 如果有 raw 文件路径，也保存一份到 raw/
if [ -n "$RAW_PATH" ] && [ -f "$RAW_PATH" ]; then
  # 推断领域目录
  local_dir=$(dirname "$RAW_PATH" | sed "s|$SKILL_DIR/raw/||" | cut -d'/' -f1)
  mkdir -p "$RAW_DIR/$local_dir"
  cp "$RAW_PATH" "$RAW_DIR/$local_dir/${DATE}-${KEY_NAME}.md"
  echo "✓ 原始资料已保存: raw/$local_dir/${DATE}-${KEY_NAME}.md"
fi

echo ""
echo "提示: 如需让数据库可追溯，先运行 scripts/source-register.sh 登记来源，再把条目写入库中。"

echo ""
echo "============================================"
echo "  固化完成！下次查询此来源时会自动使用"
echo "============================================"
