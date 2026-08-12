#!/bin/sh
set -eu
SRC=${1:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
ROOT=/opt/d-hub
SERVICE_USER=${SUDO_USER:-$(id -un)}
SERVICE_GROUP=$(id -gn "$SERVICE_USER")
sudo mkdir -p "$ROOT"
sudo chown -R "$SERVICE_USER:$SERVICE_GROUP" "$ROOT"
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
DHUB_EFFECTIVE_KEY=$(sed -n 's/^DHUB_ADMIN_KEY=//p' "$ROOT/config/dhub.env" | tail -n 1)
if [ -z "$DHUB_EFFECTIVE_KEY" ]; then
  DHUB_EFFECTIVE_KEY=$(sed -n 's/^DHUB_API_KEY=//p' "$ROOT/config/dhub.env" | tail -n 1)
fi
if [ -z "$DHUB_EFFECTIVE_KEY" ]; then
  DHUB_GENERATED_KEY=$("$ROOT/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')
  printf '\nDHUB_ADMIN_KEY=%s\n' "$DHUB_GENERATED_KEY" >> "$ROOT/config/dhub.env"
fi
chmod 600 "$ROOT/config/dhub.env"
for unit in dhub-backup.service dhub-backup.timer dhub-sync.service dhub-sync.timer; do
  sed "s/^User=duanz$/User=$SERVICE_USER/" "$SRC/deploy/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sed "s/^User=duanz$/User=$SERVICE_USER/" "$SRC/deploy/dhub.service" | sudo tee /etc/systemd/system/dhub.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now dhub
sudo systemctl enable --now dhub-backup.timer dhub-sync.timer
DHUB_LOCAL_URL=$(sed -n 's/^DHUB_URL=//p' "$ROOT/config/dhub.env" | tail -n 1)
DHUB_LOCAL_URL=${DHUB_LOCAL_URL:-http://127.0.0.1:10101}
attempt=0
until curl -fsS "$DHUB_LOCAL_URL/health"; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 30 ] || { sudo systemctl status dhub --no-pager; exit 1; }
  sleep 1
done
curl -fsS -o /dev/null "$DHUB_LOCAL_URL/"
DHUB_EFFECTIVE_KEY=$(sed -n 's/^DHUB_ADMIN_KEY=//p' "$ROOT/config/dhub.env" | tail -n 1)
DHUB_EFFECTIVE_KEY=${DHUB_EFFECTIVE_KEY:-$(sed -n 's/^DHUB_API_KEY=//p' "$ROOT/config/dhub.env" | tail -n 1)}
printf '\nDashboard: %s/\nAdmin key: %s\n' "$DHUB_LOCAL_URL" "$DHUB_EFFECTIVE_KEY"
sudo chown -R "$SERVICE_USER:$SERVICE_GROUP" "$ROOT"
