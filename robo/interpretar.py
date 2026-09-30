"""Entende a mensagem de um membro do grupo.

Calibrado com o historico real (22/06 a 04/09/2026): ~80% dos pedidos sao
"5ml", "3 ml", "quero 5ml", "apc", "vera 3". O resto vira 'duvida' e nunca mexe na lista sozinho.

Retorno (dict):
  {tipo: 'pedido',   itens: [{ml, qtd, dica}], nome, resto, sem_unidade}
  {tipo: 'apc',      dica, nome}
  {tipo: 'alterar',  ml, dica}
  {tipo: 'cancelar', dica}
  {tipo: 'lista'}                 membro colou a lista inteira (quem trata e o post.ler_linhas_lista)
  {tipo: 'duvida',   motivo}      tem cara de pedido mas nao da pra ter certeza
  {tipo: 'nada'}                  conversa, figurinha, bolao...
"""

from __future__ import annotations

import re

from .texto import normalizar

ML_MIN, ML_MAX = 1, 200

RE_CANCELAR = re.compile(r"\b(cancel\w*|desist\w*|pode tirar|tira o meu|tira meu|tirar o meu|retir\w+ (?:o )?meu|nao vou (?:mais )?querer|remove\w* (?:o )?meu)\b")
RE_ALTERAR = re.compile(r"\b(alter\w*|aument\w*|mud\w*|troc\w*|diminu\w*|ajust\w*)\b")
# "o meu aqui e so 3ml", "pra ficar 5ml", "ficar com 10": o TOTAL da pessoa nesse perfume passa a ser N
RE_TOTAL = re.compile(r"\b(?:so|somente|apenas)\s+(\d{1,3})\s*mls?\b|\b(?:pra|para) ficar\s+(?:com\s+)?(\d{1,3})|\bficar com\s+(\d{1,3})"
                      r"|\bfica\s+(?:com\s+)?(\d{1,3})\s*mls?\b"
                      r"|\bo meu (?:aqui )?e (?:so )?(\d{1,3})")
# "quero mais 2 ml dele": soma no pedido que a pessoa ja tem
RE_MAIS = re.compile(r"\bmais\s+(\d{1,3})\s*mls?\b")
RE_APC = re.compile(r"\bapc\b")
# "2x 5ml" = dois decants de 5 ml; "5ml", "5 ml", "5mls"
RE_ITEM = re.compile(r"(?:\b(\d)\s*x\s*)?\b(\d{1,3})\s*(?:ml|mls|m l)\b")
# placar de bolao: "brasil 2 x 1 noruega", "Brasil 2 x 1Noruega" (sem ml)
RE_PLACAR = re.compile(r"\b\d+\s*x\s*\d+")
# fala de ml mas nao e pedido: "falta 17ml pra fechar", "temos so 16ml", "tenho 3", "o APC ta disponivel ainda"
RE_NAO_E_PEDIDO = re.compile(r"\b(falta|faltam|temos|restam|resta|restante|somente|so tem|tenho \d|ja saiu|disponive\w*|voce pediu|pediu|ontem|nota \d+|milh\w+|mil|reais|r\$|horas?|minutos?|min)\b")
# enfeites das listas coladas ("✨30 ml APC MURILO ✨", "⭐ 5ml Giorgia")
RE_ENFEITE_LISTA = re.compile("[✨💫⭐💎🏆👑🫅]")
RE_QUERO_SOZINHO = re.compile(r"^(?:eu )?quero(?: tambem| tbm)?[!. ]*$")

PALAVRAS_VAZIAS = set("""
quero eu por favor pfv pvf pfvr porfavor pf pls obrigado obrigada obg bom dia boa tarde noite de do da dos das desse dessa
esse essa este esta tbm tb tambem pra para mim me ve vou querer ficar fico com o a os as meu minha
gente peguei oi ola ei tenho interesse um uma e ai entao testar experimentar perfume decant ok sim
restante fechar frasco mais so apenas pode ser reserva reservar reserve anota anotar coloca coloque
conhecer provar sentir presentear presente
no na nos nas em ml mls apc aqui la ja agora hoje amei lindo linda maravilhoso que quanto
""".split())


def _limpar_linha(l: str) -> str:
    return re.sub(r"\s+", " ", normalizar(l).replace("|", " ")).strip()


def _sobras(s: str) -> list[str]:
    """palavras que sobraram depois de tirar numeros, "ml" e palavras vazias"""
    s = RE_ITEM.sub(" ", s)
    s = re.sub(r"\d+", " ", s)
    return [p for p in re.split(r"[\s,.\-!/+]+", s) if p and p.isalpha() and len(p) >= 2 and p not in PALAVRAS_VAZIAS]


def _nome_das_sobras(palavras: list[str]) -> str | None:
    """Se sobrou 1 a 3 palavras que parecem nome ("vera", "gustavo ozaki"), devolve capitalizado."""
    if not palavras or len(palavras) > 3:
        return None
    return " ".join(p[:1].upper() + p[1:] for p in palavras)


