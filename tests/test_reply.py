"""Resposta (reply) a mensagens diferentes: pedido de outra pessoa, urgencia do robo, perfume fechado."""

import asyncio

from tests.test_varios_abertos import ADMIN, POST, cenario, manda, ml


def test_eu_tambem_respondendo_pedido_de_outra_pessoa(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "3ml do kirke", "x1")                                   # Ana pede Kirke
    manda(m, "5ml do chicelle", "x2", autor="3@s.whatsapp.net", nome="Cris")   # Chicelle vira o da vez
    asyncio.run(m.receber(__import__("tests.test_motor", fromlist=["msg"]).msg("5ml", autor="2@s.whatsapp.net", nome="Bia", mid="x3", citado="x1")))
    assert ml(arm, "KIRKE") == [(3, False), (5, False)] and ml(arm, "CHICELLE") == [(5, False)]


def test_reply_na_urgencia_do_robo(tmp_path):
    arm, wa, m = cenario(tmp_path)
    from tests.test_motor import msg

    async def roda():
        await m.receber(msg("45ml do torino", autor="1@s.whatsapp.net", nome="Ana", mid="x1"))   # Torino (50) fica com 5 -> urgencia
        await asyncio.sleep(0.05)
        urg = next(i for i, (_, t, _) in enumerate(wa.enviadas) if "TORINO" in t and "😱" in t)
        mid_urg = f"env{urg + 1}"
        torino = next(r for r in arm.estado.rateios if r.nome.startswith("TORINO"))
        assert mid_urg in torino.lista_msg_ids
        await m.receber(msg("eu quero 5ml", autor="2@s.whatsapp.net", nome="Bia", mid="x2", citado=mid_urg))

    asyncio.run(roda())
    assert ml(arm, "TORINO") == [(45, False), (5, False)] and ml(arm, "CHICELLE") == []


def test_reply_em_post_de_perfume_fechado(tmp_path):
    arm, wa, m = cenario(tmp_path)
    with arm as e:
        next(r for r in e.rateios if r.nome.startswith("KIRKE")).status = "fechado"
    from tests.test_motor import msg
    asyncio.run(m.receber(msg("5ml", autor="2@s.whatsapp.net", nome="Bia", mid="x1", citado="p0")))   # p0 = post do Kirke
    assert "KIRKE | TIZIANA TERENZI já fechou" in wa.enviadas[-1][1]
    assert all(r.pedidos == [] for r in arm.estado.rateios)


def test_reply_em_conversa_qualquer_segue_o_da_vez(tmp_path):
    arm, wa, m = cenario(tmp_path)
    from tests.test_motor import msg
    asyncio.run(m.receber(msg("5ml", autor="2@s.whatsapp.net", nome="Bia", mid="x1", citado="mensagem-de-bom-dia")))
    assert ml(arm, "CHICELLE") == [(5, False)]
