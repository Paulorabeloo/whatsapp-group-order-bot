"""Mede o robo contra os exemplos marcados na aba Aprender (data/exemplos.jsonl).

Uso: python scripts/avaliar_exemplos.py [--erros]

Cada duvida marcada vira um caso: "era pedido de 5 ml" ou "nao era pedido". O script mostra quantos o robo
acertaria hoje. Quando uma regra nova e escrita, roda de novo: o numero tem que subir e nao pode cair.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robo.interpretar import interpretar  # noqa: E402

ARQ = Path("data/exemplos.jsonl")
if not ARQ.exists():
    sys.exit("ainda nao ha exemplos: marque casos na aba Aprender do painel")

exemplos = [json.loads(l) for l in ARQ.read_text(encoding="utf-8").splitlines() if l.strip()]
duvidas = [x for x in exemplos if x["tipo"] == "duvida"]
certos, erros = 0, []
for x in duvidas:
    it = interpretar(x["texto"])
    if x["rotulo"] == "nada":
        ok = it["tipo"] in ("nada", "duvida")
    elif x.get("apc"):
        ok = it["tipo"] == "apc"
    else:
        ok = it["tipo"] == "pedido" and x.get("ml") in [i["ml"] for i in it["itens"]]
    certos += ok
    if not ok:
        erros.append(f"  {x['texto']!r:50} esperado {x['rotulo']} {x.get('ml') or ''} | robo: {it['tipo']}")

print(f"exemplos: {len(exemplos)} ({dict(Counter(x['tipo'] for x in exemplos))})")
if duvidas:
    print(f"duvidas que o robo resolveria hoje: {certos}/{len(duvidas)} ({100 * certos / len(duvidas):.0f}%)")
div = [x for x in exemplos if x["tipo"] == "divergencia"]
if div:
    print(f"divergencias com o admin: {len(div)} | robo errou: {sum(x['rotulo'] == 'robo_errou' for x in div)}")
if "--erros" in sys.argv and erros:
    print("\n".join(erros))
