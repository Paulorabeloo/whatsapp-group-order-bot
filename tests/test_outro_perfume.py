"""Conversa sobre OUTRO perfume enquanto um rateio esta aberto: o robo nunca anota no perfume errado."""

import asyncio

import pytest

from robo.estado import Armazem
from robo.motor import Motor
from tests.test_motor import GRUPO, WaFake, msg

POST = "✨ {n}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 20 ml: R$ 200,00 | APC\nQUANTIDADE DO FRASCO: 50 ml"
ADMIN = dict(autor="9@s.whatsapp.net", nome="Admin", fone="5519999")


def cenario(tmp_path):
    """Torino 21 ja fechou; Chicelle esta aberto."""
    arm = Armazem(tmp_path / "e.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins, e.config.avisar_admin = "ao_vivo", GRUPO, ["5519999"], "5519999"
        e.config.segundos_ate_postar_lista = 0
        e.grupo_aberto = True
    wa = WaFake()
    m = Motor(arm, wa)

    async def prepara():
        await m.receber(msg(POST.format(n="TORINO 21 | XERJOFF"), **ADMIN, mid="p1"))
        with arm as e:
            e.rateios[0].status = "fechado"
        await m.receber(msg(POST.format(n="CHICELLE | UNIQUE"), **ADMIN, mid="p2"))

    asyncio.run(prepara())
    return arm, wa, m


def chicelle(arm):
    return next(r for r in arm.estado.rateios if r.nome.startswith("CHICELLE"))


@pytest.mark.parametrize("texto", [
    "quero o apc do torino", "apc torino", "5ml do torino", "quero 3ml do torino por favor", "Torino 5ml",
    "5ml do vibrato", "apc do vibrato", "quero o apc do baccarat",
    "o apc do torino já saiu?", "nossa, a Cris levou o apc do torino, que sorte", "o torino era maravilhoso",
])
def test_fala_de_outro_perfume_nao_anota_no_chicelle(tmp_path, texto):
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg(texto, autor="1@s.whatsapp.net", nome="Ana", mid="x1")))
    assert chicelle(arm).pedidos == []


@pytest.mark.parametrize("texto", ["quero o apc do torino", "5ml do torino"])
def test_perfume_fechado_responde_que_fechou(tmp_path, texto):
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg(texto, autor="1@s.whatsapp.net", nome="Ana", mid="x1")))
    assert "TORINO 21 | XERJOFF já fechou" in wa.enviadas[-1][1]


def test_perfume_desconhecido_avisa_o_admin(tmp_path):
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg("5ml do vibrato", autor="1@s.whatsapp.net", nome="Ana", mid="x1")))
    para, texto, _ = wa.enviadas[-1]
    assert para == "5519999@s.whatsapp.net" and "não está aberto" in texto


def test_conversa_sobre_outro_nao_gera_resposta(tmp_path):
    arm, wa, m = cenario(tmp_path)
    n = len(wa.enviadas)
    asyncio.run(m.receber(msg("o torino era maravilhoso", autor="1@s.whatsapp.net", nome="Ana", mid="x1")))
    assert len(wa.enviadas) == n


@pytest.mark.parametrize("texto,ml", [
    ("5ml", 5), ("Mateo 5ml", 5), ("5ml do chicelle", 5), ("quero de 3ml", 3), ("5ml do frasco novo", 5),
    ("apc", 20), ("quero o apc do chicelle", 20), ("5ml da mesma", 5),
])
def test_pedidos_normais_continuam_indo_pro_chicelle(tmp_path, texto, ml):
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg(texto, autor="1@s.whatsapp.net", nome="Ana", mid="x1")))
    assert [p.ml for p in chicelle(arm).pedidos] == [ml]


def test_reply_no_post_manda_mesmo_citando_outro_nome(tmp_path):
    """Se a pessoa responde o post do Chicelle, vale o Chicelle, mesmo que a frase cite outro perfume."""
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg("5ml, gostei mais que o torino", autor="1@s.whatsapp.net", nome="Ana", mid="x1", citado="p2")))
    assert [p.ml for p in chicelle(arm).pedidos] == [5]


def test_dois_abertos_nome_vai_pro_certo(tmp_path):
    arm, wa, m = cenario(tmp_path)
    with arm as e:
        next(r for r in e.rateios if r.nome.startswith("TORINO")).status = "aberto"
    asyncio.run(m.receber(msg("5ml do torino", autor="1@s.whatsapp.net", nome="Ana", mid="x1")))
    torino = next(r for r in arm.estado.rateios if r.nome.startswith("TORINO"))
    assert [p.ml for p in torino.pedidos] == [5] and chicelle(arm).pedidos == []