def interpretar(texto_original: str | None) -> dict:
    if not texto_original or not isinstance(texto_original, str):
        return {"tipo": "nada"}
    bruto = texto_original.strip()
    if not bruto or bruto.startswith("<"):  # <figurinha omitida> etc. no export
        return {"tipo": "nada"}

    # lista colada por membro
    linhas_ml = [l for l in bruto.split("\n") if re.search(r"\d\s*ml", l, re.I)]
    if len(linhas_ml) >= 3 or (linhas_ml and RE_ENFEITE_LISTA.search(bruto) and "\n" in bruto):
        return {"tipo": "lista"}

    # pergunta ("ainda tem torino 5?") e comentario ("falta 17ml pra fechar") nao contam como pedido
    linhas = [x for x in (_limpar_linha(l) for l in re.split(r"\n+", bruto)) if x]
    # "pode aumentar o meu pra 10ml?" e pedido mesmo com interrogacao; "ainda tem 5?" nao e
    afirmativas = [l for l in linhas if ("?" not in l or RE_ALTERAR.search(l) or RE_TOTAL.search(l) or RE_MAIS.search(l)) and (not RE_NAO_E_PEDIDO.search(l) or re.search(r"\bquero\b", l))]
    if not afirmativas:
        # "Mefisto ainda aberto? Se sim poderia reservar 3ml ?": e pedido em forma de pergunta; o admin decide
        if any("?" in l and re.search(r"\d\s*ml", l) and re.search(r"reserv|poderia|pode|separa|quero|queria", l) for l in linhas):
            return {"tipo": "duvida", "motivo": "pedido em forma de pergunta"}
        return {"tipo": "nada"}
    t = " \n ".join(afirmativas)

    tem_ml = re.search(r"\d\s*(ml|mls)\b", t) is not None
    if not tem_ml and RE_PLACAR.search(t):
        return {"tipo": "nada"}  # bolao

    if (m := RE_TOTAL.search(t)) and not RE_APC.search(t):
        ml = int(next(g for g in m.groups() if g))
        if ML_MIN <= ml <= ML_MAX:
            return {"tipo": "alterar", "ml": ml, "total": True, "dica": " ".join(_sobras(t))}
    if (m := RE_MAIS.search(t)) and not RE_APC.search(t) and len(re.findall(r"\b\d{1,3}\b", t)) == 1:
        return {"tipo": "alterar", "mais": int(m.group(1)), "ml": int(m.group(1)), "dica": " ".join(_sobras(t))}

    if RE_CANCELAR.search(t):
        return {"tipo": "cancelar", "dica": " ".join(_sobras(t))}

    if len(bruto) > 160 or len(_sobras(t)) > 4:
        # comeca com um pedido claro e depois vira conversa: vale o comeco ("Quero 10ml. Minha irma amou...")
        primeira = re.split(r"[.!\n]", bruto.strip(), maxsplit=1)[0].strip()
        if primeira and primeira != bruto.strip() and len(primeira) <= 40:
            it = interpretar(primeira)
            if it["tipo"] in ("pedido", "apc") and not it.get("nome"):
                return it
        if tem_ml or RE_APC.search(t):
            return {"tipo": "duvida", "motivo": "mensagem longa"}
        return {"tipo": "nada"}

    if RE_ALTERAR.search(t):
        nums = [int(m.group(1)) for m in re.finditer(r"\b(\d{1,3})\s*(?:ml|mls)?\b", t)]
        ml = nums[-1] if nums else None
        if ml and ML_MIN <= ml <= ML_MAX:
            return {"tipo": "alterar", "ml": ml, "dica": " ".join(_sobras(t))}
        return {"tipo": "duvida", "motivo": "pediu alteracao sem numero claro"}

    if RE_APC.search(t):
        # "quero o apc", "apc", "10ml apc Murilo" (o tamanho do APC e fixo no post, o numero e ignorado)
        resto = _sobras(t)
        if len(resto) > 3:
            return {"tipo": "duvida", "motivo": "fala de APC no meio de conversa"}
        return {"tipo": "apc", "dica": " ".join(resto), "nome": _nome_das_sobras(resto)}

    # itens com "ml": cada um leva as palavras que vem depois dele como dica de perfume
    achados = list(RE_ITEM.finditer(t))
    if achados:
        itens = []
        for i, m in enumerate(achados):
            ml, qtd = int(m.group(2)), int(m.group(1) or 1)
            if not (ML_MIN <= ml <= ML_MAX) or not (1 <= qtd <= 5):
                return {"tipo": "duvida", "motivo": f"quantidade estranha: {m.group(0)}"}
            fim = achados[i + 1].start() if i + 1 < len(achados) else len(t)
            itens.append({"ml": ml, "qtd": qtd, "dica": " ".join(_sobras(t[m.end():fim]))})
        resto = _sobras(t)
        return {"tipo": "pedido", "itens": itens, "nome": _nome_das_sobras(resto), "resto": " ".join(resto), "sem_unidade": False}

    # numero solto: "3", "5", "vera 3", "quero 5". So em mensagem curta.
    palavras = t.split()
    soltos = [int(m.group(1)) for m in re.finditer(r"\b(\d{1,3})\b", t)]
    if len(soltos) == 1 and len(palavras) <= 4 and 1 <= soltos[0] <= ML_MAX:
        resto = _sobras(t)
        return {"tipo": "pedido", "itens": [{"ml": soltos[0], "qtd": 1, "dica": ""}], "nome": _nome_das_sobras(resto), "resto": " ".join(resto), "sem_unidade": True}

    # "quero" sem numero: pode ser APC numa venda so de APC, ou nao. Nao arrisca.
    if RE_QUERO_SOZINHO.match(t):
        return {"tipo": "duvida", "motivo": "quero sem quantidade"}

    return {"tipo": "nada"}
