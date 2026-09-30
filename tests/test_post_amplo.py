"""Leitura de posts em todos os formatos que o grupo ja usou, e das listas escritas a mao."""

import pytest

from robo.post import ler_linhas_lista, ler_post, parece_post

ANTIGO = """PERFUME DE NICHO ESCOLHIDO: TIZIANA TERENZI - ORION

Valor por ml: R$ 22,00/ Pedido mínimo: 3ml

VALORES DOS DECANTS

* 3ml –   R$ 66,00
* 5ml –   R$ 110,00 RECOMENDADO
* 10ml – R$ 220,00
* 20ml – R$ 440,00
* 40ml – R$ 880,00 (O primeiro que pedir no grupo leva o APC)

Pagamento: PIX ou cartão (até 12x com taxa)

QUANTIDADE DO FRASCO: 100ML

🏆 APC + 40ml Disponível 🏆

⭐5ml Kleber
⭐5ml Antonio Marcos"""

SETEMBRO = """04/09/2026

✨ VIBRATO | SOSPIRO

Valor por ml: R$ 20,00
Pedido mínimo: 3 ml

VALOR DOS DECANTS

💎 3 ml: R$ 60,00
💎 5 ml: R$ 100,00 | MAIS SOLICITADO
💎 10 ml: R$ 200,00
👑 30 ml: R$ 600,00 | O primeiro que pedir leva o APC

QUANTIDADE DO FRASCO: 100 ml

🫅🏼Cris Peregrina APC + 30ml 🫅🏼

💎3ml - Fabia @~Katia
💎5ml - Mateo @~Mateo
💎15 ml Cris @~Cris Peregrina
💎 15ml - Kleber @Kleber 6327
💎10 ml - Gustavo
💎 5ml william @~Willian Pestana

Disponíveis somente 5 mls"""

NOVO = """25/09/2026

🤎 UNIQUE’E LUXURY| CHICELLE

Valor por ml: R$ 40,00
Pedido mínimo: 3 ml

VALORES DOS DECANTS

💎 3 ml: R$ 120,00
💎5 ml: R$ 200,00 | MAIS SOLICITADO
💎 10 ml: R$ 400,00
💎 15 ml: R$ 600,00
👑20ml : R$ 800,00 | O primeiro que pedir leva o APC

Pagamento via PIX ou cartão em até 12x com taxa.

O pagamento deverá ser realizado apenas aos administradores: @~Financeiro

QUANTIDADE DO FRASCO: 50 ml"""

BYREDO = """ABERTURA ÀS 17 HORAS

 🌿 BYREDO – BAL D’AFRIQUE

https://www.fragrantica.com.br/perfume/Byredo/Bal-d-Afrique-6458.html

Valor por ml: R$ 32,00 | Pedido mínimo: 3 ml

VALORES DOS DECANTS

* 3 ml – R$ 96
• 5 ml – R$ 160,00 mais solicitado*
* 10 ml – R$ 320,00
* 30 ml – R$ 960,00 — o primeiro que pedir leva o APC

QUANTIDADE DO FRASCO: 100 ml"""


def test_formato_antigo():
    p = ler_post(ANTIGO)
    assert p.nome == "TIZIANA TERENZI - ORION"
    assert (p.valor_ml, p.minimo, p.total_ml, p.apc_ml) == (22.0, 3, 100, 40)
    assert p.tamanhos == [3, 5, 10, 20, 40]
    assert [(l.apc, l.ml, l.nome) for l in p.linhas_lista] == [(False, 5, "Kleber"), (False, 5, "Antonio Marcos")]


def test_formato_setembro_com_lista():
    p = ler_post(SETEMBRO)
    assert p.nome == "VIBRATO | SOSPIRO" and p.apc_ml == 30 and p.total_ml == 100
    ls = p.linhas_lista
    assert ls[0].apc and ls[0].nome.startswith("Cris")
    assert [(l.ml, l.nome) for l in ls[1:]] == [(3, "Fabia"), (5, "Mateo"), (15, "Cris"), (15, "Kleber"), (10, "Gustavo"), (5, "william")]


def test_formato_novo_espacos_estranhos():
    p = ler_post(NOVO)
    assert p.nome == "UNIQUE’E LUXURY | CHICELLE"
    assert p.tamanhos == [3, 5, 10, 15, 20] and p.apc_ml == 20 and p.total_ml == 50 and p.valor_ml == 40.0
    assert p.cabecalho.startswith("25/09/2026") and p.cabecalho.endswith("QUANTIDADE DO FRASCO: 50 ml")


def test_formato_byredo_com_link_e_travessao():
    p = ler_post(BYREDO)
    assert "BYREDO" in p.nome and "AFRIQUE" in p.nome
    assert p.valor_ml == 32.0 and p.minimo == 3 and p.apc_ml == 30 and p.tamanhos == [3, 5, 10, 30]


@pytest.mark.parametrize("prefixo", ["<imagem ocultada> ", "[Encaminhada] ", "<vídeo omitido> Acervistas, "])
def test_prefixos_de_midia_nao_atrapalham(prefixo):
    p = ler_post(prefixo + NOVO)
    assert p.total_ml == 50 and "CHICELLE" in p.nome


def test_sem_pedido_minimo_assume_3():
    t = "✨ X | Y\nValor por ml: R$ 10,00\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 50 ml"
    assert ler_post(t).minimo == 3


def test_post_sem_apc():
    t = "✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 3 ml: R$ 30,00\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 20 ml"
    p = ler_post(t)
    assert p.apc_ml is None and p.tamanhos == [3, 5]


@pytest.mark.parametrize("texto", ["", "5ml", "Valor por ml: R$ 10,00", "QUANTIDADE DO FRASCO: 50 ml", "oi tudo bem", None])
def test_nao_e_post(texto):
    assert not parece_post(texto) and ler_post(texto or "") is None


def test_linhas_lista_variadas():
    ls = ler_linhas_lista([
        "⭐ 3ml Bruna Almeida", "💎 5ml - Gio @~Gio Singnorete Lissoni", "💎 3ml Brenda @Brenda", "⭐  3ml Alana Michele",
        "🏆 Sirleia Heiderscheidt APC + 40ml 🏆", "✨30ml APC HÉRCULES✨", "💫30ml + APC CAROL💫",
        "Disponível só 16ml", "62ml para fechar o frasco", "❌❌FRASCO FECHADO❌❌04/09/26",
        "Apenas responda sobre a imagem do perfume, colocando a quantidade desejada, por exemplo: 3ml, 5ml e assim por diante.",
        "Levará o frasco original + embalagem com a quantidade informada de 30 ml.", "",
    ])
    assert [(l.apc, l.ml, l.nome) for l in ls] == [
        (False, 3, "Bruna Almeida"), (False, 5, "Gio"), (False, 3, "Brenda"), (False, 3, "Alana Michele"),
        (True, 40, "Sirleia Heiderscheidt"), (True, 30, "HÉRCULES"), (True, 30, "CAROL"),
    ]


def test_fuzz_post_nao_quebra():
    import random
    rnd = random.Random(7)
    partes = NOVO.split("\n")
    for _ in range(500):
        rnd.shuffle(partes)
        t = "\n".join(partes[: rnd.randint(1, len(partes))])
        p = ler_post(t)
        if p:
            assert p.total_ml > 0 and p.valor_ml > 0 and p.minimo >= 1
