"""Varios perfumes abertos ao mesmo tempo (o normal no grupo): cada pedido vai pro perfume certo."""

import asyncio

from robo.estado import Armazem
from robo.motor import Motor
from tests.test_motor import GRUPO, WaFake, msg

POST = "✨ {n}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 20 ml: R$ 200,00 | APC\nQUANTIDADE DO FRASCO: 50 ml"
ADMIN = dict(autor="9@s.whatsapp.net", nome="Admin", fone="5519999")
ANA = dict(autor="1@s.whatsapp.net", nome="Ana")


def cenario(tmp_path):
    """Abertos, do mais antigo ao mais novo: Kirke, Torino, Chicelle."""
    arm = Armazem(tmp_path / "e.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins, e.config.avisar_admin = "ao_vivo", GRUPO, ["5519999"], "5519999"
        e.config.segundos_ate_postar_lista = 0
        e.grupo_aberto = True
    wa = WaFake()
    m = Motor(arm, wa)

    async def prepara():
        for i, n in enumerate(["KIRKE | TIZIANA TERENZI", "TORINO 21 | XERJOFF", "CHICELLE | UNIQUE"]):
            await m.receber(msg(POST.format(n=n), **ADMIN, mid=f"p{i}"))
            await asyncio.sleep(0.01)

    asyncio.run(prepara())
    return arm, wa, m


def ml(arm, prefixo):
    r = next(x for x in arm.estado.rateios if x.nome.startswith(prefixo))
    return [(p.ml, p.apc) for p in r.pedidos]


def manda(m, texto, mid, **quem):
    asyncio.run(m.receber(msg(texto, mid=mid, **(quem or ANA))))


def test_solto_vai_pro_mais_recente(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "5ml", "x1")
    assert ml(arm, "CHICELLE") == [(5, False)] and ml(arm, "KIRKE") == [] and ml(arm, "TORINO") == []


def test_pelo_nome_vai_pro_certo_e_vira_o_da_vez(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "3ml do kirke", "x1")
    manda(m, "5ml", "x2", autor="2@s.whatsapp.net", nome="Bia")
    assert ml(arm, "KIRKE") == [(3, False), (5, False)] and ml(arm, "CHICELLE") == []


def test_admin_falando_do_perfume_muda_o_da_vez(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "@all Só 7ml do Torino, quem arremata?", "a1", **ADMIN)
    manda(m, "5ml", "x1")
    assert ml(arm, "TORINO") == [(5, False)] and ml(arm, "CHICELLE") == []


def test_dois_perfumes_na_mesma_mensagem(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "5 ml do Torino e 3 ml do Kirke", "x1")
    assert ml(arm, "TORINO") == [(5, False)] and ml(arm, "KIRKE") == [(3, False)] and ml(arm, "CHICELLE") == []
    assert len([r for r in wa.reacoes if r == "x1"]) == 1          # um 👍 so


def test_altera_e_desisto_valem_onde_a_pessoa_pediu(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "3ml do kirke", "x1")
    manda(m, "5ml do chicelle", "x2", autor="2@s.whatsapp.net", nome="Bia")   # Chicelle vira o da vez
    manda(m, "altera pra 10ml", "x3")                                        # Ana so tem pedido no Kirke
    assert ml(arm, "KIRKE") == [(10, False)] and ml(arm, "CHICELLE") == [(5, False)]
    manda(m, "desisto", "x4")
    assert ml(arm, "KIRKE") == [] and ml(arm, "CHICELLE") == [(5, False)]


def test_desisto_sem_pedido_nao_faz_nada(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "desisto", "x1")
    assert all(r.pedidos == [] for r in arm.estado.rateios)


def test_apc_solto_e_do_da_vez_apc_com_nome_e_do_certo(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "apc", "x1")
    manda(m, "quero o apc do torino", "x2", autor="2@s.whatsapp.net", nome="Bia")
    assert ml(arm, "CHICELLE") == [(20, True)] and ml(arm, "TORINO") == [(20, True)]


def test_apc_solto_pula_perfume_sem_apc(tmp_path):
    arm, wa, m = cenario(tmp_path)
    with arm as e:
        next(r for r in e.rateios if r.nome.startswith("CHICELLE")).apc_ml = None      # o da vez nao tem APC
    manda(m, "apc", "x1")
    assert ml(arm, "TORINO") == [(20, True)] and ml(arm, "CHICELLE") == []


def test_apc_solto_sem_nenhum_apc_livre_avisa(tmp_path):
    arm, wa, m = cenario(tmp_path)
    with arm as e:
        for r in e.rateios:
            r.apc_ml = None
    asyncio.run(m.receber(__import__("tests.test_motor", fromlist=["msg"]).msg("apc", mid="x1", **ANA)))
    assert "Nenhum APC disponível" in wa.enviadas[-1][1]


def test_lista_do_robo_nao_muda_o_da_vez(tmp_path):
    arm, wa, m = cenario(tmp_path)
    from tests.test_motor import msg

    async def roda():
        await m.receber(msg("3ml do kirke", mid="x1", **ANA))     # Kirke vira o da vez
        await m.receber(msg("5ml do torino", autor="2@s.whatsapp.net", nome="Bia", mid="x2"))   # Torino vira o da vez
        await asyncio.sleep(0.05)                                  # listas do Kirke e do Torino saem
        await m.postar_lista(next(r.id for r in arm.estado.rateios if r.nome.startswith("KIRKE")))  # Kirke por ultimo
        await m.receber(msg("5ml", autor="3@s.whatsapp.net", nome="Cris", mid="x3"))

    asyncio.run(roda())
    assert ml(arm, "TORINO") == [(5, False), (5, False)]          # continua o Torino, mesmo com a lista do Kirke saindo depois


WAGNER = dict(autor="9@s.whatsapp.net", nome="Sofia")


def test_dono_do_apc_soma_com_mais(tmp_path):
    # caso real 29/09: Sofia (APC do Bal) respondeu o post com "30 +10ml" -> APC passa a 40, sem linha nova
    arm, wa, m = cenario(tmp_path)
    manda(m, "apc", "s1", citado="p2", **WAGNER)
    manda(m, "20 +10ml", "s2", citado="p2", **WAGNER)
    assert ml(arm, "CHICELLE") == [(30, True)]


def test_dono_do_apc_com_igual(tmp_path):
    # caso real 29/09: Flavia "O meu vai ser APC de 35+5=40 ml" (aqui o APC e 20)
    arm, wa, m = cenario(tmp_path)
    manda(m, "apc", "r1", citado="p1", **WAGNER)
    antes = len(wa.enviadas)
    manda(m, "O meu vai ser APC de 20+5=25 ml", "r2", **WAGNER)
    assert ml(arm, "TORINO") == [(25, True)]
    assert not any("Nenhum APC" in t for _, t, _ in wa.enviadas[antes:])


def test_dono_do_apc_pedindo_mais_ml_soma_na_linha_do_apc(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "apc", "s1", citado="p2", **WAGNER)
    manda(m, "5ml", "s2", citado="p2", **WAGNER)
    manda(m, "5ml", "a1", citado="p2")                      # outra pessoa: linha propria
    assert ml(arm, "CHICELLE") == [(25, True), (5, False)]


def test_mais_de_quem_nao_tem_apc_segue_normal(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "5 +5ml", "a1", citado="p2")
    assert all(not apc for _, apc in ml(arm, "CHICELLE"))


def test_lista_mostra_o_apc_com_os_ml_de_verdade(tmp_path):
    # caso real 29/09: APC da Sofia virou 40 ml, mas a lista seguia escrevendo "APC + 30 ml"
    from robo.rateio import renderizar
    arm, wa, m = cenario(tmp_path)
    manda(m, "apc", "s1", citado="p2", **WAGNER)
    manda(m, "20 +10ml", "s2", citado="p2", **WAGNER)
    r = next(x for x in arm.estado.rateios if x.nome.startswith("CHICELLE"))
    assert "Sofia | APC + 30 ml" in renderizar(r)[0]


NADIA = dict(autor="7@s.whatsapp.net", nome="Nadia Beatriz")
BARBARA = dict(autor="6@s.whatsapp.net", nome="Bruna")


def test_o_meu_e_so_3ml_deixa_um_pedido_de_3(tmp_path):
    # caso real 29/09 14:06: "O meu aqui é só 3ml tira o de 5ml desse por favor"
    arm, wa, m = cenario(tmp_path)
    manda(m, "3ml", "m1", citado="p0", **NADIA)
    manda(m, "5ml", "m2", citado="p0", **NADIA)
    antes = len(wa.enviadas)
    manda(m, "O meu aqui é só 3ml tira o de 5ml desse por favor", "m3", citado="p0", **NADIA)
    assert ml(arm, "KIRKE") == [(3, False)]
    assert not any("Restam" in t for _, t, _ in wa.enviadas[antes:])


def test_mais_2ml_e_pra_ficar_5ml_ajustam_o_pedido(tmp_path):
    # caso real 29/09 14:07: Bruna "eu quero mais 2 ml dele pode ser?" / "pra ficar 5ml"
    arm, wa, m = cenario(tmp_path)
    manda(m, "3ml", "b1", citado="p1", **BARBARA)
    manda(m, "eu quero mais 2 ml dele pode ser?", "b2", citado="p1", **BARBARA)
    assert ml(arm, "TORINO") == [(5, False)]
    manda(m, "pra ficar 10ml", "b3", citado="p1", **BARBARA)
    assert ml(arm, "TORINO") == [(10, False)]


def test_ajuste_sem_reply_vale_pro_perfume_em_destaque(tmp_path):
    arm, wa, m = cenario(tmp_path)
    import time
    manda(m, "5ml", "b1", citado="p2", **BARBARA)          # Chicelle
    time.sleep(0.02)
    manda(m, "3ml", "b2", citado="p0", **BARBARA)          # Kirke vira o da vez
    manda(m, "pra ficar 5ml", "b3", **BARBARA)
    assert ml(arm, "KIRKE") == [(5, False)] and ml(arm, "CHICELLE") == [(5, False)]


def test_apelido_curto_do_perfume(tmp_path):
    # 29/09: "3ml bal" nao era reconhecido como BAL D'AFRIQUE (so palavras de 4+ letras contavam)
    from robo.post import ler_post
    from robo.rateio import escolher_rateio, novo_rateio
    P = "✨ {n}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 100 ml"
    rs = [novo_rateio(ler_post(P.format(n=n)), None) for n in ["HUNDRED SILENT WAYS | NISHANE", "BAL D’AFRIQUE | BYREDO", "ANI | NISHANE"]]
    assert escolher_rateio(rs, dica="bal").nome.startswith("BAL")
    assert escolher_rateio(rs, dica="ani").nome.startswith("ANI")
    assert escolher_rateio(rs, dica="for the win") is None


def test_fica_5ml_confirma_e_nao_duplica(tmp_path):
    # caso real 29/09 14:16: Bruna (ja com 5ml) "Obrigada. Fica 5ml do nishane pra mim" virou linha nova "Fica 5ml"
    from robo.interpretar import interpretar
    it = interpretar("Obrigada. Fica 5ml do nishane pra mim")
    assert it["tipo"] == "alterar" and it["ml"] == 5 and it.get("total")
    arm, wa, m = cenario(tmp_path)
    manda(m, "5ml", "b1", citado="p1", **BARBARA)
    manda(m, "Obrigada. Fica 5ml do torino pra mim", "b2", **BARBARA)
    assert ml(arm, "TORINO") == [(5, False)]


def test_pedido_chutado_confirma_no_grupo(tmp_path):
    # 29/09: "Eu 5ml" foi pro perfume errado e ninguem percebeu ate a lista final
    arm, wa, m = cenario(tmp_path)
    antes = len(wa.enviadas)
    manda(m, "5ml", "a1")                                     # sem reply, sem nome: robo escolhe
    conf = [t for _, t, _ in wa.enviadas[antes:] if t.startswith("✅")]
    assert len(conf) == 1 and "anotado no CHICELLE" in conf[0]
    antes = len(wa.enviadas)
    manda(m, "5ml", "a2", citado="p0")                        # respondeu o post: sem confirmacao
    manda(m, "3ml do torino", "a3")                           # citou o nome: sem confirmacao
    assert not any(t.startswith("✅") for _, t, _ in wa.enviadas[antes:])


def _envelhece(arm, prefixo, horas):
    from datetime import timedelta
    from robo.texto import agora
    velho = (agora() - timedelta(hours=horas)).isoformat()
    with arm as e:
        for r in e.rateios:
            if r.nome.startswith(prefixo):
                r.aberto_em, r.destaque_em = velho, None
                for p in r.pedidos:
                    p.em = velho


def test_nao_confirma_quando_so_um_perfume_esta_movimentado(tmp_path):
    # caso real 29/09 18:00: "Apc" logo apos abrir o Damask; o Bal estava parado desde cedo -> sem duvida
    arm, wa, m = cenario(tmp_path)
    _envelhece(arm, "KIRKE", 5)
    _envelhece(arm, "TORINO", 5)
    antes = len(wa.enviadas)
    manda(m, "5ml", "a1")
    manda(m, "apc", "a2", autor="8@s.whatsapp.net", nome="Telma")
    assert ml(arm, "CHICELLE") == [(5, False), (20, True)]
    assert not any(t.startswith("✅") for _, t, _ in wa.enviadas[antes:])


def test_apc_so_tem_um_livre_nao_confirma(tmp_path):
    arm, wa, m = cenario(tmp_path)
    manda(m, "apc", "s1", citado="p0", autor="7@s.whatsapp.net", nome="Sofia")   # APC do Kirke tomado
    manda(m, "apc", "s2", citado="p1", autor="6@s.whatsapp.net", nome="Rosa")     # APC do Torino tomado
    antes = len(wa.enviadas)
    manda(m, "apc", "f1", autor="8@s.whatsapp.net", nome="Telma")                   # so o Chicelle tem APC livre
    assert ml(arm, "CHICELLE") == [(20, True)]
    assert not any(t.startswith("✅") for _, t, _ in wa.enviadas[antes:])
