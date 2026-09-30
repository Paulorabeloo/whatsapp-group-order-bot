"""Catalogo de exemplo: perfumes e marcas conhecidos + marcas comuns de nicho.

Serve pra uma regra so: pedido que cita um perfume que NAO esta aberto no sistema nao e anotado
("3ml vibrato" respondendo a imagem de disponiveis, com o Bal d'Afrique aberto).
Perfumes postados depois disso entram sozinhos (Estado.perfumes_vistos).
"""

from __future__ import annotations

from .texto import palavras_chave

HISTORICO = [
    "AVENTUS FOR HER | CREED", "BLUE TALISMAN | EX NIHILO", "BAL D'AFRIQUE | BYREDO", "CEDAR CHIC | CAROLINA HERRERA",
    "DAMA BIANCA | CASAMORATI", "MEFISTO | CASAMORATI", "WILD VETIVER | CREED", "SOIE MALAQUAIS | DRIES VAN NOTEN",
    "ERBA PURA | XERJOFF", "ERBA GOLD | XERJOFF", "ALEXANDRIA II | XERJOFF", "NAXOS | XERJOFF", "TORINO 21 | XERJOFF",
    "LIFT ME UP | INITIO", "OUD FOR GREATNESS | INITIO", "SIDE EFFECT | INITIO", "MUSK THERAPY | INITIO",
    "JAZZ CLUB | MAISON MARGIELA REPLICA", "MEANT TO BE SEEN | NISHANE", "ANI | NISHANE", "HACIVAT | NISHANE",
    "HUNDRED SILENT WAYS | NISHANE", "TUBEROZA X | NISHANE", "WULONG CHA | NISHANE", "OPERA INFERNAL | FABBRICA DELLA MUSA",
    "VALAYA | PARFUMS DE MARLY", "DELINA | PARFUMS DE MARLY", "ATHENAIS | PARFUMS DE MARLY", "PALATINE | PARFUMS DE MARLY",
    "LAYTON | PARFUMS DE MARLY", "ORION | TIZIANA TERENZI", "ORIUM | TIZIANA TERENZI", "KIRKE | TIZIANA TERENZI",
    "QUEENING | MIND GAMES", "DOLCE MELODIA | SOSPIRO", "VIBRATO | SOSPIRO", "IMPADIA | BDK PARFUMS",
    "EXISTENCE | AMOUAGE",
]

MARCAS = """
creed byredo amouage nishane initio xerjoff bdk sospiro tiziana terenzi marly casamorati kilian roja
mancera montale lattafa armaf afnan rasasi ajmal nasomatto orto parisi diptyque malle lutens guerlain chanel dior
hermes penhaligons vilhelm nihilo margiela replica goldfield electimuss boadicea profumum amouroud carner zoologist
kajal memo lelabo labo baccarat maison francis kurkdjian mfk clive christian louboutin valentino ysl armani
""".split()


# palavras de nome de perfume que tambem sao nome de gente ou palavra comum: nunca servem de prova
AMBIGUAS = set("""
blue gold side mind seen ways wild club della dama pura dolce maison carolina christian francis memo chic lift musk
opera melodia effect silent hundred meant games jazz infernal musa bianca clive therapy greatness talisman
""".split())


def palavras_de_perfume(extras: list[str] = ()) -> set[str]:
    """todas as palavras que identificam um perfume/marca conhecido"""
    out = set(MARCAS)
    for n in [*HISTORICO, *extras]:
        out |= set(palavras_chave(n))
    return out - AMBIGUAS
