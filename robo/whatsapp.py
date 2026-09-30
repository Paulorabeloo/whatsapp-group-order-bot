"""Camada fina em cima do neonize (whatsmeow em Python). Tudo que toca o WhatsApp passa por aqui.

O motor nao sabe de protobuf: recebe um `Recebida` simples e chama send_texto/abrir_grupo/etc.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import segno
from neonize.aioze.client import NewAClient
from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv, MessageEv, PairStatusEv
from neonize.proto.Neonize_pb2 import JID
from neonize.utils.jid import build_jid

log = logging.getLogger("whatsapp")


@dataclass
class Recebida:
    msg_id: str
    chat: str            # "1203...@g.us" ou "5519...@s.whatsapp.net"
    autor: str           # jid do autor (pode ser @lid)
    autor_fone: str | None  # so digitos, quando o WhatsApp entrega
    push_name: str
    texto: str
    citado_id: str | None
    apagou_id: str | None   # se for "mensagem apagada", o id da mensagem apagada
    eh_grupo: bool
    de_mim: bool
    tem_imagem: bool
    citado_texto: str | None = None   # texto/legenda da mensagem respondida ("" = foto/figurinha sem texto)


def _jid_str(j: JID) -> str:
    return f"{j.User}@{j.Server}" if j and j.User else ""


def _fone(j: JID) -> str | None:
    return j.User if j and j.Server == "s.whatsapp.net" and j.User.isdigit() else None


def _jid(s: str) -> JID:
    user, _, server = s.partition("@")
    return build_jid(user, server or "s.whatsapp.net")


def _extrair(ev) -> Recebida:
    m = ev.Message
    info = ev.Info
    src = info.MessageSource
    texto, citado, apagou, citado_texto = "", None, None, None
    ci = None
    if m.HasField("conversation"):
        texto = m.conversation
    elif m.HasField("extendedTextMessage"):
        texto = m.extendedTextMessage.text
        ci = m.extendedTextMessage.contextInfo
        citado = ci.stanzaID or None
    elif m.HasField("imageMessage"):
        texto = m.imageMessage.caption or ""
        ci = m.imageMessage.contextInfo
        citado = ci.stanzaID or None
    elif m.HasField("protocolMessage") and m.protocolMessage.type == 0:  # REVOKE
        apagou = m.protocolMessage.key.ID
    if citado and ci is not None and ci.HasField("quotedMessage"):
        q = ci.quotedMessage
        citado_texto = (q.conversation or q.extendedTextMessage.text or q.imageMessage.caption
                        or q.videoMessage.caption or "")
    return Recebida(
        msg_id=info.ID,
        chat=_jid_str(src.Chat),
        autor=_jid_str(src.SenderAlt) or _jid_str(src.Sender),
        autor_fone=_fone(src.SenderAlt) or _fone(src.Sender),
        push_name=info.Pushname or "",
        texto=texto,
        citado_id=citado,
        apagou_id=apagou,
        eh_grupo=src.IsGroup,
        de_mim=src.IsFromMe,
        tem_imagem=m.HasField("imageMessage"),
        citado_texto=citado_texto,
    )


class WhatsApp:
    def __init__(self, sessao: str | Path, ao_receber: Callable[[Recebida], Awaitable[None]]):
        self.client = NewAClient(str(sessao))
        self.ao_receber = ao_receber
        self.qr_svg: str | None = None
        self.qr_em: float = 0.0        # quando o ultimo QR foi gerado (time.time())
        self.conectando = False
        self.conectado = False
        self.caiu_em: float = time.time()   # desde quando esta sem conexao (pro /saude)
        self.meu_jid: str | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._registrar()

    # ------------------------------------------------------------ eventos
    def _registrar(self) -> None:
        c = self.client

        async def qr(_c, dados: bytes):
            self.qr_svg = segno.make_qr(dados).svg_inline(scale=5)
            self.qr_em = time.time()
            log.info("QR novo gerado; abra o painel em /conexao")

        c.qr(qr)

        @c.event(ConnectedEv)
        async def _on(_c, _ev):
            self.conectado, self.qr_svg, self.caiu_em = True, None, 0.0
            try:
                me = await c.get_me()
                self.meu_jid = _jid_str(me.JID)
            except Exception:  # noqa: BLE001
                pass
            log.info("conectado como %s", self.meu_jid)

        @c.event(PairStatusEv)
        async def _pair(_c, ev):
            log.info("pareado: %s", ev)

        @c.event(DisconnectedEv)
        async def _off(_c, _ev):
            self.conectado, self.caiu_em = False, time.time()
            log.warning("desconectado; o neonize reconecta sozinho")

        @c.event(LoggedOutEv)
        async def _out(_c, _ev):
            self.conectado, self.caiu_em = False, time.time()
            log.error("sessao encerrada pelo WhatsApp. Apague data/sessao.db e escaneie de novo")

        @c.event(MessageEv)
        async def _msg(_c, ev):
            try:
                await self.ao_receber(_extrair(ev))
            except Exception:  # noqa: BLE001
                log.exception("erro tratando mensagem")

    async def conectar(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.conectando = True
        try:
            await self.client.connect()
        finally:
            self.conectando = False

    async def vigiar(self) -> None:
        """Sem conexao e sem QR novo ha mais de 1 min (o WhatsApp desiste depois de ~3 min sem scan):
        pede um QR novo. Assim a pagina /conexao sempre tem um codigo vivo."""
        while True:
            await asyncio.sleep(15)
            if self.conectado or self.conectando:
                continue
            if time.time() - self.qr_em > 60:
                self.qr_svg = None
                log.info("login expirou; pedindo QR novo")
                try:
                    await self.conectar()
                except Exception:  # noqa: BLE001
                    log.exception("falha ao reconectar")

    # ------------------------------------------------------------ acoes
    async def grupos(self) -> list[dict]:
        """todos os grupos em que o chip esta: nome, jid, quantidade de participantes, se somos admin"""
        out = []
        meu = (self.meu_jid or "").split("@")[0]
        for g in await self.client.get_joined_groups():
            parts = list(g.Participants)
            eu = next((p for p in parts if p.JID.User == meu or (p.PhoneNumber.User == meu if p.HasField("PhoneNumber") else False)), None)
            out.append({
                "nome": g.GroupName.Name or "(sem nome)",
                "jid": _jid_str(g.JID),
                "pessoas": len(parts),
                "sou_admin": bool(eu and (eu.IsAdmin or eu.IsSuperAdmin)),
                "fechado": bool(g.GroupAnnounce.IsAnnounce),
            })
        return sorted(out, key=lambda x: -x["pessoas"])

    async def admins_do_grupo(self, grupo: str) -> set[str]:
        """Todos os jeitos de identificar os admins do grupo (telefone, jid e lid)."""
        info = await self.client.get_group_info(_jid(grupo))
        ids: set[str] = set()
        for p in info.Participants:
            if not (p.IsAdmin or p.IsSuperAdmin):
                continue
            for j in (p.JID, p.LID, p.PhoneNumber):
                if j and j.User:
                    ids.add(j.User)
                    ids.add(f"{j.User}@{j.Server}")
        return ids

    async def participantes(self, grupo: str) -> list[str]:
        """jid de todo mundo do grupo (menos o proprio robo), no formato que o grupo usa (telefone ou lid)"""
        info = await self.client.get_group_info(_jid(grupo))
        meu = (self.meu_jid or "").split("@")[0]
        return [_jid_str(p.JID) for p in info.Participants if p.JID.User and p.JID.User != meu]

    async def grupo_por_nome(self, nome: str) -> str | None:
        alvo = nome.strip().lower()
        for g in await self.client.get_joined_groups():
            if (g.GroupName.Name or "").strip().lower() == alvo:
                return _jid_str(g.JID)
        return None

    async def enviar_texto(self, para: str, texto: str, mencoes: list[str] | None = None) -> str:
        lids = bool(mencoes) and all(m.endswith("@lid") for m in mencoes)
        ghost = " ".join("@" + m.split("@")[0] for m in mencoes) if mencoes else None
        r = await self.client.send_message(_jid(para), texto, ghost_mentions=ghost, mentions_are_lids=lids)
        return r.ID

    async def enviar_imagem(self, para: str, arquivo: str, legenda: str, mencoes: list[str] | None = None) -> str:
        lids = bool(mencoes) and all(m.endswith("@lid") for m in mencoes)
        ghost = " ".join("@" + m.split("@")[0] for m in mencoes) if mencoes else None
        r = await self.client.send_image(_jid(para), arquivo, caption=legenda, ghost_mentions=ghost, mentions_are_lids=lids)
        return r.ID

    async def reagir(self, chat: str, autor: str, msg_id: str, emoji: str = "👍") -> None:
        msg = await self.client.build_reaction(_jid(chat), _jid(autor), msg_id, emoji)
        await self.client.send_message(_jid(chat), msg)

    async def fechar_grupo(self, grupo: str) -> None:
        """so admins podem enviar mensagem"""
        await self.client.set_group_announce(_jid(grupo), True)

    async def abrir_grupo(self, grupo: str) -> None:
        await self.client.set_group_announce(_jid(grupo), False)

    async def grupo_esta_aberto(self, grupo: str) -> bool:
        info = await self.client.get_group_info(_jid(grupo))
        return not info.GroupAnnounce.IsAnnounce
