#!/usr/bin/env bash
# Roda NO SEU PC (Git Bash). Manda o codigo do commit atual pra VPS e instala/atualiza.
#   deploy/enviar.sh SEU_IP                    so o codigo
#   deploy/enviar.sh SEU_IP --com-dados        codigo + data/ (sessao do WhatsApp, estado, fotos)
#   deploy/enviar.sh SEU_IP --dominio painel.seudominio.com.br
# Usa a chave ~/.ssh/robo_vps. Repositorio e privado, entao o codigo vai daqui, nao do GitHub.
set -euo pipefail
IP="$1"; shift
DOMINIO=""; DADOS=0
while [ $# -gt 0 ]; do
  case "$1" in --com-dados) DADOS=1;; --dominio) DOMINIO="$2"; shift;; esac; shift
done
SSH="ssh -i $HOME/.ssh/robo_vps -o BatchMode=yes root@$IP"
cd "$(dirname "$0")/.."

echo "==> enviando o codigo ($(git rev-parse --short HEAD))"
$SSH "mkdir -p /opt/robo-grupo"
git archive --format=tar HEAD | $SSH "tar -x -C /opt/robo-grupo"

if [ "$DADOS" = 1 ]; then
  echo "==> enviando data/ (sessao do WhatsApp, estado, fotos) — o robo do PC precisa estar DESLIGADO"
  $SSH "systemctl stop robo-grupo 2>/dev/null || true; mkdir -p /opt/robo-grupo/data"
  tar -c -C data sessao.db estado.json fotos | $SSH "tar -x -C /opt/robo-grupo/data"
fi

if $SSH "systemctl list-unit-files robo-grupo.service >/dev/null 2>&1 && test -f /opt/robo-grupo/.env"; then
  echo "==> atualizando"
  $SSH "bash /opt/robo-grupo/deploy/update.sh"
else
  echo "==> primeira instalacao"
  $SSH "bash /opt/robo-grupo/deploy/install.sh $DOMINIO"
fi
