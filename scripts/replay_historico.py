"""Simula o robo no historico real do grupo e compara com as listas que o admin postou a mao.

O robo acompanha tudo sozinho (posts, pedidos curtos, listas coladas por membros). Toda vez que o
admin ("Você" no export) posta uma lista, comparamos: a lista do robo naquele momento bate com a dele?
Depois da comparacao o robo adota a lista do admin, igual vai fazer ao vivo.

Limite conhecido: o export nao guarda "respondendo a qual mensagem". Ao vivo o reply diz o perfume;
aqui, sem dica no texto, o pedido vai pro rateio aberto mais recente. Isso PIORA o numero da simulacao.

Uso: python scripts/replay_historico.py "C:\\...\\chat.txt" [--erros] [--puro]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robo.interpretar import interpretar  # noqa: E402
from robo.post import ler_post, parece_post  # noqa: E402
from robo.rateio import Autor, adotar_lista_do_admin, aplicar, cita, destacar, em_foco, escolher_rateio, incorporar_lista_colada, novo_rateio  # noqa: E402
from robo.texto import SP, palavras_chave, primeiro_nome  # noqa: E402

args = sys.argv[1:]
if not args:
    sys.exit("uso: python scripts/replay_historico.py <chat.txt> [--erros] [--puro]")
ARQ, MOSTRAR_ERROS, PURO = args[0], "--erros" in args, "--puro" in args

RX = re.compile(r"^\[(\d+)/(\d+)/(\d+), (\d+):(\d+):(\d+) ([AP]M)\] (?:- )?([^:\n]+?): ([\s\S]*)$")
msgs = []
for i, bloco in enumerate(re.split(r"\n(?=\[\d+/\d+/\d+, )", Path(ARQ).read_text(encoding="utf-8"))):
    m = RX.match(bloco.strip())
    if not m:
        continue
    mo, d, a, h, mi, s, ap, autor, texto = m.groups()
    hh = int(h) % 12 + (12 if ap == "PM" else 0)
    em = datetime(2000 + int(a), int(mo), int(d), hh, int(mi), int(s), tzinfo=SP)
    msgs.append(dict(em=em, autor=autor, texto=texto, admin=autor == "Você", id=f"m{i}"))

SETE_DIAS = timedelta(days=7)
rateios = []


def abertos(ag):
    return [r for r in rateios if r.status == "aberto" and ag - datetime.fromisoformat(r.aberto_em) < SETE_DIAS]


from robo.texto import mesmo_perfume  # noqa: E402


def trocar(velho, novo):
    rateios[:] = [novo if r.id == velho.id else r for r in rateios]


def assinatura(linhas):
    return ",".join(sorted("APC" if l.apc else str(l.ml) for l in linhas))


def dif(a, b):
    a, b = (a.split(",") if a else []), (b.split(",") if b else [])
    return abs(len(a) - len(b)) + len([x for x in a if x not in b])


finais = {}
checagens = iguais = pertos = 0
erros = []
cont = Counter()

for m in msgs:
    autor = Autor(id=m["autor"], msg_id=m["id"], push_name=primeiro_nome(m["autor"]))

    if parece_post(m["texto"]):
        post = ler_post(m["texto"])
        r = next((x for x in abertos(m["em"]) if mesmo_perfume(x.nome, post.nome)), None)
        if r is None:
            r = adotar_lista_do_admin(novo_rateio(post, m["id"], m["em"]), post.linhas_lista)
            r.aberto_em = m["em"].isoformat()
            rateios.append(r)
            continue
        destacar(r, m["em"].isoformat())
        if m["admin"]:
            checagens += 1
            robo, real = assinatura(r.pedidos), assinatura(post.linhas_lista)
            if robo == real:
                iguais += 1
            else:
                if dif(robo, real) <= 1:
                    pertos += 1
                erros.append(f"{m['em']:%Y-%m-%dT%H:%M}  {post.nome}\n    robo:  {robo or '(vazio)'}\n    admin: {real or '(vazio)'}")
            finais[r.id] = (real, robo)
            if not PURO:
                trocar(r, adotar_lista_do_admin(r, post.linhas_lista))
        else:
            res = incorporar_lista_colada(r, post.linhas_lista, autor, m["em"])
            if res.ok:
                trocar(r, res.rateio)
        continue
    if m["admin"]:
        ab = abertos(m["em"])
        if len(ab) > 1:
            citados = [x for x in ab if cita(x, m["texto"])]
            alvo = citados[0] if len(citados) == 1 else None
            if alvo:
                destacar(alvo, m["em"].isoformat())
        continue

    it = interpretar(m["texto"])
    cont[it["tipo"]] += 1
    if it["tipo"] not in ("pedido", "apc", "alterar", "cancelar"):
        continue
    lista = abertos(m["em"])
    dica = (" ".join(i["dica"] for i in it["itens"]) + " " + it.get("resto", "")) if it["tipo"] == "pedido" else it.get("dica")
    r = escolher_rateio(lista, dica=dica) if len(lista) > 1 else None
    citou = r is not None
    r = r or em_foco(lista)
    if r is None:
        continue
    res = aplicar(r, it, autor, m["em"])
    if res.ok:
        if citou:
            destacar(res.rateio, m["em"].isoformat())
        trocar(r, res.rateio)


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


print(f"mensagens de membros: {dict(cont)}")
print(f"rateios abertos na simulacao: {len(rateios)}")
print(f"listas do admin comparadas: {checagens}")
print(f"  identicas:           {iguais} ({pct(iguais, checagens)})")
print(f"  diferenca de 1 item: {pertos} ({pct(pertos, checagens)})")
print(f"  identica ou 1 item:  {pct(iguais + pertos, checagens)}")
fs = [f for f in finais.values() if f[0]]
fin_ig = sum(1 for real, robo in fs if real == robo)
fin_perto = sum(1 for real, robo in fs if real != robo and dif(robo, real) <= 1)
print(f"\nLISTA FINAL de cada perfume ({len(fs)} rateios):")
print(f"  identica: {fin_ig} ({pct(fin_ig, len(fs))})   ate 1 item de diferenca: {pct(fin_ig + fin_perto, len(fs))}")
if MOSTRAR_ERROS:
    print("\n" + "\n".join(erros))
