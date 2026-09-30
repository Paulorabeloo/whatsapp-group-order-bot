"""Regras do rateio. Funcoes puras: recebem o estado, devolvem o resultado. Sem WhatsApp aqui."""

from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

from .post import Post, LinhaLista
from .texto import normalizar, palavras_chave, primeiro_nome, data_br, agora as _agora


@dataclass
class Pedido:
    autor_id: str | None
    msg_id: str | None
    em: str
    nome: str
    ml: int
    apc: bool = False


@dataclass
class Rateio:
    id: str
    post_msg_id: str | None
    nome: str
    valor_ml: float
    minimo: int
    total_ml: int
    apc_ml: int | None
    tamanhos: list[int]
    cabecalho: str
    status: str = "aberto"  # aberto | fechado
    aberto_em: str = ""
    fechado_em: str | None = None
    lista_msg_ids: list[str] = field(default_factory=list)
    pedidos: list[Pedido] = field(default_factory=list)
    urgencias: int = 0                     # quantos avisos de "ultimos ml" ja sairam
    ultima_urgencia_em: str | None = None
    chamadas: int = 0                      # quantas chamadas de "sem interacao" ja sairam
    destaque_em: str | None = None         # ultima vez que o perfume foi o assunto (post, lista, urgencia, citado)
    ultima_chamada_em: str | None = None
    lista_pendente: bool = False           # mudou e a lista ainda nao saiu (sobrevive a reinicio)
    origem: str = "sistema"                # "sistema" (agendado/aberto no painel) | "admin" (post mandado no grupo pelo celular)

    @property
    def ultimo_movimento_em(self) -> str:
        """abertura ou ultimo pedido, o que for mais recente"""
        return max([self.aberto_em] + [p.em for p in self.pedidos])

    # --- leituras
    @property
    def reservado(self) -> int:
        return sum(p.ml for p in self.pedidos)

    @property
    def disponivel(self) -> int:
        return self.total_ml - self.reservado

    @property
    def dono_apc(self) -> Pedido | None:
        return next((p for p in self.pedidos if p.apc), None)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Rateio":
        d = dict(d)
        d["pedidos"] = [Pedido(**p) for p in d.get("pedidos", [])]
        return Rateio(**d)


@dataclass
class Autor:
    id: str
    msg_id: str | None = None
    push_name: str | None = None


@dataclass
class Resultado:
    rateio: Rateio
    ok: bool
    resposta: str | None = None
    novas: list = field(default_factory=list)


def novo_rateio(post: Post, post_msg_id: str | None, agora: datetime | None = None) -> Rateio:
    return Rateio(
        id=uuid.uuid4().hex[:10],
        post_msg_id=post_msg_id,
        nome=post.nome,
        valor_ml=post.valor_ml,
        minimo=post.minimo,
        total_ml=post.total_ml,
        apc_ml=post.apc_ml,
        tamanhos=list(post.tamanhos),
        cabecalho=post.cabecalho,
        aberto_em=(agora or _agora()).isoformat(),
    )


def em_foco(abertos: list[Rateio]) -> Rateio | None:
    """O perfume que esta "na vez": o ultimo que teve post, lista, urgencia, chamada ou foi citado pelo nome.
    No grupo ficam em media 3 perfumes abertos ao mesmo tempo; o "5ml" solto e do que esta em destaque."""
    if not abertos:
        return None
    # abriu um perfume nos ultimos 30 min: o que aconteceu ANTES dessa abertura nao conta mais
    # (o Bal citado de manha nao rouba o destaque do que abriu as 11h); citacoes depois da abertura continuam valendo
    ultima = max(r.aberto_em for r in abertos)
    if ultima >= (_agora() - timedelta(minutes=30)).isoformat():
        return max(abertos, key=lambda r: (max(r.destaque_em or "", r.aberto_em) if max(r.destaque_em or "", r.aberto_em) >= ultima else ""))
    return max(abertos, key=lambda r: max(r.destaque_em or "", r.aberto_em))


def rateio_da_mensagem(todos: list[Rateio], msg_id: str | None) -> Rateio | None:
    """De qual perfume e essa mensagem? (post, lista, urgencia/chamada do robo, ou pedido de alguem)"""
    if not msg_id:
        return None
    for r in todos:
        if r.post_msg_id == msg_id or msg_id in r.lista_msg_ids or any(p.msg_id == msg_id for p in r.pedidos):
            return r
    return None


_CURTAS_COMUNS = {"for", "the", "and", "des", "del", "les", "eau", "sur", "von", "one", "her", "his", "you", "dos", "das", "com"}


