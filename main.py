"""Sobe tudo num processo so: WhatsApp + relogio + painel web.

    python main.py              (painel em http://localhost:8080)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from robo.estado import Armazem
from robo.motor import Motor
from robo.painel import criar_app
from robo.whatsapp import WhatsApp

load_dotenv()
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


async def principal() -> None:
    Path("data").mkdir(exist_ok=True)
    primeira_vez = not Path("data/estado.json").exists()
    arm = Armazem("data/estado.json")
    # o .env so vale na primeira execucao; depois quem manda e o painel (Config / Conexao)
    if primeira_vez and os.environ.get("GRUPO_NOME"):
        arm.estado.config.grupo_nome = os.environ["GRUPO_NOME"]
    if os.environ.get("ADMINS") and not arm.estado.config.admins:
        arm.estado.config.admins = [a.strip() for a in os.environ["ADMINS"].split(",") if a.strip()]
    if os.environ.get("AVISAR_ADMIN") and not arm.estado.config.avisar_admin:
        arm.estado.config.avisar_admin = os.environ["AVISAR_ADMIN"]
    arm.salvar()

    motor: Motor | None = None

    async def ao_receber(r):
        if motor:
            await motor.receber(r)

    wa = WhatsApp("data/sessao.db", ao_receber)
    motor = Motor(arm, wa)

    async def apos_conectar():
        # espera conectar e acha o grupo pelo nome
        while not wa.conectado:
            await asyncio.sleep(2)
        if not arm.estado.config.grupo_jid:
            jid = await motor.descobrir_grupo()
            log.info("grupo: %s", jid or "NAO ENCONTRADO (confira o nome em /config)")

    porta = int(os.environ.get("PAINEL_PORTA", "8080"))
    servidor = uvicorn.Server(uvicorn.Config(criar_app(arm, motor), host="0.0.0.0", port=porta, log_level="warning"))
    log.info("painel em http://localhost:%s", porta)

    async def conectar_sem_derrubar():
        try:
            await wa.conectar()
        except Exception:  # noqa: BLE001
            log.exception("primeira conexao falhou; o vigia tenta de novo")

    await asyncio.gather(conectar_sem_derrubar(), wa.vigiar(), apos_conectar(), motor.relogio(), servidor.serve())


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
