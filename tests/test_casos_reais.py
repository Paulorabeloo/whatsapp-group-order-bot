"""Casos reais do grupo, escritos do jeito que aconteceram. Cada um virou teste antes da correção.

Os ajudantes deixam o teste legível como uma conversa: manda(texto, respondendo=POST, quem=PESSOA),
pedidos("KIRKE") e mensagens_no_grupo(). Nomes de clientes são fictícios.
"""

import asyncio

import pytest

from robo.estado import Armazem
from robo.motor import Motor
from tests.test_motor import GRUPO, WaFake, msg

POST = "✨ {n}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 20 ml: R$ 200,00 | APC\nQUANTIDADE DO FRASCO: 50 ml"
ADMIN = dict(autor="9@s.whatsapp.net", nome="Admin", fone="5519999")
MARINA = dict(autor="7@s.whatsapp.net", nome="Marina")
BRUNA = dict(autor="6@s.whatsapp.net", nome="Bruna")
POST_KIRKE, POST_TORINO = "post_kirke", "post_torino"


@pytest.fixture
def grupo(tmp_path):
    """Kirke e Torino abertos; devolve os ajudantes usados nos testes."""
    arm = Armazem(tmp_path / "e.json")
    with arm as e:
        e.modo, e.config.grupo_jid, e.config.admins = "ao_vivo", GRUPO, ["5519999"]
        e.config.segundos_ate_postar_lista = 0
        e.grupo_aberto = True
    wa = WaFake()
    m = Motor(arm, wa)
    n = [0]

    async def abrir():
        await m.receber(msg(POST.format(n="KIRKE | TIZIANA TERENZI"), **ADMIN, mid=POST_KIRKE))
        await m.receber(msg(POST.format(n="TORINO 21 | XERJOFF"), **ADMIN, mid=POST_TORINO))

    asyncio.run(abrir())
    marco = [len(wa.enviadas)]

    def manda(texto, respondendo=None, quem=MARINA):
        n[0] += 1
        asyncio.run(m.receber(msg(texto, mid=f"c{n[0]}", citado=respondendo, **quem)))

    def pedidos(prefixo):
        r = next(x for x in arm.estado.rateios if x.nome.startswith(prefixo))
        return [(p.ml, next(q for q in (MARINA, BRUNA) if q["autor"] == p.autor_id)) for p in r.pedidos]

    def mensagens_no_grupo():
        """mensagens que o robô mandou pro grupo desde o último pedido (listas e reações não contam)"""
        novas = [t for _, t, _ in wa.enviadas[marco[0]:] if "QUANTIDADE DO FRASCO" not in t]
        marco[0] = len(wa.enviadas)
        return novas

    yield manda, pedidos, mensagens_no_grupo


def test_o_meu_e_so_3ml_deixa_um_pedido_de_3(grupo):
    # 29/09 14:06: "O meu aqui é só 3ml tira o de 5ml desse por favor"
    manda, pedidos, mensagens_no_grupo = grupo
    manda("3ml", respondendo=POST_KIRKE, quem=MARINA)
    manda("5ml", respondendo=POST_KIRKE, quem=MARINA)
    mensagens_no_grupo()

    manda("O meu aqui é só 3ml tira o de 5ml desse por favor", quem=MARINA)

    assert pedidos("KIRKE") == [(3, MARINA)]   # um pedido só, de 3 ml
    assert not mensagens_no_grupo()            # sem "restam só X ml" errado


def test_mais_2ml_soma_no_pedido_que_ja_existe(grupo):
    # 29/09 14:07: "eu quero mais 2 ml dele pode ser?"
    manda, pedidos, _ = grupo
    manda("3ml", respondendo=POST_TORINO, quem=BRUNA)
    manda("eu quero mais 2 ml dele pode ser?", quem=BRUNA)

    assert pedidos("TORINO") == [(5, BRUNA)]   # 2 ml abaixo do mínimo: soma, não cria linha


def test_fica_5ml_confirma_em_vez_de_duplicar(grupo):
    # 29/09 14:16: "Obrigada. Fica 5ml do nishane pra mim" (a pessoa já tinha 5 ml)
    manda, pedidos, _ = grupo
    manda("5ml", respondendo=POST_TORINO, quem=BRUNA)
    manda("Obrigada. Fica 5ml do torino pra mim", quem=BRUNA)

    assert pedidos("TORINO") == [(5, BRUNA)]


def test_dona_do_apc_pedindo_mais_soma_no_apc(grupo):
    # 29/09 11:15: "30 +10ml" respondendo o post (quem já tinha o APC)
    manda, pedidos, _ = grupo
    manda("apc", respondendo=POST_KIRKE, quem=MARINA)
    manda("20 +10ml", respondendo=POST_KIRKE, quem=MARINA)

    assert pedidos("KIRKE") == [(30, MARINA)]
