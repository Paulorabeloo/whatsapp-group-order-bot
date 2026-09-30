"""Regras do rateio nos limites: nunca fica negativo, APC unico, alterar/cancelar em todas as situacoes,
lista colada e lista do admin com nomes repetidos, mensagem apagada, render sempre consistente."""

import random
from datetime import datetime

from robo.interpretar import interpretar
from robo.post import LinhaLista, ler_post
from robo.rateio import Autor, Rateio, adotar_lista_do_admin, aplicar, escolher_rateio, incorporar_lista_colada, novo_rateio, remover_por_msg, renderizar
from robo.texto import SP

AG = datetime(2026, 9, 25, 18, 0, tzinfo=SP)
POST = "✨ TESTE | X\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 3 ml: R$ 30,00\n💎 5 ml: R$ 50,00\n👑 10 ml: R$ 100,00 | O primeiro que pedir leva o APC\nQUANTIDADE DO FRASCO: {ml} ml"


def novo(ml=30):
    return novo_rateio(ler_post(POST.format(ml=ml)), "post", AG)


def A(i, nome=None):
    return Autor(f"{i}@s.whatsapp.net", f"m{i}", nome or f"P{i}")


def test_nunca_negativo_e_fecha_no_zero():
    r = novo(10)
    r = aplicar(r, interpretar("5ml"), A(1), AG).rateio
    res = aplicar(r, interpretar("10ml"), A(2), AG)
    assert not res.ok and "Restam só 5" in res.resposta
    r = aplicar(r, interpretar("5ml"), A(2), AG).rateio
    assert r.disponivel == 0 and r.status == "fechado"
    assert not aplicar(r, interpretar("3ml"), A(3), AG).ok
    assert "fechado" in aplicar(r, interpretar("3ml"), A(3), AG).resposta


def test_apc_unico_e_sem_espaco():
    r = novo(15)
    r = aplicar(r, interpretar("apc"), A(1), AG).rateio
    assert r.dono_apc.autor_id == A(1).id and r.disponivel == 5
    res = aplicar(r, interpretar("apc"), A(2), AG)
    assert not res.ok and "já foi" in res.resposta
    assert not aplicar(r, interpretar("apc"), A(1), AG).ok and aplicar(r, interpretar("apc"), A(1), AG).resposta is None
    r2 = aplicar(novo(15), interpretar("10ml"), A(1), AG).rateio
    res = aplicar(r2, interpretar("apc"), A(2), AG)
    assert not res.ok and "suficiente" in res.resposta


def test_apc_em_post_sem_apc_e_ignorado():
    r = novo_rateio(ler_post("✨ A | B\nValor por ml: R$ 1,00\n💎 5 ml: R$ 5,00\nQUANTIDADE DO FRASCO: 10 ml"), "p", AG)
    res = aplicar(r, interpretar("apc"), A(1), AG)
    assert not res.ok and res.resposta is None


def test_alterar_todos_os_casos():
    r = novo(30)
    # sem pedido anterior: vira pedido novo
    r = aplicar(r, {"tipo": "alterar", "ml": 5}, A(1), AG).rateio
    assert [p.ml for p in r.pedidos] == [5]
    # com um pedido: troca
    r = aplicar(r, interpretar("altera pra 10ml"), A(1), AG).rateio
    assert [p.ml for p in r.pedidos] == [10]
    # nao pode passar do disponivel
    assert "Restam" in aplicar(r, interpretar("altera pra 50ml"), A(1), AG).resposta
    # abaixo do minimo
    assert "mínimo" in aplicar(r, interpretar("altera pra 1ml"), A(1), AG).resposta
    # com dois pedidos: muda o ultimo
    r = aplicar(r, interpretar("3ml"), A(1), datetime(2026, 9, 25, 18, 5, tzinfo=SP)).rateio
    r = aplicar(r, interpretar("altera pra 5ml"), A(1), AG).rateio
    assert sorted(p.ml for p in r.pedidos if not p.apc) == [5, 10]
    # dono do APC sem outro pedido: os ml a mais somam na linha do APC (regra de 29/09), nunca viram linha separada
    r2 = aplicar(novo(30), interpretar("apc"), A(2), AG).rateio
    r2 = aplicar(r2, interpretar("altera pra 5ml"), A(2), AG).rateio
    assert r2.dono_apc.ml == 15 and [p.ml for p in r2.pedidos if not p.apc] == []


def test_cancelar():
    r = novo(30)
    assert not aplicar(r, interpretar("desisto"), A(1), AG).ok  # nada a cancelar
    r = aplicar(r, interpretar("5ml"), A(1), AG).rateio
    r = aplicar(r, interpretar("3ml"), A(1), AG).rateio
    r = aplicar(r, interpretar("apc"), A(1), AG).rateio
    r = aplicar(r, interpretar("5ml"), A(2), AG).rateio
    r = aplicar(r, interpretar("desisto"), A(1), AG).rateio
    assert [p.autor_id for p in r.pedidos] == [A(2).id] and r.dono_apc is None


