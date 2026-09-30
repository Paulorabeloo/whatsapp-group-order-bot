"""Demo sem WhatsApp: um grupo simulado com clientes pedindo sozinhos, e o painel de verdade.

    python demo.py        ->  http://127.0.0.1:8080  (sem senha, dados ficticios)

O robo, as regras e o painel sao os mesmos da producao. So o WhatsApp e trocado por um simulado
que imprime no terminal o que o robo mandaria no grupo.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import random
import shutil
import struct
import zlib
from datetime import timedelta
from pathlib import Path

import uvicorn

from robo.estado import Abertura, Armazem
from robo.motor import Motor
from robo.painel import criar_app
from robo.texto import agora
from robo.whatsapp import Recebida

GRUPO = "demo-group@g.us"
PASTA = Path(__file__).resolve().parent / ".demo"
log = logging.getLogger("demo")


class WhatsAppSimulado:
    """Mesma interface do robo/whatsapp.py; guarda o estado do grupo em memoria e imprime o que sairia."""

    def __init__(self):
        self.conectado, self.conectando, self.meu_jid, self.qr_svg, self.qr_em = True, False, "5500000000000@s.whatsapp.net", None, 0
        self.aberto, self._n = True, 0

    def _id(self) -> str:
        self._n += 1
        return f"BOT{self._n:05d}"

    async def enviar_texto(self, para, texto, mencoes=None):
        print(f"\n\033[36m[robo -> grupo]\033[0m {texto}\n")
        return self._id()

    async def enviar_imagem(self, para, arquivo, legenda, mencoes=None):
        print(f"\n\033[36m[robo -> grupo] 🖼  {Path(arquivo).name}\033[0m\n{legenda}\n")
        return self._id()

    async def reagir(self, chat, autor, msg_id, emoji="👍"):
        print(f"\033[90m  {emoji} reagiu ao pedido {msg_id}\033[0m")

    async def abrir_grupo(self, g):
        self.aberto = True
        print("\033[32m[grupo aberto]\033[0m")

    async def fechar_grupo(self, g):
        self.aberto = False
        print("\033[31m[grupo fechado: so admins falam]\033[0m")

    async def grupo_esta_aberto(self, g):
        return self.aberto

    async def admins_do_grupo(self, g):
        return {"5500000000001@s.whatsapp.net"}

    async def participantes(self, g):
        return [f"55119000000{i:02d}@s.whatsapp.net" for i in range(1, 41)]

    async def grupos(self):
        return [{"nome": "Demo Store | Group 1", "jid": GRUPO, "pessoas": 41, "sou_admin": True, "fechado": not self.aberto}]

    async def grupo_por_nome(self, nome):
        return GRUPO


def png(caminho: Path, cor1: tuple, cor2: tuple, lado: int = 480) -> None:
    """foto de exemplo (degrade) sem depender de biblioteca de imagem"""
    linhas = b""
    for y in range(lado):
        t = y / (lado - 1)
        px = bytes(int(a + (b - a) * t) for a, b in zip(cor1, cor2))
        linhas += b"\x00" + px * lado
    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    caminho.write_bytes(b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 2, 0, 0, 0))
                        + bloco(b"IDAT", zlib.compress(linhas, 9)) + bloco(b"IEND", b""))


def montar() -> Armazem:
    shutil.rmtree(PASTA, ignore_errors=True)
    (PASTA / "data" / "fotos").mkdir(parents=True)
    os.chdir(PASTA)   # o painel le data/fotos e data/exemplos.jsonl relativos a pasta atual
    png(Path("data/fotos/noir.png"), (40, 44, 52), (120, 96, 80))
    png(Path("data/fotos/iris.png"), (214, 206, 230), (120, 104, 160))
    png(Path("data/fotos/citrus.png"), (250, 228, 170), (230, 140, 60))

    arm = Armazem("data/estado.json")
    ag = agora()
    extra = "Payment via PIX or card.\nPickup or delivery after the split closes."
    with arm as e:
        e.modo, e.grupo_aberto = "ao_vivo", True
        c = e.config
        c.grupo_nome, c.grupo_jid = "Demo Store | Group 1", GRUPO
        c.segundos_ate_postar_lista, c.chamada_silencio_min = 8, 3
        e.aberturas += [
            Abertura(id="d1", nome="NOIR SANTAL | MAISON ALPHA", valor_ml=18, total_ml=60, minimo=3, tamanhos=[3, 5, 10],
                     apc_ml=20, abre_em=(ag - timedelta(minutes=40)).isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat(),
                     foto="data/fotos/noir.png", texto_extra=extra),
            Abertura(id="d2", nome="IRIS VELOURS | ATELIER BETA", valor_ml=24, total_ml=50, minimo=3, tamanhos=[3, 5, 10],
                     apc_ml=15, abre_em=(ag - timedelta(minutes=5)).isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat(),
                     foto="data/fotos/iris.png", texto_extra=extra),
            Abertura(id="d3", nome="CITRUS NOON | CASA GAMMA", valor_ml=15, total_ml=80, minimo=3, tamanhos=[3, 5, 10, 15],
                     apc_ml=None, abre_em=(ag + timedelta(hours=3)).isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat(),
                     foto="data/fotos/citrus.png", descricao="A bright citrus opening over a soft musky base.",
                     aviso_em=(ag + timedelta(hours=1)).isoformat(),
                     aviso_texto="💗 TODAY AT 3PM!\n\nCITRUS NOON | CASA GAMMA opens here in the group. ✨"),
        ]
    return arm


# conversa ficticia: (nome, texto, responde_a) — responde_a: "noir"/"iris" = o post daquele perfume
CONVERSA = [
    ("Ana", "5ml", None), ("Bruno", "apc", "noir"), ("Clara", "3 ml", "iris"), ("Davi", "bom dia pessoal!", None),
    ("Elisa", "10ml do noir", None), ("Fernando", "apc", None), ("Gabi", "quero 5ml pra conhecer", "iris"),
    ("Heitor", "5ml", "noir"), ("Iara", "3ml", None), ("Joao", "que cheiro tem o iris?", None),
    ("Ana", "altera pra 10ml", None), ("Karen", "5 ml", "noir"), ("Leo", "cancela o meu", None),
    ("Mila", "7ml iris", None), ("Nina", "3ml citrus", None), ("Otavio", "5ml", "iris"),
]


async def clientes(motor: Motor, wa: WhatsAppSimulado) -> None:
    await asyncio.sleep(6)
    pessoas = {n: f"55119000000{i:02d}@s.whatsapp.net" for i, n in enumerate(sorted({c[0] for c in CONVERSA}), start=1)}
    for i in itertools.count():
        nome, texto, resp = CONVERSA[i % len(CONVERSA)]
        rat = next((r for r in motor.arm.estado.rateios if resp and r.nome.lower().startswith(resp)), None)
        autor = pessoas[nome]
        print(f"\033[33m[{nome}]\033[0m {texto}" + (f"  \033[90m(respondendo o post do {rat.nome})\033[0m" if rat else ""))
        await motor.receber(Recebida(msg_id=f"C{i:05d}", chat=GRUPO, autor=autor, autor_fone=autor.split("@")[0], push_name=nome,
                                     texto=texto, citado_id=rat.post_msg_id if rat else None, apagou_id=None, eh_grupo=True,
                                     de_mim=False, tem_imagem=False, citado_texto=None))
        await asyncio.sleep(random.uniform(5, 9))
        if i + 1 == len(CONVERSA):
            print("\033[90m(fim da conversa de exemplo; o robo segue rodando — mexa no painel)\033[0m")
            return


async def principal() -> None:
    logging.basicConfig(level=logging.WARNING)
    arm = montar()
    wa = WhatsAppSimulado()
    motor = Motor(arm, wa)
    await motor.abrir_agora("d1")
    await motor.abrir_agora("d2")
    servidor = uvicorn.Server(uvicorn.Config(criar_app(arm, motor, sem_senha=True), host="127.0.0.1", port=8080, log_level="warning"))
    print("\npainel: http://127.0.0.1:8080  (Ctrl+C pra sair)\n")
    await asyncio.gather(servidor.serve(), motor.relogio(), clientes(motor, wa))


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
