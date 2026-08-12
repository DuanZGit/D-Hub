#!/bin/sh
set -eu
BASE=${DHUB_URL:-http://127.0.0.1:10101}
if [ -n "${DHUB_API_KEY:-}" ]; then
  curl -fsS -X POST -H "Authorization: Bearer $DHUB_API_KEY" "$BASE/backup"
else
  curl -fsS -X POST "$BASE/backup"
fi
printf '\n'
