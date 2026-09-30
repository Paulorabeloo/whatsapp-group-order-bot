"""Chamada quando o rateio fica sem nenhuma interacao: '@all O X esta aberto, ainda temos N ml'."""

import asyncio
from datetime import timedelta

from robo.texto import agora
from tests.test_motor import msg
from tests.test_padroes import POST, novo


def envelhecer(arm, minutos):
    """Faz de conta que a abertura, os pedidos e a ultima chamada foram ha N minutos."""
    antes = (agora() - timedelta(minutes=minutos)).isoformat()
    with arm as e:
        r = e.rateios[0]
        r.aberto_em = antes
        for p in r.pedidos:
            p.em = antes
        if r.ultima_chamada_em:
            r.ultima_chamada_em = antes


def chamadas(wa):
    return [t for _, t, _ in wa.enviadas if "está aberto" in t or "Bora, acervistas" in t or "pra fecharmos o frasco e trazer" in t]


def test_chamada_quando_ninguem_interage(tmp_path):
    arm, wa, m = novo(tmp_path)
    with arm as e:
        e.config.chamada_silencio_min = 30
        e.config.chamada_max = 3

    async def roda():
        await m.receber(msg(POST.format(nome="KIRKE | TIZIANA", ml=50), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        await m._tique()
        assert chamadas(wa) == []                                   # recem aberto: quieto
        envelhecer(arm, 31)
        await m._tique()
        assert "Ainda temos 50 ml" in chamadas(wa)[-1] and arm.estado.rateios[0].chamadas == 1
        await m._tique()
        assert arm.estado.rateios[0].chamadas == 1                  # nao repete antes de 30 min
        await m.receber(msg("5ml", mid="x1"))                       # alguem interagiu: relogio zera
        await m._tique()
        assert arm.estado.rateios[0].chamadas == 1
        for _ in range(3):
            envelhecer(arm, 31)
            await m._tique()
        assert arm.estado.rateios[0].chamadas == 3                  # respeita o maximo
        assert sum("Bora, acervistas" in t for t in chamadas(wa)) == 1  # alternou os textos

    asyncio.run(roda())


def test_chamada_so_com_grupo_aberto(tmp_path):
    arm, wa, m = novo(tmp_path)

    async def roda():
        await m.receber(msg(POST.format(nome="KIRKE | TIZIANA", ml=50), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        with arm as e:
            e.grupo_aberto = False
        envelhecer(arm, 60)
        await m._tique()
        assert arm.estado.rateios[0].chamadas == 0

    asyncio.run(roda())


def test_chamada_desligada(tmp_path):
    arm, wa, m = novo(tmp_path)
    with arm as e:
        e.config.chamada_silencio_min = 0

    async def roda():
        await m.receber(msg(POST.format(nome="KIRKE | TIZIANA", ml=50), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        envelhecer(arm, 600)
        await m._tique()
        assert arm.estado.rateios[0].chamadas == 0

    asyncio.run(roda())


def test_chamada_nao_briga_com_urgencia(tmp_path):
    arm, wa, m = novo(tmp_path)

    async def roda():
        await m.receber(msg(POST.format(nome="ERBA | XERJOFF", ml=20), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        await m.receber(msg("15ml", mid="x1"))                      # sobram 5: caso de urgencia, nao de chamada
        envelhecer(arm, 60)
        await m._tique()
        assert arm.estado.rateios[0].chamadas == 0

    asyncio.run(roda())


def test_varios_abertos_so_o_da_vez_recebe_chamada(tmp_path):
    arm, wa, m = novo(tmp_path)

    async def roda():
        for i, n in enumerate(["KIRKE | TIZIANA", "TORINO | XERJOFF", "CHICELLE | UNIQUE"]):
            await m.receber(msg(POST.format(nome=n, ml=50), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid=f"p{i}"))
            await asyncio.sleep(0.01)
        antes = (agora() - timedelta(minutes=40)).isoformat()
        with arm as e:
            for r in e.rateios:
                r.aberto_em = antes
            next(r for r in e.rateios if r.nome.startswith("CHICELLE")).destaque_em = (agora() - timedelta(minutes=35)).isoformat()
        await m._tique()
        cham = chamadas(wa)
        assert len(cham) == 1 and "CHICELLE" in cham[0]

    asyncio.run(roda())


def test_arroba_all_marca_todo_mundo(tmp_path):
    arm, wa, m = novo(tmp_path)
    m._todos = ["1@lid", "2@lid", "3@lid"]
    asyncio.run(m._mandar("@all 30 min pra abertura do X 💎"))
    asyncio.run(m._mandar("Restam 2 ml"))
    assert wa.enviadas[0][2] == ["1@lid", "2@lid", "3@lid"]
    assert not wa.enviadas[1][2]
