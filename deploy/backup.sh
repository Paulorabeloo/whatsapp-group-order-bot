#!/usr/bin/env bash
# Copia o estado (rateios, agenda, ajustes) e as fotos pra backups/AAAA-MM-DD.tar.gz. Guarda 30 dias.
# A sessao do WhatsApp (data/sessao.db) tambem vai: restaurar ela evita escanear o QR de novo.
set -euo pipefail
APP="/opt/robo-grupo"
cd "$APP"
mkdir -p backups
tar -czf "backups/$(date +%F).tar.gz" data .env 2>/dev/null
find backups -name '*.tar.gz' -mtime +30 -delete
