"""Reply com varios perfumes abertos: no post do robo (Barbara) e no post repostado por outra pessoa (Sofia -> Marina)."""

import asyncio

import pytest

from tests.test_observando import POST, ambiente
from tests.test_motor import msg

PRISCILA = dict(autor="111222333@lid", nome="Marina")   # admin do grupo (WaComAdmins)


def _tres_abertos(m):
    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA"), **PRISCILA, mid="post_kirke"))
        await m.receber(msg(POST.format(n="VIBRATO | SOSPIRO"), **PRISCILA, mid="post_vibrato"))
        await m.receber(msg(POST.format(n="IMPADIA | BDK"), **PRISCILA, mid="post_impadia"))   # o mais recente
    return roda()


def test_reply_no_post_vai_pro_perfume_certo(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    asyncio.run(_tres_abertos(m))
    asyncio.run(m.receber(msg("5 ml", autor="7@s.whatsapp.net", nome="Bruna", citado="post_kirke", mid="b1")))
    kirke = next(r for r in arm.estado.rateios if r.nome.startswith("KIRKE"))
    assert [(p.nome, p.ml) for p in kirke.pedidos] == [("Bruna", 5)]


def test_reply_no_post_repostado_pelo_admin(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    asyncio.run(_tres_abertos(m))
    # Marina reposta o Vibrato (mesma foto/legenda) mais tarde; Sofia responde o repost
    asyncio.run(m.receber(msg(POST.format(n="VIBRATO | SOSPIRO"), **PRISCILA, mid="repost_vibrato")))
    asyncio.run(m.receber(msg("5ml", autor="8@s.whatsapp.net", nome="Sofia", citado="repost_vibrato", mid="s1")))
    vib = next(r for r in arm.estado.rateios if r.nome.startswith("VIBRATO"))
    assert [(p.nome, p.ml) for p in vib.pedidos] == [("Sofia", 5)]
    assert len(arm.estado.rateios) == 3


def test_reply_no_post_repostado_por_quem_nao_e_admin(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    asyncio.run(_tres_abertos(m))
    asyncio.run(m.receber(msg(POST.format(n="VIBRATO | SOSPIRO"), autor="9@s.whatsapp.net", nome="Cliente", mid="repost2")))
    asyncio.run(m.receber(msg("5ml", autor="8@s.whatsapp.net", nome="Sofia", citado="repost2", mid="s2")))
    vib = next(r for r in arm.estado.rateios if r.nome.startswith("VIBRATO"))
    assert [(p.nome, p.ml) for p in vib.pedidos] == [("Sofia", 5)]


def _resp(texto, citado, citado_texto, mid, autor="8@s.whatsapp.net", nome="Enzo"):
    r = msg(texto, autor=autor, nome=nome, citado=citado, mid=mid)
    r.citado_texto = citado_texto
    return r


def test_reply_na_imagem_de_disponiveis_nao_entra_no_perfume_aberto(tmp_path):
    # caso real 28/09: Enzo respondeu a imagem "💎DISPONÍVEIS💎" da Iris com "3ml vibrato" / "3ml creed imperial"
    arm, wa, m = ambiente(tmp_path)
    with arm as e:
        e.modo = "ao_vivo"

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="BAL D'AFRIQUE | BYREDO"), **PRISCILA, mid="post_bal"))
        await m.receber(_resp("3ml vibrato", "img_helen", "💎DISPONÍVEIS💎", "e1"))
        await m.receber(_resp("3ml creed imperial", "img_helen", "💎DISPONÍVEIS💎", "e2"))
        await m.receber(_resp("5ml", "foto_sem_legenda", "", "e3"))   # foto qualquer: vale (perfume unico aberto)

    asyncio.run(roda())
    assert [(p.nome, p.ml) for p in arm.estado.rateios[0].pedidos] == [("Enzo", 5)]
    assert sum(a["motivo"] == "respondeu mensagem que não é de perfume aberto" for a in arm.estado.aprender) == 2


def test_reply_em_mensagem_que_cita_o_perfume_aberto_vale(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    asyncio.run(_tres_abertos(m))
    asyncio.run(m.receber(_resp("5ml", "conversa1", "gente o vibrato é maravilhoso", "s1", nome="Sofia")))
    vib = next(r for r in arm.estado.rateios if r.nome.startswith("VIBRATO"))
    assert [(p.nome, p.ml) for p in vib.pedidos] == [("Sofia", 5)]


def test_quero_para_conhecer_nao_vira_nome():
    from robo.interpretar import interpretar
    assert interpretar("Quero 3ml para conhecer")["nome"] is None


def test_pedido_de_perfume_que_nao_esta_aberto_nao_entra(tmp_path):
    # caso real 28/09 sem reply: com o Bal d'Afrique aberto, "3ml vibrato" / "3ml creed imperial" nao sao do Bal
    arm, wa, m = ambiente(tmp_path)

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="BAL D'AFRIQUE | BYREDO"), **PRISCILA, mid="post_bal"))
        await m.receber(msg("3ml vibrato", autor="8@s.whatsapp.net", nome="Enzo", mid="e1"))
        await m.receber(msg("3ml creed imperial", autor="8@s.whatsapp.net", nome="Enzo", mid="e2"))
        await m.receber(msg("5ml do bal", autor="9@s.whatsapp.net", nome="Rita", mid="r1"))
        await m.receber(msg("5ml byredo", autor="10@s.whatsapp.net", nome="Tina", mid="t1"))
        await m.receber(msg("5ml Celina", autor="11@s.whatsapp.net", nome="Bruno", mid="c1"))   # pra outra pessoa

    asyncio.run(roda())
    assert [(p.nome, p.ml) for p in arm.estado.rateios[0].pedidos] == [("Rita", 5), ("Tina", 5), ("Celina", 5)]
    assert "BAL D'AFRIQUE | BYREDO" in arm.estado.perfumes_vistos


