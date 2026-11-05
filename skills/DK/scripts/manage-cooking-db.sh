#!/usr/bin/env bash
# 烹饪知识库管理脚本
# 用法: ./manage-cooking-db.sh <命令> [参数]

DB_PATH="$(dirname "$0")/../db/cooking-knowledge.db"
COMMAND=${1:-"help"}

# 初始化数据库
init_db() {
  echo "初始化数据库..."
  sqlite3 "$DB_PATH" < "$(dirname "$0")/../db/schema.sql"
  sqlite3 "$DB_PATH" < "$(dirname "$0")/../db/init-data.sql"
  echo "数据库初始化完成！"
}

# 显示数据库状态
show_status() {
  echo "========================================="
  echo "烹饪知识库状态"
  echo "========================================="
  echo ""
  echo "数据库路径: $DB_PATH"
  echo "数据库大小: $(du -h "$DB_PATH" | cut -f1)"
  echo ""
  echo "数据统计:"
  for table in cooking_methods cookware ingredient_prep seasoning_science baking_knowledge healthy_cooking cooking_faq; do
    count=$(sqlite3 "$DB_PATH" "SELECT count(*) FROM $table;")
    echo "  $table: $count 条"
  done
  echo ""
  echo "总记录数: $(sqlite3 "$DB_PATH" "SELECT (SELECT count(*) FROM cooking_methods) + (SELECT count(*) FROM cookware) + (SELECT count(*) FROM ingredient_prep) + (SELECT count(*) FROM seasoning_science) + (SELECT count(*) FROM baking_knowledge) + (SELECT count(*) FROM healthy_cooking) + (SELECT count(*) FROM cooking_faq);")"
}

# 备份数据库
backup_db() {
  BACKUP_FILE="$(dirname "$DB_PATH")/cooking-knowledge-$(date +%Y%m%d%H%M%S).db"
  cp "$DB_PATH" "$BACKUP_FILE"
  echo "备份完成: $BACKUP_FILE"
}

# 恢复数据库
restore_db() {
  BACKUP_FILE=$2
  if [ -z "$BACKUP_FILE" ]; then
    echo "请指定备份文件路径"
    echo "用法: ./manage-cooking-db.sh restore <备份文件>"
    exit 1
  fi
  if [ ! -f "$BACKUP_FILE" ]; then
    echo "备份文件不存在: $BACKUP_FILE"
    exit 1
  fi
  cp "$BACKUP_FILE" "$DB_PATH"
  echo "恢复完成: $BACKUP_FILE"
}

# 添加烹饪方式
add_method() {
  echo "添加烹饪方式"
  echo "请输入以下信息（按Ctrl+D结束）:"
  echo "名称: "
  read name
  echo "英文名: "
  read name_en
  echo "科学原理: "
  read principle
  echo "温度范围: "
  read temperature
  echo "优点: "
  read pros
  echo "缺点: "
  read cons
  echo "适用食材: "
  read suitable_for
  echo "技巧: "
  read tips
  echo "健康提示: "
  read health_note
  echo "来源平台: "
  read source_platform
  echo "来源标题: "
  read source_title
  echo "来源网址: "
  read source_url
  echo "采集方式: "
  read source_method
  
  sqlite3 "$DB_PATH" "INSERT INTO cooking_methods (name, name_en, principle, temperature, pros, cons, suitable_for, tips, health_note, source_platform, source_title, source_url, source_method, source_precision) VALUES ('$name', '$name_en', '$principle', '$temperature', '$pros', '$cons', '$suitable_for', '$tips', '$health_note', '$source_platform', '$source_title', '$source_url', '$source_method', 'page-level');"
  echo "添加成功！"
}

# 添加FAQ
add_faq() {
  echo "添加常见问题"
  echo "请输入以下信息（按Ctrl+D结束）:"
  echo "分类: "
  read category
  echo "问题: "
  read question
  echo "答案: "
  read answer
  echo "来源: "
  read source
  echo "来源平台: "
  read source_platform
  echo "来源标题: "
  read source_title
  echo "来源网址: "
  read source_url
  echo "采集方式: "
  read source_method
  
  sqlite3 "$DB_PATH" "INSERT INTO cooking_faq (category, question, answer, source, source_platform, source_title, source_url, source_method, source_precision) VALUES ('$category', '$question', '$answer', '$source', '$source_platform', '$source_title', '$source_url', '$source_method', 'page-level');"
  echo "添加成功！"
}

# 导出数据为SQL
export_sql() {
  EXPORT_FILE="$(dirname "$DB_PATH")/cooking-knowledge-export-$(date +%Y%m%d%H%M%S).sql"
  sqlite3 "$DB_PATH" ".dump" > "$EXPORT_FILE"
  echo "导出完成: $EXPORT_FILE"
}

# 显示帮助
show_help() {
  echo "========================================="
  echo "烹饪知识库管理"
  echo "========================================="
  echo ""
  echo "用法: ./manage-cooking-db.sh <命令> [参数]"
  echo ""
  echo "命令:"
  echo "  init       - 初始化数据库"
  echo "  status     - 显示数据库状态"
  echo "  backup     - 备份数据库"
  echo "  restore    - 恢复数据库"
  echo "  add-method - 添加烹饪方式"
  echo "  add-faq    - 添加常见问题"
  echo "  export     - 导出数据为SQL"
  echo "  register-source - 登记来源元数据"
  echo ""
  echo "示例:"
  echo "  ./manage-cooking-db.sh init"
  echo "  ./manage-cooking-db.sh status"
  echo "  ./manage-cooking-db.sh backup"
  echo "  ./manage-cooking-db.sh restore /path/to/backup.db"
  echo "  ./manage-cooking-db.sh add-method"
  echo "  ./manage-cooking-db.sh add-faq"
  echo "  ./manage-cooking-db.sh export"
  echo "  ./manage-cooking-db.sh register-source"
  echo "========================================="
}

# 根据参数执行命令
case $COMMAND in
  "init")
    init_db
    ;;
  "status")
    show_status
    ;;
  "backup")
    backup_db
    ;;
  "restore")
    restore_db "$@"
    ;;
  "add-method")
    add_method
    ;;
  "add-faq")
    add_faq
    ;;
  "export")
    export_sql
    ;;
  "register-source")
    echo "请使用 scripts/source-register.sh 统一登记来源"
    ;;
  *)
    show_help
    ;;
esac
