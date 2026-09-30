#!/usr/bin/env bash
# Atualiza o robo com a versao mais nova do GitHub e reinicia. Roda como root.
set -euo pipefail
APP="/opt/robo-grupo"
/usr/local/bin/robo-grupo-backup || true
[ -d "$APP/.git" ] && git -C "$APP" pull -q || echo "sem git: codigo novo chega por deploy/enviar.sh"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R robo:robo "$APP"
systemctl restart robo-grupo
sleep 3
systemctl --no-pager status robo-grupo | head -5
