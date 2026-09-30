"""Reconhece o post de abertura de um decant e le as listas que o admin posta a mao.

Formatos vistos no historico:
  antigo (jul/26): "PERFUME DE NICHO ESCOLHIDO: TIZIANA TERENZI - ORION" ... "* 40ml – R$ 880,00 (O primeiro que pedir no grupo leva o APC)"
  novo   (set/26): "🌹FRENCH LEATHER | MEMO PARIS" ... "👑 30 ml: R$ 720,00 | O primeiro a pedir o APC leva o frasco original"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .texto import normalizar

RE_VALOR = re.compile(r"valor por ml:?\s*r\$\s*([\d.,]+)", re.I)
RE_MINIMO = re.compile(r"pedido m[ií]nimo:?\s*(\d+)\s*ml", re.I)
RE_FRASCO = re.compile(r"quantidade do frasco:?\s*(\d+)\s*ml", re.I)
RE_TAMANHO = re.compile(r"^[^\d\n]{0,6}(\d{1,3})\s*ml\s*[:–-]\s*r\$\s*[\d.,]+(.*)$", re.I)


@dataclass
class LinhaLista:
    apc: bool
    ml: int
    nome: str


@dataclass
class Post:
    nome: str
    valor_ml: float
    minimo: int
    total_ml: int
    tamanhos: list[int]
    apc_ml: int | None
    cabecalho: str
    linhas_lista: list[LinhaLista] = field(default_factory=list)


def _numero_br(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parece_post(texto: str | None) -> bool:
    """true se o texto e um post de decant (abertura ou lista atualizada pelo admin)"""
    t = texto or ""
    return RE_VALOR.search(t) is not None and RE_FRASCO.search(t) is not None


def ler_post(texto: str) -> Post | None:
    if not parece_post(texto):
        return None
    linhas = texto.split("\n")

    valor_ml = _numero_br(RE_VALOR.search(texto).group(1))
    m_min = RE_MINIMO.search(texto)
    minimo = int(m_min.group(1)) if m_min else 3
    total_ml = int(RE_FRASCO.search(texto).group(1))

    tamanhos: list[int] = []
    apc_ml = None
    for l in linhas:
        m = RE_TAMANHO.match(re.sub(r"^\*\s*", "", l.strip()))
        if not m:
            continue
        ml = int(m.group(1))
        tamanhos.append(ml)
        if re.search(r"apc", m.group(2), re.I) or "👑" in l:
            apc_ml = ml

    # cabecalho = tudo ate a linha da quantidade do frasco (e o que o robo repete em cima da lista)
    i_frasco = next(i for i, l in enumerate(linhas) if RE_FRASCO.search(l))
    cabecalho = re.sub(r"^<[^>]+>\s*", "", "\n".join(linhas[: i_frasco + 1])).rstrip()

    return Post(
        nome=_ler_nome(linhas),
        valor_ml=valor_ml,
        minimo=minimo,
        total_ml=total_ml,
        tamanhos=tamanhos,
        apc_ml=apc_ml,
        cabecalho=cabecalho,
        linhas_lista=ler_linhas_lista(linhas[i_frasco + 1:]),
    )


def _ler_nome(linhas_originais: list[str]) -> str:
    # datas ("04/09/2026", "25/08/26"), midia e "[Encaminhada]" nunca fazem parte do nome
    linhas = [
        re.sub(r"<[^>]+>|\[?encaminhada\]?", " ", re.sub(r"\d{1,2}/\d{1,2}(/\d{2,4})?", " ", l), flags=re.I)
        for l in linhas_originais
    ]
    # "PERFUME DE NICHO ESCOLHIDO: X", "PERFUME QUE AINDA TEMOS: X", "PERFUME DE NICHO QUE AINDA TEMOS - X"
    # (as vezes o nome vem na linha de baixo)
    prefixo = re.compile(r"^\W*perfumes?\s+(?:de\s+nicho\s+)?(?:escolhido|que\s+ainda\s+temos|ainda\s+em\s+estoque)\s*[:\-–—]?\s*", re.I)
    for i, l in enumerate(linhas):
        m = prefixo.match(l)
        if not m:
            continue
        resto = re.sub(r"[*_]", "", l[m.end():]).strip(" -–—")
        if not resto:
            resto = next((re.sub(r"[*_]", "", x).strip(" -–—") for x in linhas[i + 1:] if re.sub(r"[\W_]", "", x)), "")
        resto = re.sub(r"\s*\((?:[^)]*)\)", "", resto)   # "(França EDT)"
        if resto:
            return re.sub(r"\s+", " ", resto)
    # formato novo: "🌹FRENCH LEATHER | MEMO PARIS" (a tabela de precos tambem tem "|", por isso o filtro)
    for l in linhas:
        if "|" not in l or re.search(r"\bml\b|r\$|valor|solicitad|apc|frete|pagamento", l, re.I):
            continue
        limpa = re.sub(r"[^\w|\s'’&.-]", "", re.sub(r"\b\d{5,}\b", "", l)).strip()
        if len(limpa) > 3:
            return re.sub(r"\s*\|\s*", " | ", limpa)
    # primeira linha "de verdade" antes do preco: pula avisos de horario, links e datas
    for l in linhas:
        if RE_VALOR.search(l):
            break
        if re.search(r"abertura|hora|http|acervista|valor|escolhid|unboxing", l, re.I):
            continue
        limpa = re.sub(r"[^\w\s'’&.–-]", "", l).strip(" -–")
        if len(re.sub(r"[\W\d_]", "", limpa)) >= 3:
            return re.sub(r"\s+", " ", limpa)
    return "Decant"


def ler_linhas_lista(linhas: list[str]) -> list[LinhaLista]:
    """Linhas da lista escrita pelo admin, ex.:
    "💎5ml - Fabia @~Katia"   "⭐ 3ml Bruna Almeida"   "🫅🏼Cris Peregrina APC + 30ml 🫅🏼"   "🏆 APC + 40ml Disponível 🏆"
    """
    out: list[LinhaLista] = []
    for bruta in linhas:
        l = bruta.strip()
        if not l:
            continue
        n = normalizar(l)
        if re.search(r"dispon|fechad|arremat|para fechar", n):
            continue
        # texto explicativo do post antigo ("colocando a quantidade desejada... 3ml, 5ml", "levara ... 30 ml")
        if len(l) > 60 or re.search(r"exemplo|respond|informad|levar|frasco|quantidade|valor|r\$|privado|pagamento", n):
            continue
        if re.search(r"\bapc\b", n):
            nome = re.sub(r"[^\w\s'@~.-]", " ", l)
            nome = re.sub(r"\d+\s*ml\b|\bAPC\b|dispon\S*|\bml\b", " ", nome, flags=re.I)
            nome = re.sub(r"@.*$", " ", nome)
            nome = re.sub(r"[\d_]", " ", nome)
            nome = re.sub(r"\s+", " ", nome).strip()
            m = re.search(r"(\d{1,3})\s*ml", n)
            if nome and nome != "+":
                out.append(LinhaLista(apc=True, ml=int(m.group(1)) if m else 0, nome=nome))
            continue
        m = re.search(r"(\d{1,3})\s*ml\s*[-–]?\s*(.*)$", l, re.I)
        if not m:
            continue
        nome = re.sub(r"@.*$", " ", m.group(2))
        nome = re.sub(r"[^\w\s'.-]", " ", nome)
        nome = re.sub(r"[\d_]", " ", nome)
        nome = re.sub(r"\s+", " ", nome).strip()
        out.append(LinhaLista(apc=False, ml=int(m.group(1)), nome=nome or "?"))
    return out
