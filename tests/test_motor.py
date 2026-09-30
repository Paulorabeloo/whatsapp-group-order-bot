"""Roda o motor inteiro com um WhatsApp de mentira: abertura agendada → contagem → abre → pedidos → esgota → fecha."""

import asyncio
from datetime import timedelta

import pytest

from robo.estado import Abertura, Armazem
from robo.motor import Motor
from robo.rateio import Pedido
from robo.texto import agora
from robo.whatsapp import Recebida

GRUPO = "123@g.us"


class WaFake:
    def __init__(self):
        self.enviadas, self.reacoes, self.anuncio, self.imagens = [], [], [], []
        self.conectado, self.meu_jid, self.qr_svg = True, "5519@s.whatsapp.net", None
        self._n = 0

    async def enviar_texto(self, para, texto, mencoes=None):
        self._n += 1
        self.enviadas.append((para, texto, mencoes))
        return f"env{self._n}"

    async def enviar_imagem(self, para, arquivo, legenda, mencoes=None):
        self.imagens.append(arquivo)
        return await self.enviar_texto(para, legenda, mencoes)

    async def reagir(self, chat, autor, msg_id, emoji="👍"):
        self.reacoes.append(msg_id)
        self.emojis = getattr(self, "emojis", []) + [emoji]

    async def fechar_grupo(self, g):
        self.anuncio.append("fechou")

    async def abrir_grupo(self, g):
        self.anuncio.append("abriu")

    async def grupo_por_nome(self, nome):
        return GRUPO

    async def grupo_esta_aberto(self, g):
        if not self.anuncio:   # o fake so sabe o estado depois que alguem abriu/fechou
            raise RuntimeError("estado do grupo desconhecido")
        return self.anuncio[-1] == "abriu"


def msg(texto, autor="1@s.whatsapp.net", nome="Ana", citado=None, mid=None, fone=None):
    return Recebida(msg_id=mid or f"m{abs(hash((autor, texto)))}", chat=GRUPO, autor=autor, autor_fone=fone, push_name=nome,
                    texto=texto, citado_id=citado, apagou_id=None, eh_grupo=True, de_mim=False, tem_imagem=False)


@pytest.fixture
def ambiente(tmp_path):
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.modo = "ao_vivo"
        e.config.grupo_jid = GRUPO
        e.config.admins = ["5519999"]
        e.config.avisar_admin = "5519999"
        e.config.segundos_ate_postar_lista = 0
    wa = WaFake()
    return arm, wa, Motor(arm, wa)


def test_abertura_agendada_ate_fechar(ambiente):
    arm, wa, m = ambiente
    ag = agora()
    ab = Abertura(id="a1", nome="FRENCH LEATHER | MEMO PARIS", valor_ml=24, total_ml=10, minimo=3, tamanhos=[3, 5, 10],
                  apc_ml=None, abre_em=(ag + timedelta(minutes=4)).isoformat(), fecha_em=(ag + timedelta(hours=4)).isoformat())
    with arm as e:
        e.aberturas.append(ab)

    async def roda():
        await m._tique()                                   # 4 min antes: fecha, posta os valores, contagem de 5 min
        assert any("5 min" in t for _, t, _ in wa.enviadas)
        assert wa.anuncio[-1] == "fechou" and any("Valor por ml: R$ 24,00" in t for _, t, _ in wa.enviadas)
        with arm as e:
            e.abertura("a1").abre_em = (agora() - timedelta(seconds=1)).isoformat()
        antes = len(wa.enviadas)
        await m._tique()                                   # hora de abrir: so abre, nao repete o post
        assert wa.anuncio[-1] == "abriu" and [t for _, t, _ in wa.enviadas[antes:]] == ["GRUPO ABERTO 🥂"]
        assert len(arm.estado.rateios) == 1
        rat = arm.estado.rateios[0]
        assert rat.post_msg_id == wa.enviadas[-1][0 + 1] or rat.post_msg_id.startswith("env")

        await m.receber(msg("5ml", citado=rat.post_msg_id, mid="p1"))
        await m.receber(msg("3 ml", autor="2@s.whatsapp.net", nome="Bia", citado=rat.post_msg_id, mid="p2"))
        await asyncio.sleep(0.05)
        assert wa.reacoes == ["p1", "p2"]
        lista, aviso = wa.enviadas[-2][1], wa.enviadas[-1][1]
        assert "💎 5ml - Ana" in lista and "💎 3ml - Bia" in lista and "Disponível 2 ml" in lista
        assert "abaixo do mínimo" in aviso   # sobra 2 < minimo 3: sem "quem arremata", so avisa o admin

        await m.receber(msg("5ml", autor="3@s.whatsapp.net", nome="Cris", citado=rat.post_msg_id, mid="p3"))
        assert "Restam só 2 ml" in wa.enviadas[-1][1]

        # esgota via painel (pedido do privado) e fecha o frasco + grupo
        with arm as e:
            e.rateio(rat.id).pedidos.append(Pedido(None, None, ag.isoformat(), "Dani", 2))
        await m.fechar_rateio(rat.id)
        assert "FRASCO FECHADO" in wa.enviadas[-1][1]
        assert wa.anuncio[-1] == "abriu"          # frasco fechado NAO fecha o grupo; so 1h antes da proxima abertura
        assert arm.estado.abertura("a1").status == "encerrada"

    asyncio.run(roda())


