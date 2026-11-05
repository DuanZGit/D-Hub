#!/usr/bin/env bash
# 统一来源登记脚本
# 用法: ./source-register.sh <db_path> <platform> <title> <url> [method] [precision] [notes]
#
# 例子:
#   ./source-register.sh db/nutrition-v2.db "USDA FoodData Central" "Chicken thigh page" "https://fdc.nal.usda.gov/..." manual page-level

DB_PATH=${1:-""}
PLATFORM=${2:-""}
TITLE=${3:-""}
URL=${4:-""}
METHOD=${5:-"manual/curated"}
PRECISION=${6:-"site-level"}
NOTES=${7:-""}

if [ -z "$DB_PATH" ] || [ -z "$PLATFORM" ] || [ -z "$TITLE" ] || [ -z "$URL" ]; then
  echo "用法: $0 <db_path> <platform> <title> <url> [method] [precision] [notes]"
  exit 1
fi

if [ ! -f "$DB_PATH" ]; then
  echo "数据库不存在: $DB_PATH"
  exit 1
fi

sqlite3 "$DB_PATH" <<SQL
BEGIN;
CREATE TABLE IF NOT EXISTS source_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  title TEXT,
  url TEXT NOT NULL,
  method TEXT,
  notes TEXT,
  precision_level TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO source_registry(platform, title, url, method, notes, precision_level)
VALUES (
  '$(printf "%s" "$PLATFORM" | sed "s/'/''/g")',
  '$(printf "%s" "$TITLE" | sed "s/'/''/g")',
  '$(printf "%s" "$URL" | sed "s/'/''/g")',
  '$(printf "%s" "$METHOD" | sed "s/'/''/g")',
  '$(printf "%s" "$NOTES" | sed "s/'/''/g")',
  '$(printf "%s" "$PRECISION" | sed "s/'/''/g")'
);
COMMIT;
SQL

echo "已登记来源: $PLATFORM | $TITLE | $URL | $PRECISION"
