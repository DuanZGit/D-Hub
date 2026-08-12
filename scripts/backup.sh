#!/bin/sh
set -eu
BASE=${DHUB_URL:-http://127.0.0.1:10101}
curl -fsS -X POST "$BASE/backup"
printf '\n'
