#!/bin/sh
set -eu
SRC=${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
ROOT=/opt/d-hub
sudo mkdir -p "$ROOT"
sudo chown -R duanz:duanz "$ROOT"
for type in mcp skills wiki files; do
  for tier in global agents projects; do mkdir -p "$ROOT/$type/$tier"; done
done
for dir in config data logs backups scripts; do mkdir -p "$ROOT/$dir"; done
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install "$SRC[memory]"
cp -r "$SRC/scripts/." "$ROOT/scripts/"
chmod +x "$ROOT/scripts/"*.sh "$ROOT/scripts/"*.py
[ -f "$ROOT/config/dhub.env" ] || cp "$SRC/deploy/dhub.env.example" "$ROOT/config/dhub.env"
sudo cp "$SRC/deploy/dhub.service" /etc/systemd/system/dhub.service
sudo systemctl daemon-reload
sudo systemctl enable --now dhub
curl -fsS http://127.0.0.1:10101/health
