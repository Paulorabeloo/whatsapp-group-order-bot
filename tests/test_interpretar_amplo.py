"""Entendimento de mensagem: todos os jeitos de pedir vistos no grupo + casos-limite + fuzz.
Regra de ouro: interpretar() NUNCA levanta excecao, seja qual for o texto."""

import os
import random
import string
from pathlib import Path

import pytest

from robo.interpretar import interpretar

CHAT = Path(os.environ.get("CHAT_EXPORT", "chat.txt"))   # export do WhatsApp (nao versionado)


def tipo(t):
    return interpretar(t)["tipo"]


def ml(t):
    it = interpretar(t)
    return [i["ml"] for i in it["itens"] for _ in range(i["qtd"])] if it["tipo"] == "pedido" else None


# ---------------------------------------------------------------- pedidos
@pytest.mark.parametrize("texto,esperado", [
    ("5ml", [5]), ("5 ml", [5]), ("5ML", [5]), ("5 mL", [5]), ("5mls", [5]), ("5 m l", [5]),
    ("quero 5ml", [5]), ("Quero 5 ml", [5]), ("eu quero 5ml", [5]), ("Eu quero de 3ml", [3]),
    ("5ml por favor", [5]), ("5ml, por favor", [5]), ("3ml por favor, experimentar", [3]),
    ("Bom dia, 3ml por favor", [3]), ("Boa noite, side effect 5 ml", [5]),
    ("clara 3", [3]), ("Clara 3 ml", [3]), ("3 ml\nEduardo", [3]), ("Mateo 5ml", [5]), ("5ml - Fabio", [5]),
    ("5ml Torino", [5]), ("5 ml - valaya", [5]), ("Valaya - 3ml\nSara", [3]), ("5ml giorgia - kirke", [5]),
    ("10", [10]), ("7", [7]), ("10-", [10]), ("15", [15]), ("2", [2]), ("1", [1]),
    ("2x 5ml", [5, 5]), ("2 x 5ml", [5, 5]), ("3x 3ml", [3, 3, 3]),
    ("5 ml do Torino e 5 ml do wulong cha", [5, 5]), ("eduardo\n10ml naxos\n5ml jazz club", [10, 5]),
    ("vou ficar com esses 10ml 🤩", [10]), ("peguei 5ml gente!", [5]), ("Tarde !\nTenho interesse 5ml", [5]),
    ("quero 5ml desse", [5]), ("esse eu quero 5 ml", [5]), ("O meu quero 10 ml", [10]), ("vou querer 5 ml", [5]),
    ("5ml 🙏", [5]), ("💎 5ml", [5]), ("5ml!!!", [5]), ("  5ml  ", [5]), ("5\u00a0ml", [5]),
    ("quero 3ml - 87,00", [3]), ("12 ml", [12]), ("8ml", [8]), ("100ml", [100]),
])
def test_pedidos(texto, esperado):
    assert ml(texto) == esperado, interpretar(texto)


# ---------------------------------------------------------------- apc / alterar / cancelar
@pytest.mark.parametrize("texto", ["apc", "APC", "Apc", "quero o apc", "Quero meu APC", "eu quero apc", "APC!!!", "apc 🙏", "30ml apc murilo", "10ml APC"])
def test_apc(texto):
    assert tipo(texto) == "apc", interpretar(texto)


@pytest.mark.parametrize("texto,esperado", [
    ("altera pra 10ml", 10), ("aumenta pra 10", 10), ("pode aumentar o meu para 10ml por favor ?", 10),
    ("muda meu pedido pra 5ml", 5), ("troca o meu 3 por 5ml", 5), ("diminui pra 3ml", 3), ("ajusta pra 15", 15),
])
def test_alterar(texto, esperado):
    it = interpretar(texto)
    assert it["tipo"] == "alterar" and it["ml"] == esperado, it


@pytest.mark.parametrize("texto", ["desisto", "cancela o meu", "pode tirar o meu", "tira meu pedido", "não vou querer mais", "nao vou mais querer", "remove o meu por favor", "desisti do 5ml"])
def test_cancelar(texto):
    assert tipo(texto) == "cancelar", interpretar(texto)


