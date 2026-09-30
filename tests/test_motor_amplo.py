"""Motor em situacoes de erro e de borda: WhatsApp falhando, mensagens de outro chat, admin, apagar, modos."""

import asyncio
from datetime import timedelta

import pytest

from robo.estado import Abertura, Armazem
from robo.motor import Motor
from robo.texto import agora
from robo.whatsapp import Recebida
from tests.test_motor import GRUPO, WaFake, msg

POST = "✨ TESTE | X\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 10 ml: R$ 100,00 | APC\nQUANTIDADE DO FRASCO: {ml} ml"
ADMIN = dict(autor="9@s.whatsapp.net", nome="Admin", fone="5519999")


def ambiente(tmp_path, modo="ao_vivo"):
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins, e.config.avisar_admin = modo, GRUPO, ["5519999"], "5519999"
        e.config.segundos_ate_postar_lista = 0
        e.grupo_aberto = True
    wa = WaFake()
    return arm, wa, Motor(arm, wa)


class WaQuebrado(WaFake):
    """WhatsApp que falha em tudo que envia."""
    async def enviar_texto(self, *a, **k):
        raise RuntimeError("sem rede")

    async def reagir(self, *a, **k):
        raise RuntimeError("sem rede")

    async def abrir_grupo(self, g):
        raise RuntimeError("sem permissão")

    async def fechar_grupo(self, g):
        raise RuntimeError("sem permissão")


def roda(coro):
    return asyncio.run(coro)


def test_modo_desligado_ignora_tudo(tmp_path):
    arm, wa, m = ambiente(tmp_path, modo="desligado")

    async def t():
        await m.receber(msg(POST.format(ml=50), **ADMIN, mid="p"))
        await m.receber(msg("5ml", mid="x"))
        assert arm.estado.rateios == [] and wa.enviadas == []

    roda(t())