def test_cancelar_reabre_frasco_fechado():
    r = aplicar(novo(10), interpretar("10ml"), A(1), AG).rateio
    assert r.status == "fechado"
    r2 = remover_por_msg(r, "m1")
    assert r2.status == "aberto" and r2.disponivel == 10
    assert remover_por_msg(r, "inexistente") is None


def test_lista_colada_nomes_repetidos_e_apc():
    r = aplicar(novo(50), interpretar("5ml"), A(1, "Ana"), AG).rateio
    linhas = [LinhaLista(False, 5, "Ana"), LinhaLista(False, 5, "Ana"), LinhaLista(True, 10, "Bia")]
    res = incorporar_lista_colada(r, linhas, A(9, "Bia"), AG)
    assert res.ok and len(res.novas) == 2
    assert res.rateio.disponivel == 30 and res.rateio.dono_apc.nome == "Bia"
    # duas linhas novas: nenhuma vira mencao do autor
    assert all(p.autor_id is None for p in res.rateio.pedidos[1:])
    # colar a mesma lista de novo nao duplica
    res2 = incorporar_lista_colada(res.rateio, linhas, A(9, "Bia"), AG)
    assert not res2.ok and res2.novas == []


def test_lista_colada_que_estoura_e_recusada():
    r = novo(10)
    res = incorporar_lista_colada(r, [LinhaLista(False, 5, "A"), LinhaLista(False, 10, "B")], A(1), AG)
    assert not res.ok and res.rateio is r


def test_admin_manda_sempre():
    r = aplicar(novo(50), interpretar("5ml"), A(1, "Ana"), AG).rateio
    r = aplicar(r, interpretar("apc"), A(2, "Bia"), AG).rateio
    # admin postou lista menor, sem a Bia e com Ana em 10
    r2 = adotar_lista_do_admin(r, [LinhaLista(False, 10, "Ana")])
    assert [(p.ml, p.nome, p.autor_id) for p in r2.pedidos] == [(10, "Ana", A(1).id)] and r2.dono_apc is None
    # admin postou lista vazia: zera
    assert adotar_lista_do_admin(r, []).pedidos == []
    # admin postou lista que fecha
    r3 = adotar_lista_do_admin(r, [LinhaLista(False, 50, "Todo")])
    assert r3.status == "fechado"


def test_escolher_rateio_dica_ambigua():
    a, b = novo(), novo()
    a.nome, a.post_msg_id = "NISHANE HACIVAT", "pa"
    b.nome, b.post_msg_id = "NISHANE ANI", "pb"
    assert escolher_rateio([a, b], dica="nishane") is None      # os dois casam
    assert escolher_rateio([a, b], dica="hacivat") is a
    assert escolher_rateio([a, b], citado_id="pb") is b
    a.lista_msg_ids.append("lista1")
    assert escolher_rateio([a, b], citado_id="lista1") is a
    assert escolher_rateio([], citado_id="x") is None


def test_render_consistente_e_mencoes_unicas():
    r = novo(30)
    texto, mencoes = renderizar(r, AG)
    assert "Disponível 30 ml incluindo APC" in texto and mencoes == []
    r = aplicar(r, interpretar("5ml"), A(1, "Ana"), AG).rateio
    r = aplicar(r, interpretar("3ml"), A(1, "Ana"), AG).rateio
    r = aplicar(r, interpretar("apc"), A(2, "Bia"), AG).rateio
    texto, mencoes = renderizar(r, AG)
    assert texto.count("@1") == 2 and mencoes.count(A(1).id) == 1 and A(2).id in mencoes
    assert "👑 Bia | APC + 10 ml 👑" in texto and "Disponível 12 ml" in texto and "incluindo APC" not in texto
    assert "\n\n\n" not in texto


def test_dict_roundtrip():
    r = aplicar(novo(), interpretar("5ml"), A(1), AG).rateio
    r2 = Rateio.from_dict(r.to_dict())
    assert r2.to_dict() == r.to_dict() and r2.disponivel == r.disponivel


def test_simulacao_aleatoria_invariantes():
    """Milhares de acoes aleatorias: o disponivel nunca fica negativo, nunca ha 2 APC, status coerente."""
    rnd = random.Random(3)
    frases = ["5ml", "3ml", "10ml", "7", "apc", "altera pra 5ml", "desisto", "2x 3ml", "quero 15 ml", "1ml", "100ml", "oi", "2", "3"]
    for _ in range(300):
        r = novo(rnd.choice([10, 20, 30, 50, 100]))
        for _ in range(rnd.randint(1, 40)):
            aut = A(rnd.randint(1, 6))
            if rnd.random() < 0.1:
                r = remover_por_msg(r, aut.msg_id) or r
            else:
                r = aplicar(r, interpretar(rnd.choice(frases)), aut, AG).rateio
            assert 0 <= r.disponivel <= r.total_ml
            assert sum(1 for p in r.pedidos if p.apc) <= 1
            assert (r.status == "fechado") == (r.disponivel == 0)
            assert all(p.ml >= 1 for p in r.pedidos)
            renderizar(r, AG)
