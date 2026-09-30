"""Modo Observando (rodar no Grupo 1 sem mandar nada), admins lidos do grupo e aba Aprender."""

import asyncio
import io
from datetime import timedelta

from robo.estado import Abertura, Armazem
from robo.motor import Motor
from robo.texto import agora
from tests.test_motor import GRUPO, WaFake, msg
from tests.test_painel import PNG, cli  # noqa: F401  (fixture)

POST = "✨ {n}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 20 ml: R$ 200,00 | APC\nQUANTIDADE DO FRASCO: 30 ml"


class WaComAdmins(WaFake):
    def __init__(self, admins):
        super().__init__()
        self._admins = admins

    async def admins_do_grupo(self, g):
        return set(self._admins)


def ambiente(tmp_path, admins=("111222333@lid", "111222333")):
    arm = Armazem(tmp_path / "e.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.avisar_admin = "observando", GRUPO, "5519999"
        e.config.segundos_ate_postar_lista = 0
        e.config.chamada_silencio_min = 1
        e.grupo_aberto = True
    wa = WaComAdmins(admins)
    return arm, wa, Motor(arm, wa)


ADMIN_REAL = dict(autor="111222333@lid", nome="Bruno")   # admin do grupo, sem estar cadastrado no painel


def test_observando_nao_manda_nada_pra_ninguem(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    ag = agora()
    with arm as e:
        e.aberturas.append(Abertura(id="a", nome="X | Y", valor_ml=1, total_ml=10, minimo=3, tamanhos=[3], apc_ml=None,
                                    abre_em=(ag - timedelta(minutes=1)).isoformat(), fecha_em=ag.isoformat(),
                                    aviso_em=(ag - timedelta(minutes=2)).isoformat(), aviso_texto="oi"))

    async def roda():
        await m._tique()                                                   # le admins; nao abre nada
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA"), **ADMIN_REAL, mid="p1"))
        await m.receber(msg("5ml", mid="x1"))
        await m.receber(msg("30ml", autor="2@s.whatsapp.net", nome="Bia", mid="x2"))   # passa do disponivel
        await m.receber(msg("eu quero", autor="3@s.whatsapp.net", nome="Cris", mid="x3"))  # duvida
        await m.receber(msg("20ml", autor="4@s.whatsapp.net", nome="Dani", mid="x4"))  # sobra 5 -> urgencia
        await asyncio.sleep(0.05)
        with arm as e:
            e.rateios[0].aberto_em = (agora() - timedelta(hours=2)).isoformat()
            for p in e.rateios[0].pedidos:
                p.em = e.rateios[0].aberto_em
        await m._tique()
        await asyncio.sleep(0.05)

    asyncio.run(roda())
    assert wa.enviadas == [] and wa.reacoes == [] and wa.anuncio == []   # NADA saiu
    r = arm.estado.rateios[0]
    assert [(p.ml, p.nome) for p in r.pedidos] == [(5, "Ana"), (20, "Dani")]   # mas anotou tudo
    assert arm.estado.abertura("a").status == "agendada"                          # nem mexeu na agenda


def test_admin_do_grupo_reconhecido_sem_cadastro(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA"), **ADMIN_REAL, mid="p1"))
        await m.receber(msg("bom dia, 5ml pra mim tambem", **ADMIN_REAL, mid="p2"))   # conversa de admin nao vira pedido

    asyncio.run(roda())
    assert len(arm.estado.rateios) == 1 and arm.estado.rateios[0].pedidos == []


def test_divergencia_com_a_lista_do_admin_vai_pro_aprender(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA"), **ADMIN_REAL, mid="p1"))
        await m.receber(msg("5ml", mid="x1"))
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA") + "\n\n💎5ml - Ana\n💎3ml - Bia", **ADMIN_REAL, mid="p2"))
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA") + "\n\n💎5ml - Ana\n💎3ml - Bia", **ADMIN_REAL, mid="p3"))

    asyncio.run(roda())
    div = [a for a in arm.estado.aprender if a["tipo"] == "divergencia"]
    assert len(div) == 1                                      # a segunda lista ja bate: nao repete
    assert div[0]["robo"] == ["5 Ana"] and div[0]["admin"] == ["3 Bia", "5 Ana"]


def test_duvida_vai_pro_aprender(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA"), **ADMIN_REAL, mid="p1"))
        await m.receber(msg("eu quero", mid="x1"))

    asyncio.run(roda())
    a = arm.estado.aprender[0]
    assert a["tipo"] == "duvida" and a["texto"] == "eu quero" and a["abertos"] == ["KIRKE | TIZIANA"]


def test_aba_aprender_marca_e_grava_exemplo(cli):
    with cli.arm as e:
        item = e.para_aprender("duvida", "me separa cinco daquele", autor="Ana", motivo="quero sem quantidade", abertos=["KIRKE"])
    html = cli.get("/aprender").text
    assert "me separa cinco daquele" in html and "Era pedido" in html
    r = cli.post(f"/aprender/{item['id']}", data={"rotulo": "pedido", "ml": "5", "perfume": "KIRKE"})
    assert r.status_code == 303
    a = cli.arm.estado.aprender[0]
    assert a["status"] == "revisado" and a["rotulo"] == "pedido 5 ml KIRKE"
    import json
    linha = json.loads(open("data/exemplos.jsonl", encoding="utf-8").read().splitlines()[-1])
    assert linha["texto"] == "me separa cinco daquele" and linha["ml"] == 5 and linha["perfume"] == "KIRKE"
    assert "Nada pendente" in cli.get("/aprender").text
    assert "pedido 5 ml KIRKE" in cli.get("/aprender?ver=revisados").text


def test_correcao_manual_vira_item(cli):
    from robo.post import ler_post
    from robo.rateio import novo_rateio
    r = novo_rateio(ler_post(POST.format(n="X | Y")), None)
    with cli.arm as e:
        e.rateios.append(r)
    cli.post(f"/rateio/{r.id}/add", data={"ml": "5", "nome": "Bruno"})
    cli.post(f"/rateio/{r.id}/remover", data={"i": "0"})
    tipos = [a["texto"] for a in cli.arm.estado.aprender if a["tipo"] == "correcao"]
    assert tipos == ["Removido 5 ml de Bruno no X | Y", "Adicionado 5 ml de Bruno no X | Y"]


def test_modo_observando_no_painel(cli):
    cli.post("/modo", data={"modo": "observando"})
    assert cli.arm.estado.modo == "observando" and "Observando" in cli.get("/").text


def test_pausado_nao_anota_nem_responde(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    with arm as e:
        e.modo = "ao_vivo"

    async def roda():
        await m._tique()
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA"), **ADMIN_REAL, mid="p1"))
        with arm as e:
            e.rateios[0].status = "pausado"
        antes = len(wa.enviadas)
        await m.receber(msg("5ml", citado="p1", mid="x1"))
        await m.receber(msg("5ml", mid="x2"))
        await m.receber(msg("quero 5ml do kirke", mid="x3"))
        return antes

    antes = asyncio.run(roda())
    assert arm.estado.rateios[0].pedidos == [] and len(wa.enviadas) == antes and wa.reacoes == []


def test_abertura_vencida_nao_abre(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    ag = agora()
    with arm as e:
        e.modo = "ao_vivo"
        e.aberturas.append(Abertura(id="v", nome="IMPADIA | BDK", valor_ml=1, total_ml=10, minimo=3, tamanhos=[3], apc_ml=None,
                                    abre_em=(ag - timedelta(days=2)).isoformat(), fecha_em=(ag - timedelta(days=1)).isoformat()))
    asyncio.run(m._tique())
    assert arm.estado.abertura("v").status == "cancelada" and wa.enviadas == [] and wa.anuncio == []


def test_estado_do_grupo_vem_do_whatsapp(tmp_path):
    # caso real 26-28/09: robo desligado depois de fechar o grupo, admin reabriu pelo celular;
    # o painel ficou achando "fechado" e o "fechar 1h antes" da proxima abertura nao dispararia
    arm, wa, m = ambiente(tmp_path)
    with arm as e:
        e.grupo_aberto = False
    wa.anuncio.append("abriu")
    asyncio.run(m._tique())
    assert arm.estado.grupo_aberto is True
