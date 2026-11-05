#!/usr/bin/env bash
# Karpathy Wiki 查询脚本
# 用法: ./wiki-query.sh <操作> [参数]

WIKI_DIR="$(dirname "$0")/../wiki"
RAW_DIR="$(dirname "$0")/../raw"
OPERATION=${1:-"help"}
QUERY=${2:-""}
CATEGORY=${3:-""}

# 查询 Wiki
query_wiki() {
  echo "============================================================"
  echo "【Wiki 查询】"
  echo "============================================================"
  echo ""
  echo "查询: $QUERY"
  if [ -n "$CATEGORY" ]; then
    echo "分类: $CATEGORY"
  fi
  echo ""
  
  # 搜索 Wiki 页面
  echo "【匹配的 Wiki 页面】"
  echo "------------------------------------------------------------"
  
  local found=0
  
  # 定义分类和图标
  declare -A categories=(
    ["recipes"]="📄 食谱"
    ["ingredients"]="🥬 食材"
    ["chemistry"]="🧪 化学反应"
    ["nutrition"]="💊 营养"
    ["techniques"]="🔪 技巧"
    ["appliances"]="🧼 厨具家电"
    ["concepts"]="📚 概念"
  )
  
  # 根据分类搜索
  if [ -n "$CATEGORY" ]; then
    # 搜索指定分类
    if [ -d "$WIKI_DIR/$CATEGORY" ]; then
      for file in "$WIKI_DIR/$CATEGORY/"*.md; do
        if [ -f "$file" ]; then
          local name=$(basename "$file" .md)
          if echo "$name" | grep -qi "$QUERY"; then
            echo "${categories[$CATEGORY]}: $name"
            echo "   路径: $file"
            # 提取摘要（跳过标题和空行）
            head -10 "$file" | grep -v "^#" | grep -v "^$" | head -1
            echo ""
            found=1
          fi
        fi
      done
    fi
  else
    # 搜索所有分类
    for dir in "${!categories[@]}"; do
      if [ -d "$WIKI_DIR/$dir" ]; then
        for file in "$WIKI_DIR/$dir/"*.md; do
          if [ -f "$file" ]; then
            local name=$(basename "$file" .md)
            if echo "$name" | grep -qi "$QUERY"; then
              echo "${categories[$dir]}: $name"
              echo "   路径: $file"
              head -10 "$file" | grep -v "^#" | grep -v "^$" | head -1
              echo ""
              found=1
            fi
          fi
        done
      fi
    done
  fi
  
  # 如果文件名搜索没有结果，搜索文件内容
  if [ $found -eq 0 ]; then
    echo "【文件内容搜索】"
    echo "------------------------------------------------------------"
    
    for dir in "${!categories[@]}"; do
      if [ -d "$WIKI_DIR/$dir" ]; then
        for file in "$WIKI_DIR/$dir/"*.md; do
          if [ -f "$file" ]; then
            local name=$(basename "$file" .md)
            if grep -qi "$QUERY" "$file"; then
              echo "${categories[$dir]}: $name"
              echo "   路径: $file"
              echo "   匹配内容:"
              grep -i -n "$QUERY" "$file" | head -3
              echo ""
              found=1
            fi
          fi
        done
      fi
    done
  fi
  
  # 如果 wiki 无结果，搜索 raw/recipes 原始资料
  if [ $found -eq 0 ] && [ -d "$RAW_DIR/recipes" ]; then
    echo "【raw 食谱搜索】"
    echo "------------------------------------------------------------"
    for file in "$RAW_DIR/recipes/"*.md; do
      if [ -f "$file" ]; then
        local name=$(basename "$file" .md)
        # 去掉日期前缀和"的做法"后缀用于匹配
        local core=$(echo "$name" | sed 's/^[0-9-]*//; s/\.md$//; s/的做法$//')
        if echo "$core" | grep -qi "$QUERY"; then
          echo "📄 食谱(raw): $name"
          echo "   路径: $file"
          local desc=$(head -1 "$file" | sed 's/^# //')
          echo "   $desc"
          echo ""
          found=1
        fi
      fi
    done
    if [ $found -eq 0 ]; then
      echo "（raw 中未找到匹配菜谱）"
    fi
  fi
  
  if [ $found -eq 0 ]; then
    echo "未找到匹配的 Wiki 页面"
    echo ""
    echo "提示："
    echo "  - 尝试使用更简短的关键词"
    echo "  - 检查是否有拼写错误"
    echo "  - 使用 'list' 命令查看所有可用页面"
  fi
}

