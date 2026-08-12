#!/bin/sh
set -eu
BASE=${DHUB_URL:-http://127.0.0.1:10101}
ADMIN_KEY=${DHUB_ADMIN_KEY:-${DHUB_API_KEY:-}}
if [ -n "$ADMIN_KEY" ]; then
  curl -fsS -X POST -H "Authorization: Bearer $ADMIN_KEY" "$BASE/backup"
else
  curl -fsS -X POST "$BASE/backup"
fi
printf '\n'
