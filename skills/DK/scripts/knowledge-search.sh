#!/usr/bin/env bash
# 百科知识查询 — 无需任何配置，纯 curl 实现
# 用法: ./knowledge-search.sh <关键词> [平台]
# 平台: baike | wiki | general

KEYWORD=${1:-"美拉德反应"}
PLATFORM=${2:-"general"}

echo "============================================"
echo "  百科知识查询: $KEYWORD"
echo "============================================"
echo ""

# 纯 curl 获取百度百科摘要
fetch_baike() {
  echo "【百度百科】"
  local url="https://baike.baidu.com/item/$KEYWORD"
  local html=$(curl -sL --connect-timeout 8 \
    -H "User-Agent: Mozilla/5.0" "$url" 2>/dev/null)
  
  if [ -n "$html" ] && [ ${#html} -gt 100 ]; then
    # 提取摘要
    local summary=$(echo "$html" | grep -oP '<dd class="lemma-summary">[^<]*</dd>' | head -1 | sed 's/<[^>]*>//g')
    if [ -n "$summary" ]; then
      echo "  $summary"
    else
      # 提取第一段正文
      local text=$(echo "$html" | grep -oP '<div class="content"><h2[^>]*>[^<]*</h2>[^<]*</div>' | head -1 | sed 's/<[^>]*>//g' | head -c 300)
      if [ -n "$text" ]; then
        echo "  $text"
      else
        echo "  页面存在但内容需要 JS 渲染"
      fi
    fi
    echo "  链接: $url"
  else
    echo "  （访问失败）"
    echo "  链接: $url"
  fi
  echo ""
}

# 维基百科
fetch_wiki() {
  echo "【维基百科】"
  local url="https://zh.wikipedia.org/wiki/$KEYWORD"
  echo "  链接: $url"
  echo "  （维基百科有中文页面，直接访问阅读）"
  echo ""
}

# 通用网页读取 — 用 curl 直接请求
fetch_general() {
  echo "【通用网页查询】"
  
  # 尝试访问 Jina Reader（免费，无需key）
  echo "  Jina Reader: https://r.jina.ai/"
  echo "  用法: curl -s https://r.jina.ai/网页URL"
  echo ""
  
  # 示例：读取一个公开的知识文章
  echo "  示例：读取维基百科摘要"
  local wiki_url="https://zh.wikipedia.org/api/rest_v1/page/html/$KEYWORD"
  local html=$(curl -sL --connect-timeout 8 "$wiki_url" 2>/dev/null)
  if [ -n "$html" ] && [ ${#html} -gt 50 ]; then
    local text=$(echo "$html" | sed 's/<[^>]*>//g' | sed 's/^[[:space:]]*//' | head -c 300)
    if [ ${#text} -gt 20 ]; then
      echo "  $text"
    fi
  else
    echo "  （维基百科 API 可能需要英文关键词）"
  fi
  echo ""
}

case $PLATFORM in
  "baike"|"百科")
    fetch_baike
    ;;
  "wiki"|"wikipedia")
    fetch_wiki
    ;;
  *)
    fetch_baike
    fetch_wiki
    fetch_general
    ;;
esac

echo "============================================"
echo "  查询完成"
echo "============================================"
