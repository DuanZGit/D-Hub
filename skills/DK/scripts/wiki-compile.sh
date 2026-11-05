#!/usr/bin/env bash
# 用法: bash scripts/wiki-compile.sh <类别> <关键词>
# 功能: 从 raw/ 编译到 wiki/，自动提取元数据，更新索引和日志

CATEGORY=$1
KEYWORD=$2
RAW_FILE=$(ls raw/$CATEGORY/*-$KEYWORD.md 2>/dev/null | head -1)
WIKI_FILE="wiki/$CATEGORY/$KEYWORD.md"

if [ -z "$RAW_FILE" ]; then
  echo "错误：未找到 raw/$CATEGORY/*-$KEYWORD.md"
  exit 1
fi

# 提取元数据
SOURCE=$(grep "^来源:" "$RAW_FILE" | cut -d: -f2- | xargs)
SOURCE_URL=$(grep "^来源网址:" "$RAW_FILE" | cut -d: -f2- | xargs)

# 创建 wiki 目录
mkdir -p "wiki/$CATEGORY"
mkdir -p "wiki/media/$CATEGORY"

# 编译（由 Agent 调用 LLM 完成结构化转换）
echo "待编译: $RAW_FILE → $WIKI_FILE"
echo "来源: $SOURCE"
echo "来源网址: $SOURCE_URL"

# 复制媒体文件（如有）
if grep -q "媒体文件:" "$RAW_FILE"; then
  MEDIA_PATH=$(grep "^媒体文件:" "$RAW_FILE" | cut -d: -f2- | xargs)
  if [ -n "$MEDIA_PATH" ] && [ -f "$MEDIA_PATH" ]; then
    cp "$MEDIA_PATH" "wiki/media/$CATEGORY/"
    echo "已复制媒体文件: $MEDIA_PATH"
  fi
fi

# 更新索引
if [ -f "wiki/index.md" ]; then
  echo "- [[$KEYWORD]] - $SOURCE" >> wiki/index.md
  echo "已更新索引: wiki/index.md"
fi

# 更新日志
if [ -f "wiki/log.md" ]; then
  echo "- [$(date +%Y-%m-%d)] 新增 $WIKI_FILE | 来源: $SOURCE | 网址: $SOURCE_URL" >> wiki/log.md
  echo "已更新日志: wiki/log.md"
fi

echo "编译完成！"