def chaves(nome: str) -> set[str]:
    """palavras que identificam o perfume: as de 4+ letras e os apelidos curtos do nome ("BAL", "ANI", "OUD")"""
    perfume = normalizar(nome.split("|")[0])
    curtas = {p for p in re.findall(r"[a-z]{3}\b", perfume) if re.fullmatch(r"[a-z]{3}", p) and p not in _CURTAS_COMUNS}
    curtas = {p for p in curtas if re.search(rf"(?<![a-z]){p}(?![a-z])", perfume)}
    return set(palavras_chave(nome)) | curtas


def cita(r: Rateio, texto: str) -> bool:
    """O texto fala desse perfume pelo nome?"""
    return bool(set(re.findall(r"[a-z0-9]+", normalizar(texto))) & chaves(r.nome))


def destacar(r: Rateio, quando: str) -> None:
    if not r.destaque_em or quando > r.destaque_em:
        r.destaque_em = quando


def escolher_rateio(abertos: list[Rateio], citado_id: str | None = None, dica: str | None = None) -> Rateio | None:
    """Qual rateio aberto essa mensagem quis dizer? None = nao da pra saber."""
    if not abertos:
        return None
    if citado_id:
        for r in abertos:
            if r.post_msg_id == citado_id or citado_id in r.lista_msg_ids or any(p.msg_id == citado_id for p in r.pedidos):
                return r
    if dica:
        palavras = set(re.findall(r"[a-z0-9]+", normalizar(dica)))
        casam = [r for r in abertos if palavras & chaves(r.nome)]
        if len(casam) == 1:
            return casam[0]
    return abertos[0] if len(abertos) == 1 else None


# palavras que aparecem depois de "do/da/de" e NAO sao nome de perfume
_NAO_PERFUME = {"frasco", "perfume", "decant", "decants", "grupo", "loja", "lista", "pedido", "apc", "valor", "mesmo", "mesma",
                "esse", "essa", "este", "esta", "minha", "minhas", "meus", "sobra", "vez", "casa", "vida",
                "maior", "menor", "outro", "outra", "hoje", "ontem", "amanha", "semana", "manha", "tarde", "noite",
                "vcs", "voces", "todos", "todas", "novo", "nova", "ultimo", "ultima", "primeiro", "primeira", "dele", "dela"}


def outro_perfume(texto: str, abertos: list[Rateio], todos: list[Rateio], vistos: list[str] = ()) -> Rateio | bool | None:
    """A mensagem fala de um perfume que NAO esta aberto?
    Devolve o Rateio fechado que ela cita (pra responder "ja fechou"), True se cita um nome desconhecido
    ("5ml do vibrato"), ou None se nao cita outro perfume (segue o fluxo normal)."""
    import re
    t = normalizar(texto)
    palavras = set(re.findall(r"[a-z]{4,}", t))
    chaves_abertas = {p for r in abertos for p in chaves(r.nome)}
    if palavras & chaves_abertas:
        return None  # cita um perfume aberto: o fluxo normal resolve
    for r in todos:
        if r.status != "aberto" and palavras & set(palavras_chave(r.nome)):
            return r
    for m in re.finditer(r"\b(?:do|da|de|desse|dessa)\s+([a-z]{4,})", t):
        if m.group(1) not in _NAO_PERFUME:
            return True
    # cita um perfume/marca conhecido que nao esta aberto ("3ml vibrato", "5ml creed imperial"): nao e do aberto
    from .catalogo import palavras_de_perfume
    conhecidas = palavras_de_perfume([*vistos, *(r.nome for r in todos)]) - chaves_abertas
    if set(re.findall(r"[a-z]{3,}", t)) & conhecidas:
        return True
    return None


def _nome_exibicao(r: Rateio, nome_escrito: str | None, push_name: str | None) -> str:
    """tira do nome escrito as palavras que sao do perfume ("5 ml sospiro vibrato" nao e nome de gente)"""
    if nome_escrito:
        chaves = set(palavras_chave(r.nome))
        sobra = [p for p in nome_escrito.split() if normalizar(p) not in chaves]
        if sobra:
            return " ".join(sobra)
    return primeiro_nome(push_name) or "Acervista"