@pytest.mark.regra_pausado
def test_lista_que_o_admin_manda_nao_entra_no_sistema(tmp_path):
    # 28-29/09: listas postadas por admin viravam copias pausadas (Tobacco, Vibrato, Orience, Argentina) e confundiam o
    # painel; e a lista do admin do perfume do sistema reescrevia os pedidos (Diana/Gustavo sem numero)
    arm, wa, m = ambiente(tmp_path)
    from robo.post import ler_post
    from robo.rateio import novo_rateio
    with arm as e:
        e.rateios.append(novo_rateio(ler_post(POST.format(n="BAL D'AFRIQUE | BYREDO")), "post_bal"))

    async def roda():
        await m._tique()
        await m.receber(msg("5ml", autor="8@s.whatsapp.net", nome="Tina", citado="post_bal", mid="t1"))
        await m.receber(msg(POST.format(n="VIBRATO | SOSPIRO") + "\n\n💎5ml - Quenia\n💎3ml - Paula", **PRISCILA, mid="lista_vib"))
        await m.receber(msg(POST.format(n="BAL D'AFRIQUE | BYREDO") + "\n\n💎5ml - Tina\n💎10ml - Gustavo", **PRISCILA, mid="lista_bal"))
        await m.receber(msg("3ml", autor="9@s.whatsapp.net", nome="Bia", citado="lista_bal", mid="b1"))

    asyncio.run(roda())
    assert [r.nome for r in arm.estado.rateios] == ["BAL D'AFRIQUE | BYREDO"]          # nada de copia pausada
    assert [(p.nome, p.ml) for p in arm.estado.rateios[0].pedidos] == [("Tina", 5), ("Bia", 3)]   # nao reescreve
    assert any(a["tipo"] == "divergencia" for a in arm.estado.aprender)                 # so avisa no Aprender


def test_reply_em_conversa_qualquer_vale_com_confirmacao(tmp_path):
    # 28-29/09: "Clara 3", "5 ml" e "3" respondendo uma foto/conversa foram ignorados e o admin teve que lancar a mao
    arm, wa, m = ambiente(tmp_path)
    with arm as e:
        e.modo = "ao_vivo"

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="BAL D'AFRIQUE | BYREDO"), **PRISCILA, mid="post_bal"))
        await m.receber(_resp("Clara 3", "conversa", "gente que perfume lindo", "c1", nome="Clara"))
        await m.receber(_resp("5 ml", "foto", "", "s1", autor="9@s.whatsapp.net", nome="Selma"))
        await m.receber(_resp("3ml", "sobras", "💎DISPONÍVEIS💎", "e1", autor="10@s.whatsapp.net", nome="Enzo"))   # sobras: nao

        await m.receber(msg(POST.format(n="CEDAR CHIC | CAROLINA HERRERA"), **PRISCILA, mid="post_cedar"))
        antes = len(wa.enviadas)
        await m.receber(_resp("3", "conversa2", "kkkk", "l1", autor="11@s.whatsapp.net", nome="Leo"))   # 2 abertos: confirma
        return antes

    antes = asyncio.run(roda())
    bal = next(r for r in arm.estado.rateios if r.nome.startswith("BAL"))
    assert [(p.nome, p.ml) for p in bal.pedidos] == [("Clara", 3), ("Selma", 5)]
    assert sum(t.startswith("✅") for _, t, _ in wa.enviadas[:antes]) == 0   # um perfume so: sem confirmacao
    assert sum(t.startswith("✅") for _, t, _ in wa.enviadas[antes:]) == 1   # dois abertos + resposta sem relacao: confirma


def test_mensagem_longa_que_comeca_com_pedido_claro():
    from robo.interpretar import interpretar
    it = interpretar("Quero 10ml.\nMinha irmã amou, dei o meu decant pra ela e vou comprar outro pra mim.❤️")
    assert it["tipo"] == "pedido" and it["itens"][0]["ml"] == 10
    assert interpretar("Tanto é que virou frasco lacrado aqui kkkkkkk\nAPC seria pouco 🙈🙈🙈")["tipo"] != "apc"


@pytest.mark.regra_pausado
def test_divergencia_some_quando_a_lista_bate(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    from robo.post import ler_post
    from robo.rateio import novo_rateio
    with arm as e:
        e.rateios.append(novo_rateio(ler_post(POST.format(n="BAL D'AFRIQUE | BYREDO")), "post_bal"))

    async def roda():
        await m._tique()
        await m.receber(msg("5ml", autor="8@s.whatsapp.net", nome="Tina", citado="post_bal", mid="t1"))
        await m.receber(msg(POST.format(n="BAL D'AFRIQUE | BYREDO") + "\n\n💎5ml - Tina\n💎3ml - Ivo", **PRISCILA, mid="l1"))
        await m.receber(msg(POST.format(n="BAL D'AFRIQUE | BYREDO") + "\n\n💎5ml - Tina\n💎3ml - Ivo", **PRISCILA, mid="l2"))

    asyncio.run(roda())
    div = [a for a in arm.estado.aprender if a["tipo"] == "divergencia"]
    assert len(div) == 1 and div[0]["status"] == "pendente"
    with arm as e:
        r = e.rateios[0]
        from robo.rateio import Pedido
        r.pedidos.append(Pedido(None, None, r.aberto_em, "Ivo", 3))
        e.resolver_divergencias(r)
    assert arm.estado.aprender[0]["status"] == "resolvido"
