"""Estado do robo salvo em disco (data/estado.json). Uma classe so, gravacao atomica.

Guarda: modo, configuracao, rateios, aberturas agendadas e o log das ultimas acoes.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from .rateio import Rateio
from .texto import agora

MODOS = ("desligado", "observando", "sombra", "ao_vivo")

REGRAS_PADRAO = """📌 COMO FUNCIONA O NOSSO GRUPO

Quem anota os pedidos aqui é o robô 🤖. Ele lê o grupo o tempo todo e monta a lista sozinho. Pra ele nunca errar o seu pedido, é assim:

🛍️ PRA PEDIR
Responda o post do perfume e escreva a quantidade. Só isso:
👉 5ml
Se o robô reagir com 👍, tá anotado. A lista atualizada sai em 1 minuto.

🔀 TEM MAIS DE UM PERFUME ABERTO?
Diga qual é. Ou responde o post dele, ou escreve o nome:
👉 5ml do bal
👉 3ml orience
Sem isso, o robô entende que é do perfume que abriu por último.

👑 APC
Responda o post e escreva apc. O primeiro que pedir leva.

✏️ MUDOU DE IDEIA?
Responda o post de novo:
👉 altera pra 10ml ou cancela o meu

⚠️ ATENÇÃO
* Escreva sempre a quantidade. "Quero" sozinho não vale.
* Perfume que já fechou ou que não está na lista do robô: quem anota é o admin. Responda o post dele que a gente cuida.

⏰ ABERTURAS
O grupo fecha 1 hora antes de cada abertura e abre sozinho na hora marcada. Fique de olho no "GRUPO ABERTO 🥂".