def aplicar(original: Rateio, intencao: dict, autor: Autor, agora: datetime | None = None) -> Resultado:
    """Aplica a intencao de um membro. Nao altera `original`.
    `resposta` e o texto curto pra responder no grupo quando algo nao deu (ou None)."""
    r = copy.deepcopy(original)
    ag = agora or _agora()

    def falha(resposta: str | None) -> Resultado:
        return Resultado(rateio=original, ok=False, resposta=resposta)

    if r.status != "aberto":
        return falha(f"O {r.nome} já está fechado 🙏")

    tipo = intencao["tipo"]
    if tipo == "pedido":
        nome = _nome_exibicao(r, intencao.get("nome"), autor.push_name)
        novos = [it["ml"] for it in intencao["itens"] for _ in range(it.get("qtd", 1))]
        livre = r.disponivel
        # sobra menor que o minimo: quem pedir exatamente a sobra leva (fecha o frasco)
        pega_a_sobra = len(novos) == 1 and novos[0] == livre and 0 < livre < r.minimo
        # "7" sem "ml": vale qualquer quantidade a partir do minimo (o pessoal pede valor quebrado tambem)
        if intencao.get("sem_unidade") and not pega_a_sobra and any(ml < r.minimo or ml > r.total_ml for ml in novos):
            return falha(None)
        if not pega_a_sobra and any(ml < r.minimo for ml in novos):
            return falha(f"O pedido mínimo é {r.minimo} ml 🙂")
        if sum(novos) > livre:
            return falha(f"Restam só {livre} ml do {r.nome} 🙏" if livre > 0 else f"O {r.nome} esgotou 🙏")
        dono = r.dono_apc
        if dono and autor.id and dono.autor_id == autor.id:
            dono.ml += sum(novos)   # quem tem o APC e pede mais: soma na linha do APC ("APC + 40 ml"), nao vira outra linha
            dono.msg_id = autor.msg_id
        else:
            for ml in novos:
                r.pedidos.append(Pedido(autor.id, autor.msg_id, ag.isoformat(), nome, ml))

    elif tipo == "apc":
        if not r.apc_ml:
            return falha(None)  # post sem APC: deixa pro admin
        dono = r.dono_apc
        if dono:
            return falha(None if dono.autor_id == autor.id else "O APC já foi reservado 💎")
        if r.disponivel < r.apc_ml:
            return falha(f"Não sobrou ml suficiente pro APC ({r.disponivel} ml livres) 🙏")
        r.pedidos.append(Pedido(autor.id, autor.msg_id, ag.isoformat(), _nome_exibicao(r, intencao.get("nome"), autor.push_name), r.apc_ml, apc=True))

    elif tipo == "alterar":
        meus = [p for p in r.pedidos if p.autor_id == autor.id and not p.apc]
        if not meus:
            return aplicar(original, {"tipo": "pedido", "itens": [{"ml": intencao["ml"], "qtd": 1}]}, autor, ag)
        if intencao.get("mais") and intencao["mais"] >= r.minimo:
            # "mais 5ml": linha nova, como os admins fazem na lista (historico)
            return aplicar(original, {"tipo": "pedido", "itens": [{"ml": intencao["mais"], "qtd": 1}]}, autor, ag)
        if intencao.get("mais"):
            # "quero mais 2 ml" (abaixo do minimo): soma no ultimo pedido da pessoa
            intencao = {**intencao, "ml": max(meus, key=lambda p: p.em).ml + intencao["mais"]}
        elif intencao.get("total") and len(meus) > 1:
            # "o meu aqui e so 3ml": a pessoa fica com UM pedido de N ml (os outros saem)
            fica = min(meus, key=lambda p: p.em)
            r.pedidos = [p for p in r.pedidos if p is fica or p not in meus]
            meus = [fica]
        alvo = max(meus, key=lambda p: p.em)  # mais de um decant: muda o ultimo que a pessoa pediu
        if intencao["ml"] < r.minimo:
            return falha(f"O pedido mínimo é {r.minimo} ml 🙂")
        if intencao["ml"] - alvo.ml > r.disponivel:
            return falha(f"Restam só {r.disponivel} ml do {r.nome} 🙏")
        alvo.ml = intencao["ml"]
        alvo.msg_id = autor.msg_id

    elif tipo == "cancelar":
        antes = len(r.pedidos)
        r.pedidos = [p for p in r.pedidos if p.autor_id != autor.id]
        if len(r.pedidos) == antes:
            return falha(None)
    else:
        return falha(None)

    if r.disponivel <= 0:
        r.status, r.fechado_em = "fechado", ag.isoformat()
    return Resultado(rateio=r, ok=True)


def ajustar_apc(original: Rateio, autor_id: str, texto: str, agora: datetime | None = None) -> Resultado | None:
    """Dono do APC mudando o tamanho: "30 +10ml" (soma) ou "APC de 35+5=40 ml" (total depois do =).
    Devolve None quando a pessoa nao e dona do APC desse perfume ou a mensagem nao tem "+N"/"=N"."""
    dono = original.dono_apc
    if not dono or not autor_id or dono.autor_id != autor_id:
        return None
    t = texto.lower()
    igual = re.findall(r"=\s*(\d{1,3})", t)
    mais = [int(x) for x in re.findall(r"\+\s*(\d{1,3})", t)]
    if igual:
        total = int(igual[-1])
    elif mais:
        total = dono.ml + sum(mais)
    else:
        return None
    if total <= dono.ml:
        return None
    if total - dono.ml > original.disponivel:
        return Resultado(rateio=original, ok=False, resposta=f"Restam só {original.disponivel} ml do {original.nome} 🙏")
    r = copy.deepcopy(original)
    r.dono_apc.ml = total
    if r.disponivel <= 0:
        r.status, r.fechado_em = "fechado", (agora or _agora()).isoformat()
    return Resultado(rateio=r, ok=True)