# 显示 Wiki 页面内容
show_page() {
  local page_path=""
  
  # 搜索所有目录
  for dir in recipes ingredients chemistry nutrition techniques appliances concepts; do
    if [ -d "$WIKI_DIR/$dir" ]; then
      for file in "$WIKI_DIR/$dir/"*.md; do
        if [ -f "$file" ]; then
          local name=$(basename "$file" .md)
          if [ "$name" = "$QUERY" ]; then
            page_path="$file"
            break 2
          fi
        fi
      done
    fi
  done
  
  if [ -n "$page_path" ]; then
    echo "============================================================"
    echo "【Wiki 页面】"
    echo "============================================================"
    echo "文件: $page_path"
    echo "============================================================"
    cat "$page_path"
  else
    echo "未找到页面: $QUERY"
    echo ""
    echo "可用页面："
    list_pages
  fi
}

# 列出所有 Wiki 页面
list_pages() {
  echo "============================================================"
  echo "【Wiki 页面列表】"
  echo "============================================================"
  echo ""
  
  declare -A categories=(
    ["recipes"]="📄 食谱 (recipes/)"
    ["ingredients"]="🥬 食材 (ingredients/)"
    ["chemistry"]="🧪 化学反应 (chemistry/)"
    ["nutrition"]="💊 营养知识 (nutrition/)"
    ["techniques"]="🔪 技巧 (techniques/)"
    ["appliances"]="🧼 厨具家电 (appliances/)"
    ["concepts"]="📚 概念 (concepts/)"
  )
  
  local total=0
  
  for dir in recipes ingredients chemistry nutrition techniques appliances concepts; do
    echo "${categories[$dir]}"
    echo "------------------------------------------------------------"
    local count=0
    if [ -d "$WIKI_DIR/$dir" ]; then
      for file in "$WIKI_DIR/$dir/"*.md; do
        if [ -f "$file" ]; then
          local name=$(basename "$file" .md)
          echo "  - $name"
          count=$((count + 1))
        fi
      done
    fi
    echo "  (共 $count 个页面)"
    echo ""
    total=$((total + count))
  done
  
  echo "============================================================"
  echo "总计: $total 个 Wiki 页面"
  echo "============================================================"
}