def test_ignora_outro_chat_privado_e_mensagem_propria(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def t():
        await m.receber(msg(POST.format(ml=50), **ADMIN, mid="p"))
        outro = msg("5ml", mid="a"); outro.chat = "999@g.us"
        priv = msg("5ml", mid="b"); priv.chat = "1@s.whatsapp.net"; priv.eh_grupo = False
        minha = msg("5ml", mid="c"); minha.de_mim = True
        for r in (outro, priv, minha):
            await m.receber(r)
        assert arm.estado.rateios[0].pedidos == []

    roda(t())


def test_admin_nao_vira_pedido_mas_post_dele_abre_e_atualiza(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def t():
        await m.receber(msg("5ml", **ADMIN, mid="a"))          # admin falando: nao e pedido
        assert arm.estado.rateios == []
        await m.receber(msg(POST.format(ml=50), **ADMIN, mid="p"))
        await m.receber(msg("5ml", mid="x1", nome="Ana"))
        await m.receber(msg(POST.format(ml=50) + "\n\n💎5ml - Ana\n💎10ml - Bia", **ADMIN, mid="p2"))
        r = arm.estado.rateios[0]
        assert [(p.ml, p.nome) for p in r.pedidos] == [(5, "Ana"), (10, "Bia")]
        assert r.pedidos[0].autor_id == "1@s.whatsapp.net" and "p2" in r.lista_msg_ids

    roda(t())


def test_mensagem_apagada_remove_e_reposta(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def t():
        await m.receber(msg(POST.format(ml=10), **ADMIN, mid="p"))
        await m.receber(msg("5ml", mid="x1"))
        await m.receber(msg("5ml", autor="2@s.whatsapp.net", nome="Bia", mid="x2"))
        assert arm.estado.rateios[0].status == "fechado"
        apagou = Recebida(msg_id="z", chat=GRUPO, autor="1@s.whatsapp.net", autor_fone=None, push_name="Ana", texto="",
                          citado_id=None, apagou_id="x1", eh_grupo=True, de_mim=False, tem_imagem=False)
        await m.receber(apagou)
        await asyncio.sleep(0.05)
        r = arm.estado.rateios[0]
        assert r.status == "aberto" and r.disponivel == 5 and [p.msg_id for p in r.pedidos] == ["x2"]
        assert any("Disponível 5 ml" in t for _, t, _ in wa.enviadas)

    roda(t())


def test_apagar_mensagem_que_nao_e_pedido_nao_faz_nada(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def t():
        await m.receber(msg(POST.format(ml=10), **ADMIN, mid="p"))
        apagou = Recebida(msg_id="z", chat=GRUPO, autor="1@s.whatsapp.net", autor_fone=None, push_name="A", texto="",
                          citado_id=None, apagou_id="nada", eh_grupo=True, de_mim=False, tem_imagem=False)
        await m.receber(apagou)
        assert arm.estado.rateios[0].pedidos == []   # so nao pode quebrar

    roda(t())


def test_whatsapp_fora_do_ar_nao_perde_o_pedido(tmp_path):
    arm, _, _ = ambiente(tmp_path)
    wa = WaQuebrado()
    m = Motor(arm, wa)

    async def t():
        await m.receber(msg(POST.format(ml=50), **ADMIN, mid="p"))
        await m.receber(msg("5ml", mid="x1"))           # reagir e lista falham ao enviar...
        await asyncio.sleep(0.05)
        r = Armazem(arm.caminho).estado.rateios[0]
        assert [p.ml for p in r.pedidos] == [5]        # ...mas o pedido ficou salvo em disco e nada quebrou

    roda(t())


def test_abrir_sem_ser_admin_nao_derruba_o_relogio(tmp_path):
    arm, _, _ = ambiente(tmp_path)
    wa = WaQuebrado()
    m = Motor(arm, wa)
    ag = agora()
    with arm as e:
        e.aberturas.append(Abertura(id="a", nome="X | Y", valor_ml=1, total_ml=10, minimo=3, tamanhos=[3], apc_ml=None,
                                    abre_em=(ag - timedelta(seconds=1)).isoformat(), fecha_em=(ag + timedelta(hours=1)).isoformat()))

    async def t():
        with pytest.raises(RuntimeError):
            await m._tique()
        # o relogio de verdade engole a excecao e tenta de novo no proximo tique
        m2 = Motor(arm, WaFake())
        await m2._tique()
        assert arm.estado.abertura("a").status == "aberta"

    roda(t())


def test_estado_corrompido_em_disco_nao_impede_de_subir(tmp_path):
    caminho = tmp_path / "estado.json"
    caminho.write_text("{isso nao e json", encoding="utf-8")
    arm = Armazem(caminho)
    assert arm.estado.modo == "desligado" and arm.estado.rateios == []
    assert (tmp_path / "estado.json.corrompido").exists()


def test_estado_roundtrip_completo(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def t():
        await m.receber(msg(POST.format(ml=50), **ADMIN, mid="p"))
        await m.receber(msg("5ml", mid="x1"))
        with arm as e:
            e.aberturas.append(Abertura(id="a", nome="X | Y", valor_ml=1, total_ml=10, minimo=3, tamanhos=[3], apc_ml=None,
                                        abre_em=agora().isoformat(), fecha_em=agora().isoformat(), aviso_em=agora().isoformat(), aviso_texto="oi"))
        de_novo = Armazem(arm.caminho).estado
        assert de_novo.rateios[0].pedidos[0].ml == 5 and de_novo.aberturas[0].aviso_texto == "oi"
        assert de_novo.config.admins == ["5519999"] and de_novo.log[0]["tipo"]

    roda(t())


def test_pedido_com_reply_vai_pro_rateio_certo_mesmo_com_varios(tmp_path):
    arm, wa, m = ambiente(tmp_path)

    async def t():
        await m.receber(msg(POST.format(ml=50).replace("TESTE | X", "VELHO | X"), **ADMIN, mid="p1"))
        await m.receber(msg(POST.format(ml=50).replace("TESTE | X", "NOVO | Y"), **ADMIN, mid="p2"))
        await m.receber(msg("5ml", mid="x1", citado="p1"))
        velho = next(r for r in arm.estado.rateios if r.nome.startswith("VELHO"))
        assert [p.ml for p in velho.pedidos] == [5]

    roda(t())


def test_modo_sombra_e_perguntar(tmp_path):
    arm, wa, m = ambiente(tmp_path, modo="sombra")
    with arm as e:
        e.config.sem_reply = "perguntar"

    async def t():
        await m.receber(msg(POST.format(ml=50).replace("TESTE | X", "A | X"), **ADMIN, mid="p1"))
        await m.receber(msg(POST.format(ml=50).replace("TESTE | X", "B | Y"), **ADMIN, mid="p2"))
        await m.receber(msg("5ml", mid="x1"))
        await asyncio.sleep(0.05)
        assert all(r.pedidos == [] for r in arm.estado.rateios)
        assert any("sem reply" in t for _, t, _ in wa.enviadas) and all(p.endswith("@s.whatsapp.net") for p, _, _ in wa.enviadas)

    roda(t())


def test_lista_junta_pedidos_em_uma_so(tmp_path):
    arm, wa, m = ambiente(tmp_path)
    with arm as e:
        e.config.segundos_ate_postar_lista = 0.1

    async def t():
        await m.receber(msg(POST.format(ml=50), **ADMIN, mid="p"))
        for i in range(5):
            await m.receber(msg("5ml", autor=f"{i}@s.whatsapp.net", nome=f"P{i}", mid=f"x{i}"))
        await asyncio.sleep(0.3)
        listas = [t for _, t, _ in wa.enviadas if "Disponível" in t]
        assert len(listas) == 1 and "Disponível 25 ml" in listas[0]

    roda(t())