def remover_por_msg(original: Rateio, msg_id: str) -> Rateio | None:
    """Mensagem apagada: tira o pedido que veio dela."""
    if not any(p.msg_id == msg_id for p in original.pedidos):
        return None
    r = copy.deepcopy(original)
    r.pedidos = [p for p in r.pedidos if p.msg_id != msg_id]
    if r.status == "fechado" and r.disponivel > 0:
        r.status, r.fechado_em = "aberto", None
    return r


def _chave(l) -> str:
    return f"{'APC' if l.apc else l.ml}|{primeiro_nome(l.nome)}"


def incorporar_lista_colada(original: Rateio, linhas: list[LinhaLista], autor: Autor, agora: datetime | None = None) -> Resultado:
    """Membro copiou a lista e colou com a linha dele no fim. Entra so o que e novo.
    Se veio exatamente 1 linha nova, ela e do autor (vira mencao); senao ficam so os nomes."""
    existentes = [_chave(p) for p in original.pedidos]
    novas: list[LinhaLista] = []
    for l in linhas:
        k = _chave(l)
        if k in existentes:
            existentes.remove(k)
        else:
            novas.append(l)
    if not novas:
        return Resultado(rateio=original, ok=False, novas=[])
    r = original
    eh_do_autor = len(novas) == 1
    for l in novas:
        quem = Autor(id=autor.id if eh_do_autor else None, msg_id=autor.msg_id, push_name=l.nome)
        intencao = {"tipo": "apc", "nome": l.nome} if l.apc else {"tipo": "pedido", "itens": [{"ml": l.ml, "qtd": 1}], "nome": l.nome}
        res = aplicar(r, intencao, quem, agora)
        if not res.ok:
            return Resultado(rateio=original, ok=False, resposta=res.resposta, novas=novas)
        r = res.rateio
    return Resultado(rateio=r, ok=True, novas=novas)


def adotar_lista_do_admin(original: Rateio, linhas: list[LinhaLista]) -> Rateio:
    """Admin postou a lista na mao: o robo adota a lista dele (o admin sempre manda)."""
    r = copy.deepcopy(original)
    sobrando = list(r.pedidos)
    novos: list[Pedido] = []
    for l in linhas:
        antigo = next((p for p in sobrando if p.apc == l.apc and primeiro_nome(p.nome) == primeiro_nome(l.nome)), None)
        if antigo:
            sobrando.remove(antigo)
        novos.append(Pedido(
            autor_id=antigo.autor_id if antigo else None,
            msg_id=antigo.msg_id if antigo else None,
            em=antigo.em if antigo else _agora().isoformat(),
            nome=l.nome,
            ml=(l.ml or r.apc_ml) if l.apc else l.ml,   # "APC + 40ml" na lista do admin vale 40
            apc=l.apc,
        ))
    r.pedidos = novos
    r.status = "fechado" if r.disponivel <= 0 else "aberto"
    return r


def renderizar(r: Rateio, agora: datetime | None = None) -> tuple[str, list[str]]:
    """Texto da lista no formato que o grupo ja usa. Devolve (texto, mencoes)."""
    mencoes: list[str] = []

    def marca(p: Pedido) -> str:
        if not p.autor_id:
            return ""
        mencoes.append(p.autor_id)
        return f" @{p.autor_id.split('@')[0]}"

    partes = [r.cabecalho, ""]
    if r.apc_ml:
        dono = r.dono_apc
        partes.append(f"👑 {dono.nome} | APC + {dono.ml} ml 👑{marca(dono)}" if dono else f"👑 APC + {r.apc_ml} ml disponível 👑")
        partes.append("")
    for p in r.pedidos:
        if not p.apc:
            partes.append(f"💎 {p.ml}ml - {p.nome}{marca(p)}")
    partes.append("")

    livre = r.disponivel
    if r.status == "fechado" or livre <= 0:
        partes.append(f"❌❌ FRASCO FECHADO ❌❌ {data_br(agora)}")
    else:
        partes.append(f"Disponível {livre} ml" + (" incluindo APC" if r.apc_ml and not r.dono_apc else ""))

    texto = "\n".join(partes)
    while "\n\n\n" in texto:
        texto = texto.replace("\n\n\n", "\n\n")
    return texto, list(dict.fromkeys(mencoes))
