"""Utilidades de texto compartilhadas."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")

_GENERICAS = {"perfume", "nicho", "escolhido", "parfum", "parfums", "decant", "eau", "extrait", "edition",
              "ainda", "temos", "estoque", "disponivel", "fragrancia", "fragrancias", "hoje"}
_RE_LIXO = re.compile(r"[^\w\s|?!,.\-+x/]", re.UNICODE)


def normalizar(s: str | None) -> str:
    """minusculo, sem acento, sem emoji, espacos colapsados"""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _RE_LIXO.sub(" ", s.lower()).replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def palavras_chave(nome: str) -> list[str]:
    """palavras "significativas" de um nome de perfume (pra casar "torino" com "TORINO 21 | XERJOFF")"""
    return [
        p for p in re.split(r"[\s|\-/,.]+", normalizar(nome))
        if len(p) >= 4 and not p.isdigit() and p not in _GENERICAS
    ]


def mesmo_perfume(a: str, b: str) -> bool:
    """Dois nomes sao o mesmo perfume? A marca sozinha nao basta ("NISHANE ANI" != "NISHANE HACIVAT"):
    todas as palavras do nome mais curto precisam aparecer no outro. Conta palavras de 3+ letras ("ANI", "CHA")."""
    def chaves(n):
        return {p for p in re.split(r"[\s|\-/,.:–—]+", normalizar(n)) if len(p) >= 3 and not p.isdigit() and p not in _GENERICAS}
    ca, cb = chaves(a), chaves(b)
    if not ca or not cb:
        return False
    menor, maior = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return menor <= maior


def primeiro_nome(nome: str | None) -> str:
    limpo = re.sub(r"[^\w\s'-]", " ", (nome or "").lstrip("~"), flags=re.UNICODE)
    limpo = re.sub(r"[\d_]", " ", limpo).strip()
    p = limpo.split()[0] if limpo.split() else ""
    return p[:1].upper() + p[1:].lower() if p else ""


def data_br(d: datetime | None = None) -> str:
    return (d or datetime.now(SP)).astimezone(SP).strftime("%d/%m/%y")


def agora() -> datetime:
    return datetime.now(SP)