Qualquer dúvida, é só chamar um admin. 💎"""


@dataclass
class Config:
    grupo_nome: str = "Minha Loja | Grupo 1"
    grupo_jid: str = ""                      # descoberto pelo nome na primeira conexao
    admins: list[str] = field(default_factory=list)  # telefones com DDI, ex. 5519999999999
    avisar_admin: str = ""                   # telefone que recebe a lista no modo sombra e as duvidas
    segundos_ate_postar_lista: int = 60      # junta os pedidos e posta uma lista so
    reagir_pedido: bool = True
    emoji_reacao: str = "👍"                 # reacao no pedido anotado
    responder_erro_no_grupo: bool = True     # "Restam so X ml" no grupo; se False, so avisa o admin
    aviso_ultimos_ml: int = 10               # "@all So X ml!" quando sobrar isso ou menos
    urgencia_a_cada_min: int = 90            # repete o aviso de ultimos ml a cada N min enquanto nao fecha (0 = so uma vez)
    urgencia_max: int = 4                    # no maximo N avisos por rateio
    chamada_silencio_min: int = 15           # perfume aberto sem nenhuma interacao ha N min: manda chamada (0 = desliga)
    chamada_max: int = 3                     # no maximo N chamadas por perfume
    contagem_min: list[int] = field(default_factory=lambda: [30, 5])
    fechar_antes_min: int = 60               # fecha o grupo N min antes da abertura (0 = nao fecha)
    sem_reply: str = "recente"               # pedido sem reply com varios rateios abertos: "recente" | "perguntar"
    apc_reserva_ml: bool = False             # True = pedidos normais nao podem comer os ml do APC
    folga_abertura_min: int = 30             # 30 min antes/depois de uma abertura, o robo nao fala de outro perfume
    confirmar_sem_reply: bool = True         # pedido sem reply com varios perfumes abertos: "✅ anotado no X" no grupo
    post_do_admin_abre: bool = False         # True = post que o admin manda pelo celular ja abre o rateio; False = entra pausado
    hora_fechar_padrao: str = "22:00"
    regras_texto: str = REGRAS_PADRAO        # "como pedir" pro grupo (vazio = nao manda)
    regras_antes_min: int = 10               # manda as regras N min antes de cada abertura (0 = nao)
    regras_a_cada_h: int = 4                 # e repete ao longo do dia no maximo a cada N horas (0 = so antes da abertura)
    regras_horario: str = "09:00-21:00"      # janela do dia em que a repeticao pode sair
    textos: dict[str, str] = field(default_factory=lambda: {
        "aviso": "💗 ABERTURA DE HOJE, ÀS {hora}!\n\nO {nome} será aberto oficialmente aqui no grupo. ✨\n\n{descricao}\n\n⏰ Abertura às {hora}\n\nQuem quiser garantir o seu decant, fica de olho no grupo. 👀💎",
        "fechar_antes": "Pessoal, vamos fechar o grupo agora e voltamos com a abertura do {nome} às {hora}! Nos vemos daqui a pouco, cheirosos 😄🥰",
        "contagem": "@all {min} min pra abertura do {nome} 💎",
        "aberto": "GRUPO ABERTO 🥂",
        "chamada": "@all O {nome} está aberto! Ainda temos {ml} ml disponíveis 💎",
        "chamada_2": "Bora, acervistas! Quem vai garantir o seu {nome}? {ml} ml esperando por vocês ✨",
        "chamada_3": "@all {ml} ml do {nome} pra fecharmos o frasco e trazer a próxima joia 😉",
        "ultimos": "@all Só {ml} ml disponíveis do {nome} 😱 Quem arremata?",
        "ultimos_2": "@all Somente {ml} ml pra fecharmos o frasco do {nome} 😉✨",
        "ultimos_3": "Restam {ml} ml do {nome}. Quem arremata pra fecharmos e trazer a próxima joia? 💎",
        "fechado_frasco": "❌❌ FRASCO FECHADO ❌❌ {data}",
    })


@dataclass
class Abertura:
    """Uma abertura agendada: o robo abre o grupo, posta o decant e fecha no horario."""
    id: str
    nome: str
    valor_ml: float
    total_ml: int
    minimo: int
    tamanhos: list[int]
    apc_ml: int | None
    abre_em: str            # ISO com fuso
    fecha_em: str           # ISO com fuso
    foto: str | None = None  # caminho em data/fotos/
    texto_extra: str = ""   # frete, pagamento etc. (vai no post)
    status: str = "agendada"  # agendada | contagem | aberta | encerrada | cancelada
    avisos_feitos: list[int] = field(default_factory=list)
    regras_feito: bool = False   # "como pedir" ja saiu antes desta abertura
    rateio_id: str | None = None
    descricao: str = ""          # 1 ou 2 frases sobre o perfume (vai no aviso)
    aviso_em: str | None = None  # ISO; quando mandar o aviso "abertura de hoje"
    aviso_texto: str = ""        # texto final do aviso (ja com nome/hora/descricao)
    aviso_feito: bool = False
    fechou_antes: bool = False   # ja fechou o grupo N min antes da abertura
    abriu_em: str | None = None      # hora REAL em que o grupo abriu e o post saiu
    encerrou_em: str | None = None   # hora REAL em que o frasco fechou

    @property
    def hora_curta(self) -> str:
        """'12h', '18h30'"""
        from datetime import datetime
        d = datetime.fromisoformat(self.abre_em)
        return f"{d.hour}h" if d.minute == 0 else f"{d.hour}h{d.minute:02d}"

    def post_texto(self, quando: "datetime | None" = None) -> str:
        """quando = hora real da abertura (o "Abrir agora" pode adiantar a data agendada)"""
        from datetime import datetime
        data = (quando or datetime.fromisoformat(self.abre_em)).strftime("%d/%m/%Y")
        titulo = self.nome if not self.nome[:1].isalnum() else f"✨ {self.nome}"
        linhas = [data, "", titulo, "", f"Valor por ml: R$ {self.valor_ml:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), f"Pedido mínimo: {self.minimo} ml", "", "VALORES DOS DECANTS", ""]
        # o APC sempre entra no post, mesmo quando o tamanho dele nao foi marcado na lista de tamanhos
        for t in sorted(set(self.tamanhos) | ({self.apc_ml} if self.apc_ml else set())):
            preco = f"R$ {t * self.valor_ml:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if t == self.apc_ml:
                linhas.append(f"👑 {t} ml: {preco} | O primeiro que pedir leva o APC")
            elif t == 5:
                linhas.append(f"💎 {t} ml: {preco} | MAIS SOLICITADO")
            else:
                linhas.append(f"💎 {t} ml: {preco}")
        if self.texto_extra.strip():
            linhas += ["", self.texto_extra.strip()]
        linhas += ["", f"QUANTIDADE DO FRASCO: {self.total_ml} ml"]
        return "\n".join(linhas)


@dataclass
class Estado:
    modo: str = "desligado"
    config: Config = field(default_factory=Config)
    rateios: list[Rateio] = field(default_factory=list)
    aberturas: list[Abertura] = field(default_factory=list)
    grupo_aberto: bool | None = None  # None = nao sabemos ainda
    regras_enviadas_em: str | None = None   # ultima vez que o "como pedir" saiu no grupo
    log: list[dict] = field(default_factory=list)
    aprender: list[dict] = field(default_factory=list)  # casos pra revisar: duvida, divergencia com o admin, correcao manual
    perfumes_vistos: list[str] = field(default_factory=list)  # todo perfume ja postado (fica mesmo se o rateio for excluido)

    def rateios_abertos(self) -> list[Rateio]:
        return [r for r in self.rateios if r.status == "aberto"]

    def rateio(self, rid: str) -> Rateio | None:
        return next((r for r in self.rateios if r.id == rid), None)

    def abertura(self, aid: str) -> Abertura | None:
        return next((a for a in self.aberturas if a.id == aid), None)

    def para_aprender(self, tipo: str, texto: str, **extra) -> dict:
        """Guarda um caso pra revisao humana na aba Aprender (duvida | divergencia | correcao)."""
        item = {"id": novo_id(), "em": agora().isoformat(timespec="seconds"), "tipo": tipo, "texto": texto[:600],
                "status": "registrado" if tipo == "correcao" else "pendente", "rotulo": None, **extra}
        self.aprender.insert(0, item)
        del self.aprender[500:]
        return item

    def resolver_divergencias(self, r: "Rateio") -> None:
        """Divergencia pendente desse perfume some quando a lista do robo passa a bater com a do admin (ou ele fecha)."""
        robo = sorted(("APC" if p.apc else str(p.ml)) + " " + p.nome for p in r.pedidos)
        for a in self.aprender:
            if a["tipo"] == "divergencia" and a["status"] == "pendente" and a.get("perfume") == r.nome:
                if r.status != "aberto" or sorted(x.split(" ")[0] for x in robo) == sorted(x.split(" ")[0] for x in a.get("admin", [])):
                    a["status"], a["rotulo"] = "resolvido", "lista bateu"

    def registrar(self, tipo: str, texto: str) -> None:
        self.log.insert(0, {"em": agora().isoformat(timespec="seconds"), "tipo": tipo, "texto": texto[:300]})
        del self.log[300:]


class Armazem:
    """Carrega e salva o Estado. Thread-safe porque o WhatsApp chama de outra thread."""

    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.estado = self._carregar()

    def _carregar(self) -> Estado:
        if not self.caminho.exists():
            return Estado()
        try:
            d = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # arquivo corrompido (queda de energia no meio da gravacao): guarda pra pericia e sobe zerado
            quebrado = self.caminho.with_suffix(".json.corrompido")
            os.replace(self.caminho, quebrado)
            return Estado()
        cfg = Config(**{**asdict(Config()), **d.get("config", {})})
        return Estado(
            modo=d.get("modo", "desligado"),
            config=cfg,
            rateios=[Rateio.from_dict(r) for r in d.get("rateios", [])],
            aberturas=[Abertura(**a) for a in d.get("aberturas", [])],
            grupo_aberto=d.get("grupo_aberto"),
            regras_enviadas_em=d.get("regras_enviadas_em"),
            log=d.get("log", []),
            aprender=d.get("aprender", []),
            perfumes_vistos=d.get("perfumes_vistos", []),
        )

    def salvar(self) -> None:
        with self._lock:
            tmp = self.caminho.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self.estado), ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.caminho)

    def __enter__(self):
        self._lock.acquire()
        return self.estado

    def __exit__(self, *exc):
        try:
            if exc[0] is None:
                self.salvar()
        finally:
            self._lock.release()


def novo_id() -> str:
    return uuid.uuid4().hex[:8]
