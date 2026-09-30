"""Padroes tirados do historico: fecha 1h antes, urgencia repetida, pedido solto vai pro mais recente."""

import asyncio
from datetime import datetime, timedelta

from robo.estado import Abertura, Armazem
from robo.motor import Motor
from robo.rateio import Pedido
from robo.texto import agora
from tests.test_motor import GRUPO, WaFake, msg

POST = "✨ {nome}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: {ml} ml"


def novo(tmp_path):
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins = "ao_vivo", GRUPO, ["5519999"]
        e.config.segundos_ate_postar_lista = 0
        e.grupo_aberto = True
    wa = WaFake()
    return arm, wa, Motor(arm, wa)


def test_fecha_grupo_uma_hora_antes(tmp_path):
    arm, wa, m = novo(tmp_path)
    ag = agora()
    with arm as e:
        e.aberturas.append(Abertura(id="a", nome="KIRKE | TIZIANA", valor_ml=1, total_ml=10, minimo=3, tamanhos=[3], apc_ml=None,
                                    abre_em=(ag + timedelta(minutes=50)).isoformat(), fecha_em=(ag + timedelta(hours=5)).isoformat()))

    async def roda():
        await m._tique()
        await m._tique()
        assert wa.anuncio == ["fechou"]
        assert sum("vamos fechar o grupo agora" in t for _, t, _ in wa.enviadas) == 1
        assert "às " + arm.estado.abertura("a").hora_curta in wa.enviadas[0][1]
        assert arm.estado.grupo_aberto is False

    asyncio.run(roda())