# ---------------------------------------------------------------- nao e pedido
@pytest.mark.parametrize("texto", [
    "Brasil 2 x 1 Noruega", "Brasil 2x1 Noruega", "Brasil 3 x 2", "3x2", "2 x 0",
    "falta 17ml pra fechar", "temos 16ml disponíveis incluindo o apc", "somente 10ml pra fecharmos", "restam 5ml",
    "ainda tem torino 5?", "tem 10ml ainda?", "quanto tá o ml?", "o APC já saiu?", "vai ter 5ml?",
    "obrigada", "obrigado 🙏", "kkkkkkk", "👏👏👏", "bom dia", "sensacional", "ok", "sim", "perfeito", "🫣", "?",
    "<figurinha omitida>", "<imagem ocultada>", "<vídeo omitido>", "Mensagem apagada", "",
    "@all", "Grupo aberto", "amei esse perfume", "esse é maravilhoso", "Nota 10 esse perfume",
    "ontem você pediu 5 ml do Alexandria", "olha...já tenho um frasco dele", "Minha experiência boa foi com Valaya, peguei 5ml e adorei o perfume todo",
    "Sensacional pessoal!!! obrigado pela confiança", "vou pegar 1 milhão", "1500", "R$ 120,00",
])
def test_nao_e_pedido(texto):
    assert tipo(texto) in ("nada", "duvida"), interpretar(texto)


@pytest.mark.parametrize("texto", ["eu quero", "quero", "Quero também", "eu quero tbm"])
def test_quero_sem_numero_e_duvida(texto):
    assert tipo(texto) == "duvida"


def test_lista_colada_e_reconhecida():
    lista = "✨ VIBRATO | SOSPIRO\n\n💎3ml - Fabia\n💎5ml - Mateo\n💎15ml - Cris\n\nDisponível 5 ml"
    assert tipo(lista) == "lista"
    assert tipo("✨APC 30ml Dr Marchius✨\n\n5ml Luciana\n5ml JB") == "lista"


def test_dica_do_perfume():
    assert interpretar("5ml torino")["itens"][0]["dica"] == "torino"
    assert interpretar("3ml do nishane, por favor")["itens"][0]["dica"] == "nishane"


# ---------------------------------------------------------------- nunca quebra
@pytest.mark.parametrize("texto", [None, 123, "", " ", "\n\n", "ml", "mlml", "x", "5" * 500, "ml " * 300, "🤎" * 100,
                                   "\u202e5ml", "5\u200bml", "٥ml", "５ml", "5ｍｌ", "-5ml", "+5ml", "5.5ml", "5,5 ml", "0ml", "999ml", "1000ml"])
def test_nao_quebra(texto):
    r = interpretar(texto)
    assert isinstance(r, dict) and "tipo" in r


def test_fuzz_aleatorio():
    rnd = random.Random(42)
    alfabeto = string.printable + "áéíóúãõçÁÉÍÓÚ💎👑✨🙏❌@~|–—"
    for _ in range(3000):
        t = "".join(rnd.choice(alfabeto) for _ in range(rnd.randint(0, 80)))
        r = interpretar(t)
        assert r["tipo"] in ("pedido", "apc", "alterar", "cancelar", "lista", "duvida", "nada")
        if r["tipo"] == "pedido":
            assert all(1 <= i["ml"] <= 200 and 1 <= i["qtd"] <= 5 for i in r["itens"])


@pytest.mark.skipif(not CHAT.exists(), reason="export do grupo nao esta nesta maquina")
def test_todas_as_mensagens_reais_do_grupo():
    """Cada uma das mensagens reais passa sem excecao e cai numa categoria valida."""
    import re
    bruto = CHAT.read_text(encoding="utf-8")
    n = 0
    for bloco in re.split(r"\n(?=\[\d+/\d+/\d+, )", bruto):
        m = re.match(r"^\[.*?\] (?:- )?([^:\n]+?): ([\s\S]*)$", bloco.strip())
        if not m:
            continue
        r = interpretar(m.group(2))
        assert r["tipo"] in ("pedido", "apc", "alterar", "cancelar", "lista", "duvida", "nada")
        n += 1
    assert n > 5000
