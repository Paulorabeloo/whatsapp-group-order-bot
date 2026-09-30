"""Robo reinicia no meio de um rateio: nada se perde."""

import asyncio

from robo.estado import Armazem
from robo.motor import Motor
from tests.test_motor import GRUPO, WaFake, msg
from tests.test_varios_abertos import ADMIN, POST, cenario, ml


def test_lista_pendente_sai_depois_do_reinicio(tmp_path):
    arm = Armazem(tmp_path / "e.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins = "ao_vivo", GRUPO, ["5519999"]
        e.config.segundos_ate_postar_lista = 60        # lista ficaria 60 s na espera
        e.grupo_aberto = True
    m = Motor(arm, WaFake())

    async def antes():
        await m.receber(msg(POST.format(n="CHICELLE | UNIQUE"), **ADMIN, mid="p1"))
        await m.receber(msg("5ml", mid="x1"))
        # "cai" antes dos 60 s: o timer morre junto com o processo

    asyncio.run(antes())
    assert Armazem(arm.caminho).estado.rateios[0].lista_pendente is True

    arm2 = Armazem(arm.caminho)                           # robo sobe de novo
    with arm2 as e:
        e.config.segundos_ate_postar_lista = 0
    wa2 = WaFake()
    m2 = Motor(arm2, wa2)

    async def depois():
        tarefa = asyncio.create_task(m2.relogio())
        await asyncio.sleep(0.1)
        tarefa.cancel()

    asyncio.run(depois())
    assert any("💎 5ml" in t for _, t, _ in wa2.enviadas)
    assert arm2.estado.rateios[0].lista_pendente is False


def test_pedido_separado_nao_usa_nome_do_outro_perfume(tmp_path):
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg("5 ml do Torino e 5 ml do Chicelle", autor="1@s.whatsapp.net", nome="Marketing", mid="x1")))
    nomes = [p.nome for r in arm.estado.rateios for p in r.pedidos]
    assert nomes == ["Marketing", "Marketing"]


def test_nome_escrito_sem_palavra_de_perfume(tmp_path):
    arm, wa, m = cenario(tmp_path)
    asyncio.run(m.receber(msg("Clara 5ml chicelle", autor="1@s.whatsapp.net", nome="Cle", mid="x1")))
    r = next(x for x in arm.estado.rateios if x.nome.startswith("CHICELLE"))
    assert [p.nome for p in r.pedidos] == ["Clara"]
