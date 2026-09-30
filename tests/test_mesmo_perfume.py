"""Reconhecer o mesmo perfume em nomes escritos de jeitos diferentes, sem confundir perfumes da mesma marca."""

import pytest

from robo.post import ler_post
from robo.texto import mesmo_perfume


@pytest.mark.parametrize("a,b", [
    ("TORINO 21 | XERJOFF", "Xerjoff Torino 21"),
    ("VIBRATO | SOSPIRO", "SOSPIRO VIBRATO"),
    ("NISHANE ANI", "PERFUME DE NICHO QUE AINDA TEMOS - NISHANE ANI"),
    ("🤎 UNIQUE’E LUXURY | CHICELLE", "UNIQUE'E LUXURY | CHICELLE"),
    ("CAROLINA HERRERA - CEDAR CHIC", "CEDAR CHIC"),
    ("PARFUM DE MARLY – DELINA LA ROSÉE", "PARFUMS DE MARLY - DELINA LA ROSEE"),
])
def test_mesmo(a, b):
    assert mesmo_perfume(a, b) and mesmo_perfume(b, a)


@pytest.mark.parametrize("a,b", [
    ("NISHANE ANI", "NISHANE HACIVAT"),
    ("NISHANE HACIVAT", "NISHANE WULONG CHÁ"),
    ("SOSPIRO VIBRATO", "SOSPIRO DOLCE MELODIA"),
    ("XERJOFF TORINO 21", "XERJOFF ERBA PURA"),
    ("TIZIANA TERENZI - ORION", "TIZIANA TERENZI - KIRKE"),
    ("PARFUMS DE MARLY - VALAYA", "PARFUMS DE MARLY - DELINA"),
    ("", "NISHANE ANI"),
])
def test_diferente(a, b):
    assert not mesmo_perfume(a, b)


@pytest.mark.parametrize("inicio,nome", [
    ("PERFUME QUE AINDA TEMOS: PARFUM DE MARLY – DELINA LA ROSÉE", "PARFUM DE MARLY – DELINA LA ROSÉE"),
    ("PERFUME DE NICHO QUE AINDA TEMOS - NISHANE ANI", "NISHANE ANI"),
    ("*PERFUME DE NICHO ESCOLHIDO: \n*\nMAISON MARGIELA (França EDT) – RÉPLICA JAZZ CLUB **", "MAISON MARGIELA – RÉPLICA JAZZ CLUB"),
    ("PERFUME DE NICHO ESCOLHIDO: TIZIANA TERENZI - ORION", "TIZIANA TERENZI - ORION"),
])
def test_nome_com_prefixo_do_admin(inicio, nome):
    p = ler_post(inicio + "\n\nValor por ml: R$ 19,00/ Pedido mínimo: 3ml\n* 3ml – R$ 57,00\nQUANTIDADE DO FRASCO: 100ML")
    assert p.nome == nome
