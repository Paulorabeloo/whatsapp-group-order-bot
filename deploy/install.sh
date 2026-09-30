#!/usr/bin/env bash
# Instala o Robô do Grupo numa VPS Ubuntu 24.04 (roda como root, uma vez).
#   curl -fsSL https://raw.githubusercontent.com/Paulorabeloo/whatsapp-group-order-bot/main/deploy/install.sh | bash -s -- robo.seudominio.com.br
# Argumento 1 (opcional): dominio do painel. Sem dominio, o painel fica em http://IP:8080.
set -euo pipefail

DOMINIO="${1:-}"
REPO="https://github.com/Paulorabeloo/whatsapp-group-order-bot.git"
USUARIO="robo"
APP="/opt/robo-grupo"

echo "==> pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip ffmpeg ufw curl >/dev/null

echo "==> usuario de servico '$USUARIO'"
id -u "$USUARIO" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$USUARIO"

echo "==> codigo em $APP"
if [ -d "$APP/.git" ]; then
  git -C "$APP" pull -q
elif [ -f "$APP/main.py" ]; then
  echo "    codigo ja enviado (deploy/enviar.sh), sem git"
else
  git clone -q "$REPO" "$APP"
fi
mkdir -p "$APP/data/fotos" "$APP/backups"

echo "==> ambiente python"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

if [ ! -f "$APP/.env" ]; then
  # (tr </dev/urandom | head quebra com pipefail: o tr morre de SIGPIPE e o script sai calado)
  SENHA="$(python3 -c 'import secrets; print(secrets.token_urlsafe(15))')"
  # numeros de exemplo do .env.example NUNCA vao pra producao: admins e aviso se configuram no painel
  sed -e "s/^PAINEL_SENHA=.*/PAINEL_SENHA=$SENHA/" -e "s/^ADMINS=.*/ADMINS=/" -e "s/^AVISAR_ADMIN=.*/AVISAR_ADMIN=/"       -e "s/^GRUPO_NOME=.*/GRUPO_NOME=Minha Loja | Grupo 1/" "$APP/.env.example" >"$APP/.env"
  echo "    senha do painel gerada: $SENHA   (esta em $APP/.env)"
fi
chown -R "$USUARIO:$USUARIO" "$APP"
chmod 600 "$APP/.env"

echo "==> servico systemd (reinicia sozinho, sobe com a maquina)"
install -m 644 "$APP/deploy/robo-grupo.service" /etc/systemd/system/robo-grupo.service
systemctl daemon-reload
systemctl enable --now robo-grupo
systemctl restart robo-grupo

echo "==> backup diario do estado (03:15) em $APP/backups, guarda 30 dias"
install -m 755 "$APP/deploy/backup.sh" /usr/local/bin/robo-grupo-backup
echo "15 3 * * * $USUARIO /usr/local/bin/robo-grupo-backup" >/etc/cron.d/robo-grupo-backup

echo "==> firewall"
ufw allow OpenSSH >/dev/null
if [ -n "$DOMINIO" ]; then
  echo "==> HTTPS com Caddy para $DOMINIO"
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' >/etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  sed "s/DOMINIO/$DOMINIO/" "$APP/deploy/Caddyfile" >/etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
  ufw allow 80,443/tcp >/dev/null
  echo "    painel: https://$DOMINIO"
else
  # sem dominio o painel NAO fica exposto (a senha iria sem criptografia): acesse por tunel SSH
  #   ssh -L 8080:127.0.0.1:8080 root@IP   e abra http://localhost:8080
  echo "    painel sem dominio: use um tunel SSH (ssh -L 8080:127.0.0.1:8080 root@IP) e abra http://localhost:8080"
fi
ufw --force enable >/dev/null

echo
echo "==> pronto. Proximo passo: abrir o painel, aba Conexao, e escanear o QR com o celular do chip."
echo "    logs ao vivo:  journalctl -u robo-grupo -f"
echo "    atualizar:     $APP/deploy/update.sh"