def test_pedido_solto_vai_pro_mais_recente(tmp_path):
    arm, wa, m = novo(tmp_path)

    async def roda():
        await m.receber(msg(POST.format(nome="VELHO | X", ml=50), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        await asyncio.sleep(0)
        await m.receber(msg(POST.format(nome="NOVO | Y", ml=50), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p2"))
        await m.receber(msg("5ml", mid="x1"))               # sem reply, sem dica
        await m.receber(msg("3ml velho", autor="2@s.whatsapp.net", nome="Bia", mid="x2"))  # dica pelo nome
        novo_r = next(r for r in arm.estado.rateios if r.nome.startswith("NOVO"))
        velho_r = next(r for r in arm.estado.rateios if r.nome.startswith("VELHO"))
        assert [p.ml for p in novo_r.pedidos] == [5] and [p.ml for p in velho_r.pedidos] == [3]

    asyncio.run(roda())


def test_urgencia_repete_e_para(tmp_path):
    arm, wa, m = novo(tmp_path)
    with arm as e:
        e.config.urgencia_a_cada_min = 30
        e.config.urgencia_max = 3

    async def roda():
        await m.receber(msg(POST.format(nome="ERBA | XERJOFF", ml=20), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        await m.receber(msg("10ml", mid="x1"))
        await asyncio.sleep(0.05)
        r = arm.estado.rateios[0]
        assert r.urgencias == 1 and "10 ml" in wa.enviadas[-1][1]
        await m._tique()                                   # ainda nao passou 30 min
        assert arm.estado.rateios[0].urgencias == 1
        with arm as e:
            e.rateios[0].ultima_urgencia_em = (agora() - timedelta(minutes=31)).isoformat()
        await m._tique()
        assert arm.estado.rateios[0].urgencias == 2 and "fecharmos o frasco" in wa.enviadas[-1][1]
        with arm as e:
            e.rateios[0].ultima_urgencia_em = (agora() - timedelta(minutes=31)).isoformat()
        await m._tique()
        with arm as e:
            e.rateios[0].ultima_urgencia_em = (agora() - timedelta(minutes=31)).isoformat()
        await m._tique()
        assert arm.estado.rateios[0].urgencias == 3          # respeita o maximo

    asyncio.run(roda())


def test_sobra_abaixo_do_minimo_nao_pede_arremate(tmp_path):
    arm, wa, m = novo(tmp_path)
    with arm as e:
        e.config.avisar_admin = "5519999"

    async def roda():
        await m.receber(msg(POST.format(nome="BYREDO | X", ml=12), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="p1"))
        await m.receber(msg("10ml", mid="x1"))            # sobram 2, minimo 3
        await asyncio.sleep(0.05)
        assert not any("arremata" in t for _, t, _ in wa.enviadas)
        assert any(para == "5519999@s.whatsapp.net" and "abaixo do mínimo" in t for para, t, _ in wa.enviadas)
        await m._tique()
        assert arm.estado.rateios[0].urgencias >= arm.estado.config.urgencia_max

    asyncio.run(roda())


def test_duas_aberturas_com_1h_de_diferenca(tmp_path):
    # caso real 28/09: Orience 17h e Argentina 18h. As 17h o Orience abre; o Argentina NAO pode fechar o grupo
    from robo.estado import Abertura
    from tests.test_motor import WaFake  # noqa: F401
    arm, wa, m = novo(tmp_path)
    ag = agora()

    def ab(i, nome, abre):
        return Abertura(id=i, nome=nome, valor_ml=23, total_ml=50, minimo=3, tamanhos=[3, 5, 10], apc_ml=None,
                        abre_em=abre.isoformat(), fecha_em=(abre + timedelta(days=1)).isoformat())

    with arm as e:
        e.grupo_aberto = True
        e.aberturas += [ab("arg", "ARGENTINA | MEMO PARIS", ag + timedelta(hours=2)), ab("ori", "ORIENCE | CHAMBRE 52", ag + timedelta(hours=1))]

    def em(minutos):   # desloca a agenda como se o relogio andasse
        with arm as e:
            for a in e.aberturas:
                a.abre_em = (datetime.fromisoformat(a.abre_em) - timedelta(minutes=minutos)).isoformat()

    async def roda():
        em(1)                      # 16h01: fecha pro Orience e posta os valores dele
        await m._tique()
        assert wa.anuncio == ["fechou"] and sum("Valor por ml" in t for _, t, _ in wa.enviadas) == 1
        em(59)                     # 17h00: Orience abre; Argentina (18h) nao fecha em cima
        await m._tique()
        await m._tique()
        assert wa.anuncio == ["fechou", "abriu"]
        assert not arm.estado.abertura("arg").fechou_antes
        assert not any("vamos fechar" in t and "ARGENTINA" in t for _, t, _ in wa.enviadas)
        em(60)                     # 18h00: Argentina so posta (grupo ja aberto, sem novo "GRUPO ABERTO")
        await m._tique()
        assert wa.anuncio == ["fechou", "abriu"]
        assert sum(t.startswith("GRUPO ABERTO") for _, t, _ in wa.enviadas) == 1
        assert sum("Valor por ml" in t for _, t, _ in wa.enviadas) == 2
        assert {r.nome for r in arm.estado.rateios_abertos()} == {"ORIENCE | CHAMBRE 52", "ARGENTINA | MEMO PARIS"}

    asyncio.run(roda())


def test_lista_sai_com_a_foto_do_perfume(tmp_path):
    from robo.estado import Abertura
    arm, wa, m = novo(tmp_path)
    ag = agora()
    with arm as e:
        e.config.segundos_ate_postar_lista = 0
        e.aberturas.append(Abertura(id="b", nome="BAL D'AFRIQUE | BYREDO", valor_ml=29, total_ml=100, minimo=3, tamanhos=[3, 5],
                                    apc_ml=None, abre_em=ag.isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat(),
                                    foto="data/fotos/bal.jpeg"))

    async def roda():
        await m.abrir_agora("b")
        rid = arm.estado.abertura("b").rateio_id
        await m.receber(msg("5ml", mid="p1"))
        await asyncio.sleep(0.05)
        await m.postar_lista(rid)

    asyncio.run(roda())
    assert wa.imagens.count("data/fotos/bal.jpeg") >= 2            # post + lista
    assert "5ml - Ana" in wa.enviadas[-1][1]


def test_perfume_que_acabou_de_abrir_vira_o_da_vez(tmp_path):
    # caso real 29/09 14:00: Cedar abriu, mas "Eu 5ml" foi pro Hundred (que seguia em destaque)
    from robo.estado import Abertura
    arm, wa, m = novo(tmp_path)
    ag = agora()
    with arm as e:
        e.config.segundos_ate_postar_lista = 0
        e.aberturas.append(Abertura(id="c", nome="CEDAR CHIC | CAROLINA HERRERA", valor_ml=20, total_ml=100, minimo=3,
                                    tamanhos=[3, 5], apc_ml=None, abre_em=(ag + timedelta(minutes=50)).isoformat(),
                                    fecha_em=(ag + timedelta(days=1)).isoformat()))

    async def roda():
        await m._tique()                                                           # fecha e posta o Cedar
        await m.receber(msg(POST.format(nome="HUNDRED SILENT WAYS | NISHANE", ml=100), autor="9@s.whatsapp.net",
                            nome="Admin", fone="5519999", mid="h1"))                  # admin fala do Hundred depois
        await asyncio.sleep(0.02)
        with arm as e:
            e.abertura("c").abre_em = (agora() - timedelta(seconds=1)).isoformat()
        await m._tique()                                                           # 14h: Cedar abre
        await m.receber(msg("Eu 5ml", mid="x1"))

    asyncio.run(roda())
    cedar = next(r for r in arm.estado.rateios if r.nome.startswith("CEDAR"))
    assert [p.ml for p in cedar.pedidos] == [5]


def test_durante_abertura_o_robo_nao_fala_de_outro_perfume(tmp_path):
    # caso real 30/09 11:00: "GRUPO ABERTO" + "somente 7 ml do Bal" no mesmo segundo -> pedidos novos foram pro Bal
    from robo.estado import Abertura
    from robo.rateio import Pedido
    arm, wa, m = novo(tmp_path)
    ag = agora()
    with arm as e:
        e.config.segundos_ate_postar_lista = 0
        e.aberturas.append(Abertura(id="n", nome="CANT GET ENOUGH | INITIO", valor_ml=20, total_ml=100, minimo=3, tamanhos=[3, 5],
                                    apc_ml=None, abre_em=(ag + timedelta(minutes=50)).isoformat(),
                                    fecha_em=(ag + timedelta(days=1)).isoformat()))

    async def roda():
        await m._tique()                                                              # fecha o grupo e posta o novo
        await m.receber(msg(POST.format(nome="BAL D'AFRIQUE | BYREDO", ml=100), autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="b0"))
        with arm as e:
            bal = next(r for r in e.rateios if r.nome.startswith("BAL"))
            bal.aberto_em = (agora() - timedelta(days=1)).isoformat()
            bal.pedidos.append(Pedido("x@s.whatsapp.net", "b1", bal.aberto_em, "Alguem", 93))   # sobram 7 ml
            e.abertura("n").abre_em = (agora() - timedelta(seconds=1)).isoformat()
        await m._tique()                                                              # 11:00 abre
        await m._tique()
        await m.receber(msg("5", mid="d1", autor="5@s.whatsapp.net", nome="Dalva"))
        await m.receber(msg("10ml Pvf", mid="l1", autor="6@s.whatsapp.net", nome="Livia"))
        await asyncio.sleep(0.05)

    asyncio.run(roda())
    textos = [t for _, t, _ in wa.enviadas]
    assert not any("7 ml" in t and "BAL" in t for t in textos)                       # nada de urgencia do Bal na abertura
    novo_r = next(r for r in arm.estado.rateios if r.nome.startswith("CANT"))
    assert [(p.nome, p.ml) for p in novo_r.pedidos] == [("Dalva", 5), ("Livia", 10)]
    assert not any("Restam só" in t for t in textos)


def test_regras_saem_10_min_antes_e_repetem_sem_spam(tmp_path):
    from robo.estado import Abertura
    arm, wa, m = novo(tmp_path)
    ag = agora()
    with arm as e:
        e.config.segundos_ate_postar_lista = 0
        e.config.regras_horario = "00:00-23:59"
        e.aberturas.append(Abertura(id="r", nome="X | Y", valor_ml=10, total_ml=50, minimo=3, tamanhos=[3, 5], apc_ml=None,
                                    abre_em=(ag + timedelta(minutes=9)).isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat()))

    def regras():
        return sum("COMO FUNCIONA O NOSSO GRUPO" in t for _, t, _ in wa.enviadas)

    async def roda():
        await m._tique()                                       # 9 min antes: regras saem (1)
        assert regras() == 1
        await m._tique()                                       # nao repete
        assert regras() == 1
        with arm as e:
            e.abertura("r").abre_em = (agora() - timedelta(seconds=1)).isoformat()
        await m._tique()                                       # abre
        await m.receber(msg("5ml", mid="p1"))
        await asyncio.sleep(0.05)
        await m._tique()                                       # menos de 4 h desde a ultima: nao repete
        assert regras() == 1
        with arm as e:
            e.regras_enviadas_em = (agora() - timedelta(hours=5)).isoformat()
        await m._tique()                                       # 5 h depois, com pedido novo: repete (2)
        assert regras() == 2
        with arm as e:
            e.regras_enviadas_em = (agora() - timedelta(hours=5)).isoformat()
            for r in e.rateios:
                for p in r.pedidos:
                    p.em = (agora() - timedelta(hours=6)).isoformat()   # nenhum pedido depois da ultima vez
        await m._tique()                                       # sem pedido novo desde entao: nao repete
        assert regras() == 2

    asyncio.run(roda())


def test_regras_vazias_nao_mandam_nada(tmp_path):
    from robo.estado import Abertura
    arm, wa, m = novo(tmp_path)
    ag = agora()
    with arm as e:
        e.config.regras_texto = ""
        e.aberturas.append(Abertura(id="r", nome="X | Y", valor_ml=10, total_ml=50, minimo=3, tamanhos=[3], apc_ml=None,
                                    abre_em=(ag + timedelta(minutes=5)).isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat()))
    asyncio.run(m._tique())
    assert not any("COMO FUNCIONA" in t for _, t, _ in wa.enviadas)