# 统计 Wiki 信息
show_stats() {
  echo "============================================================"
  echo "【Wiki 统计】"
  echo "============================================================"
  echo ""
  
  local total=0
  local total_size=0
  
  declare -A categories=(
    ["recipes"]="📄 食谱"
    ["ingredients"]="🥬 食材"
    ["chemistry"]="🧪 化学反应"
    ["nutrition"]="💊 营养知识"
    ["techniques"]="🔪 技巧"
    ["appliances"]="🧼 厨具家电"
    ["concepts"]="📚 概念"
  )
  
  for dir in recipes ingredients chemistry nutrition techniques appliances concepts; do
    local count=$(find "$WIKI_DIR/$dir" -name "*.md" 2>/dev/null | wc -l)
    local size=$(du -sh "$WIKI_DIR/$dir" 2>/dev/null | cut -f1)
    echo "  ${categories[$dir]}: $count 个页面 ($size)"
    total=$((total + count))
  done
  
  echo ""
  echo "  总计: $total 个页面"
  
  echo ""
  echo "【原始资料统计】"
  for dir in recipes techniques nutrition chemistry appliances; do
    if [ -d "$RAW_DIR/$dir" ]; then
      local count=$(find "$RAW_DIR/$dir" -name "*.md" 2>/dev/null | wc -l)
      local size=$(du -sh "$RAW_DIR/$dir" 2>/dev/null | cut -f1)
      echo "  $dir: $count 个文件 ($size)"
    fi
  done
  
  echo ""
  echo "【数据库统计】"
  local db_dir="$(dirname "$0")/../db"
  if [ -d "$db_dir" ]; then
    if command -v sqlite3 &> /dev/null; then
      for db in "$db_dir"/*.db; do
        if [ -f "$db" ]; then
          local name=$(basename "$db" .db)
          local size=$(du -sh "$db" | cut -f1)
          local tables=$(sqlite3 "$db" ".tables" 2>/dev/null | wc -w)
          local records=$(sqlite3 "$db" "SELECT SUM(cnt) FROM (SELECT COUNT(*) as cnt FROM $(sqlite3 "$db" ".tables" | tr ' ' ',' | sed 's/,/ UNION ALL SELECT COUNT(*) FROM /g'));" 2>/dev/null || echo "0")
          echo "  $name: $size ($tables 个表, $records 条记录)"
        fi
      done
    else
      echo "  sqlite3 未安装，无法查询数据库详细信息"
      for db in "$db_dir"/*.db; do
        if [ -f "$db" ]; then
          local name=$(basename "$db" .db)
          local size=$(du -sh "$db" | cut -f1)
          echo "  $name: $size"
        fi
      done
    fi
  fi
}

# 显示帮助
show_help() {
  echo "============================================================"
  echo "Karpathy Wiki 查询脚本"
  echo "============================================================"
  echo ""
  echo "用法: ./wiki-query.sh <操作> [参数] [分类]"
  echo ""
  echo "操作:"
  echo "  query <关键词> [分类]   - 搜索 Wiki 页面"
  echo "  show <页面名>           - 显示页面内容"
  echo "  list                    - 列出所有页面"
  echo "  stats                   - 显示统计信息"
  echo "  help                    - 显示此帮助"
  echo ""
  echo "分类 (可选):"
  echo "  recipes     - 食谱"
  echo "  ingredients - 食材"
  echo "  chemistry   - 化学反应"
  echo "  nutrition   - 营养知识"
  echo "  techniques  - 烹饪技巧"
  echo ""
  echo "示例:"
  echo "  ./wiki-query.sh query 番茄              # 搜索所有分类"
  echo "  ./wiki-query.sh query 番茄 recipes      # 只搜索食谱"
  echo "  ./wiki-query.sh show 红烧肉             # 显示页面"
  echo "  ./wiki-query.sh list                    # 列出所有页面"
  echo "  ./wiki-query.sh stats                   # 显示统计"
  echo ""
  echo "Wiki 结构:"
  echo "  recipes/     - 食谱"
  echo "  ingredients/ - 食材"
  echo "  chemistry/   - 化学反应"
  echo "  nutrition/   - 营养知识"
  echo "  techniques/  - 烹饪技巧"
  echo "============================================================"
}

# 搜索原始资料
search_raw() {
  echo "============================================================"
  echo "【原始资料搜索】"
  echo "============================================================"
  echo ""
  echo "搜索: $QUERY"
  echo ""
  
  local found=0
  
  for dir in recipes techniques nutrition chemistry appliances; do
    if [ -d "$RAW_DIR/$dir" ]; then
      for file in "$RAW_DIR/$dir/"*.md; do
        if [ -f "$file" ]; then
          local name=$(basename "$file")
          if echo "$name" | grep -qi "$QUERY"; then
            echo "📄 $dir: $name"
            echo "   路径: $file"
            echo ""
            found=1
          fi
        fi
      done
    fi
  done
  
  if [ $found -eq 0 ]; then
    echo "未找到匹配的原始资料"
  fi
}

# 根据参数执行操作
case $OPERATION in
  "query"|"搜索")
    if [ -z "$QUERY" ]; then
      echo "请提供查询关键词"
      exit 1
    fi
    query_wiki
    ;;
  "show"|"显示")
    if [ -z "$QUERY" ]; then
      echo "请提供页面名称"
      exit 1
    fi
    show_page
    ;;
  "list"|"列表")
    list_pages
    ;;
  "stats"|"统计")
    show_stats
    ;;
  "raw"|"原始资料")
    if [ -z "$QUERY" ]; then
      echo "请提供搜索关键词"
      exit 1
    fi
    search_raw
    ;;
  "help"|"-h"|"--help")
    show_help
    ;;
  *)
    echo "未知操作: $OPERATION"
    echo "使用 'help' 查看可用操作"
    exit 1
    ;;
esac