def test_modo_sombra_nao_posta_no_grupo(ambiente):
    arm, wa, m = ambiente
    with arm as e:
        e.modo = "sombra"
    post = "✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 50 ml"

    async def roda():
        await m.receber(msg(post, autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="post"))
        await m.receber(msg("5ml", citado="post", mid="p1"))
        await asyncio.sleep(0.05)
        assert wa.reacoes == []
        assert all(para == "5519999@s.whatsapp.net" for para, _, _ in wa.enviadas)
        assert "💎 5ml - Ana" in wa.enviadas[-1][1]

    asyncio.run(roda())


def test_duvida_vai_pro_admin(ambiente):
    arm, wa, m = ambiente
    post = "✨ X | Y\nValor por ml: R$ 10,00\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 50 ml"

    async def roda():
        await m.receber(msg(post, autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="post"))
        await m.receber(msg("eu quero", mid="d1"))
        assert wa.enviadas[-1][0] == "5519999@s.whatsapp.net" and "Não entendi" in wa.enviadas[-1][1]

    asyncio.run(roda())


def test_frasco_fechado_nao_duplica_lista(tmp_path):
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins = "ao_vivo", GRUPO, ["5519999"]
        e.config.segundos_ate_postar_lista = 0.05
    wa = WaFake()
    m = Motor(arm, wa)
    post = "✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 10 ml"

    async def roda():
        await m.receber(msg(post, autor="9@s.whatsapp.net", nome="Admin", fone="5519999", mid="post"))
        await m.receber(msg("5ml", mid="p1"))                                   # agenda lista em 50 ms
        await m.receber(msg("5ml", autor="2@s.whatsapp.net", nome="Bia", mid="p2"))  # fecha o frasco: lista na hora
        await asyncio.sleep(0.2)
        listas = [t for _, t, _ in wa.enviadas if "FRASCO FECHADO" in t]
        assert len(listas) == 1

    asyncio.run(roda())


def test_segunda_abertura_com_grupo_ja_aberto_nao_repete_grupo_aberto(tmp_path):
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.modo, e.config.grupo_jid = "ao_vivo", GRUPO
    wa = WaFake()
    m = Motor(arm, wa)
    ag = agora()
    for i in (1, 2):
        with arm as e:
            e.aberturas.append(Abertura(id=f"a{i}", nome=f"P{i} | X", valor_ml=10, total_ml=20, minimo=3, tamanhos=[3, 5], apc_ml=None,
                                        abre_em=ag.isoformat(), fecha_em=(ag + timedelta(hours=1)).isoformat()))

    async def roda():
        await m.abrir_agora("a1")
        await m.abrir_agora("a2")
        assert sum("GRUPO ABERTO" in t for _, t, _ in wa.enviadas) == 1
        assert wa.anuncio == ["abriu"]
        assert sum("QUANTIDADE DO FRASCO" in t for _, t, _ in wa.enviadas) == 2   # os dois posts sairam

    asyncio.run(roda())
