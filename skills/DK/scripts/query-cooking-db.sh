#!/usr/bin/env bash
# 烹饪知识库查询脚本
# 用法: ./query-cooking-db.sh <查询类型> [关键词]

DB_PATH="$(dirname "$0")/../db/cooking-knowledge.db"
QUERY_TYPE=${1:-"help"}
KEYWORD=${2:-""}

# 检查数据库是否存在，不存在则初始化
init_db() {
  if [ ! -f "$DB_PATH" ]; then
    echo "初始化数据库..."
    sqlite3 "$DB_PATH" < "$(dirname "$0")/../db/schema.sql"
    sqlite3 "$DB_PATH" < "$(dirname "$0")/../db/init-data.sql"
    echo "数据库初始化完成！"
  fi
}

# 查询烹饪方式
query_methods() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有烹饪方式】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, temperature, pros, health_note, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM cooking_methods;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, principle, temperature, pros, cons, suitable_for, tips, health_note, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM cooking_methods WHERE name LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 查询厨具
query_cookware() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有厨具】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, material, pros, cons, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM cookware;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, material, pros, cons, suitable_for, maintenance, safety_note, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM cookware WHERE name LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 查询食材处理
query_ingredient() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有食材分类】"
    sqlite3 -header -column "$DB_PATH" "SELECT DISTINCT category FROM ingredient_prep;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, cleaning, cutting, marinating, blanching, storage, tips, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM ingredient_prep WHERE name LIKE '%$KEYWORD%' OR category LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 查询调味料
query_seasoning() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有调味料】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, flavor, function_text, timing, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM seasoning_science;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT name, flavor, function_text, timing, substitutes, health_note, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM seasoning_science WHERE name LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 查询烘焙知识
query_baking() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有烘焙知识】"
    sqlite3 -header -column "$DB_PATH" "SELECT category, topic, content, temperature, duration, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM baking_knowledge;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT category, topic, content, temperature, duration, tips, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM baking_knowledge WHERE topic LIKE '%$KEYWORD%' OR content LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 查询健康烹饪
query_healthy() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有健康烹饪要点】"
    sqlite3 -header -column "$DB_PATH" "SELECT category, topic, recommendation, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM healthy_cooking;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT category, topic, principle, recommendation, tips, special_population, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM healthy_cooking WHERE topic LIKE '%$KEYWORD%' OR category LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 查询FAQ
query_faq() {
  if [ -z "$KEYWORD" ]; then
    echo "【所有常见问题】"
    sqlite3 -header -column "$DB_PATH" "SELECT category, question, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM cooking_faq;"
  else
    echo "【查询: $KEYWORD】"
    sqlite3 -header -column "$DB_PATH" "SELECT question, answer, source, COALESCE(source_platform,'') as 来源平台, COALESCE(source_url,'') as 来源网址 FROM cooking_faq WHERE question LIKE '%$KEYWORD%' OR answer LIKE '%$KEYWORD%';" 2>/dev/null
  fi
}

# 全文搜索
search_all() {
  echo "【全文搜索: $KEYWORD】"
  echo ""
  
  echo "▶ 烹饪方式:"
  sqlite3 -header -column "$DB_PATH" "SELECT name, principle FROM cooking_methods WHERE name LIKE '%$KEYWORD%' OR principle LIKE '%$KEYWORD%' OR suitable_for LIKE '%$KEYWORD%';" 2>/dev/null
  
  echo ""
  echo "▶ 厨具:"
  sqlite3 -header -column "$DB_PATH" "SELECT name, suitable_for FROM cookware WHERE name LIKE '%$KEYWORD%' OR suitable_for LIKE '%$KEYWORD%';" 2>/dev/null
  
  echo ""
  echo "▶ 食材处理:"
  sqlite3 -header -column "$DB_PATH" "SELECT name, tips FROM ingredient_prep WHERE name LIKE '%$KEYWORD%' OR tips LIKE '%$KEYWORD%';" 2>/dev/null
  
  echo ""
  echo "▶ 调味料:"
  sqlite3 -header -column "$DB_PATH" "SELECT name, function_text FROM seasoning_science WHERE name LIKE '%$KEYWORD%' OR function_text LIKE '%$KEYWORD%';" 2>/dev/null
  
  echo ""
  echo "▶ 常见问题:"
  sqlite3 -header -column "$DB_PATH" "SELECT question, answer FROM cooking_faq WHERE question LIKE '%$KEYWORD%' OR answer LIKE '%$KEYWORD%';" 2>/dev/null
}

# 显示帮助
show_help() {
  echo "========================================="
  echo "烹饪知识库查询"
  echo "========================================="
  echo ""
  echo "用法: ./query-cooking-db.sh <类型> [关键词]"
  echo ""
  echo "查询类型:"
  echo "  methods    - 烹饪方式（蒸、煮、炒、烤等）"
  echo "  cookware   - 厨具（铁锅、烤箱、高压锅等）"
  echo "  ingredient - 食材处理（肉类、蔬菜、鱼类等）"
  echo "  seasoning  - 调味料（盐、酱油、醋等）"
  echo "  baking     - 烘焙知识（温度、时间、技巧）"
  echo "  healthy    - 健康烹饪（控油、控盐、食品安全）"
  echo "  faq        - 常见问题"
  echo "  search     - 全文搜索"
  echo ""
  echo "示例:"
  echo "  ./query-cooking-db.sh methods        # 列出所有烹饪方式"
  echo "  ./query-cooking-db.sh methods 蒸      # 查询蒸的详细信息"
  echo "  ./query-cooking-db.sh cookware 烤箱   # 查询烤箱使用"
  echo "  ./query-cooking-db.sh ingredient 猪肉 # 查询猪肉处理"
  echo "  ./query-cooking-db.sh search 高血压   # 全文搜索"
  echo ""
  echo "数据来源:"
  echo "  - 中国营养学会《中国居民膳食指南》"
  echo "  - 中国烹饪协会烹饪标准"
  echo "  - 食品安全国家标准"
  echo "  - 世界卫生组织(WHO)"
  echo "  - 国家卫健委"
  echo "========================================="
}

# 初始化数据库
init_db

# 根据参数执行查询
case $QUERY_TYPE in
  "methods"|"方式"|"烹饪方式")
    query_methods
    ;;
  "cookware"|"厨具"|"锅具")
    query_cookware
    ;;
  "ingredient"|"食材"|"处理")
    query_ingredient
    ;;
  "seasoning"|"调味"|"调料")
    query_seasoning
    ;;
  "baking"|"烘焙"|"烤箱")
    query_baking
    ;;
  "healthy"|"健康"|"安全")
    query_healthy
    ;;
  "faq"|"问题")
    query_faq
    ;;
  "search"|"搜索")
    search_all
    ;;
  *)
    show_help
    ;;
esac
