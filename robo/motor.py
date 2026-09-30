"""O motor: liga WhatsApp + regras do rateio + agenda.

- mensagem no grupo → interpretar → aplicar → agenda a lista (junta pedidos por N segundos)
- post do admin → abre rateio novo ou adota a lista dele
- relogio (a cada 15 s) → contagem regressiva, abrir grupo + postar, aviso de ultimos ml, fechar grupo

Modos: desligado (so le), sombra (manda a lista pro admin no privado), ao_vivo (posta no grupo).
"""

from __future__ import annotations

import asyncio
import re
import logging
from datetime import datetime

from .estado import Abertura, Armazem, novo_id
from .ia import IA
from .interpretar import interpretar
from .post import Post, ler_post, parece_post
from .rateio import (Autor, Rateio, Resultado, adotar_lista_do_admin, ajustar_apc, aplicar, cita, destacar, rateio_da_mensagem, em_foco, escolher_rateio, incorporar_lista_colada, outro_perfume,
                     novo_rateio, remover_por_msg, renderizar)
from .texto import SP, agora, data_br, mesmo_perfume, normalizar, palavras_chave
from .whatsapp import Recebida, WhatsApp

log = logging.getLogger("motor")


class Motor:
    def __init__(self, armazem: Armazem, wa: WhatsApp):
        self.arm = armazem
        self.wa = wa
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._admins_grupo: set[str] = set()   # admins de verdade do grupo, lidos do WhatsApp
        self._todos: list[str] = []            # todos os participantes (pro "@all")
        self.ia = IA()

    # ------------------------------------------------------------ util
    @property
    def cfg(self):
        return self.arm.estado.config

    async def _regras_do_dia(self, est, ag: datetime) -> None:
        """Repete o "como pedir" ao longo do dia, sem virar spam: no maximo a cada N horas, dentro do horario,
        com o grupo aberto, algum perfume aberto e pelo menos um pedido novo desde a ultima vez."""
        cfg = self.cfg
        if not cfg.regras_texto.strip() or cfg.regras_a_cada_h <= 0 or not est.grupo_aberto or not est.rateios_abertos():
            return
        try:
            ini, fim = cfg.regras_horario.split("-")
            h_ini = tuple(int(x) for x in ini.split(":")); h_fim = tuple(int(x) for x in fim.split(":"))
        except ValueError:
            h_ini, h_fim = (9, 0), (21, 0)
        if not (h_ini <= (ag.hour, ag.minute) <= h_fim):
            return
        ultima = est.regras_enviadas_em
        if ultima and (ag - datetime.fromisoformat(ultima)).total_seconds() < cfg.regras_a_cada_h * 3600:
            return
        # teve pedido depois da ultima vez? (grupo parado nao ganha regra)
        if ultima and not any(p.em > ultima for r in est.rateios_abertos() for p in r.pedidos):
            return
        # abertura chegando: a regra de "N min antes" cuida
        if any(a.status in ("agendada", "contagem") and 0 < (datetime.fromisoformat(a.abre_em) - ag).total_seconds() <= 3600
               for a in est.aberturas):
            return
        with self.arm as e2:
            e2.regras_enviadas_em = ag.isoformat()
            e2.registrar("agenda", "regras do grupo (repetição do dia)")
        await self._mandar(cfg.regras_texto.strip())

    @staticmethod
    def _movimentou(r: Rateio, segundos: int) -> bool:
        """teve abertura, destaque ou pedido nos ultimos N segundos?"""
        ultimo = max(r.destaque_em or "", r.ultimo_movimento_em)
        return (agora() - datetime.fromisoformat(ultimo)).total_seconds() < segundos

    def _post_do_admin_abre(self) -> bool:
        return self.cfg.post_do_admin_abre

    def _eh_admin(self, r: Recebida) -> bool:
        if r.de_mim or (r.autor_fone is not None and r.autor_fone in self.cfg.admins):
            return True
        return bool(self._admins_grupo) and (r.autor in self._admins_grupo or r.autor.split("@")[0] in self._admins_grupo
                                             or (r.autor_fone or "") in self._admins_grupo)

    async def atualizar_admins(self) -> bool:
        if not self.cfg.grupo_jid or not getattr(self.wa, "conectado", False):
            return False
        try:
            self._admins_grupo = await self.wa.admins_do_grupo(self.cfg.grupo_jid)
            log.info("admins do grupo: %d ids", len(self._admins_grupo))
            if hasattr(self.wa, "participantes"):   # pro "@all" notificar todo mundo
                self._todos = await self.wa.participantes(self.cfg.grupo_jid)
                log.info("participantes: %d (%s)", len(self._todos), ", ".join(sorted({j.split("@")[-1] for j in self._todos})))
            return True
        except Exception:  # noqa: BLE001
            log.exception("nao consegui ler os admins do grupo")
            return False

    async def _mandar(self, texto: str, mencoes: list[str] | None = None, grupo_ok: bool = True, foto: str | None = None) -> str | None:
        """Respeita o modo. Devolve o id da mensagem quando foi pro grupo."""
        e = self.arm.estado
        if e.modo == "observando":
            return None  # so observa: nao manda nada pra ninguem
        if e.modo == "ao_vivo" and grupo_ok and self.cfg.grupo_jid:
            if "@all" in texto and not mencoes:
                # "@all" escrito nao notifica ninguem: marca todos os participantes de forma invisivel
                mencoes = list(getattr(self, "_todos", []) or [])
            if foto:
                try:
                    return await self.wa.enviar_imagem(self.cfg.grupo_jid, foto, texto, mencoes or None)
                except Exception:  # noqa: BLE001
                    log.exception("foto nao foi; mando so o texto")
            return await self.wa.enviar_texto(self.cfg.grupo_jid, texto, mencoes or None)
        if e.modo in ("sombra", "ao_vivo") and self.cfg.avisar_admin:
            await self.wa.enviar_texto(self.cfg.avisar_admin + "@s.whatsapp.net", "🕶️ (sombra)\n\n" + texto)
        return None

    async def _avisar_admin(self, texto: str) -> None:
        if self.cfg.avisar_admin and self.arm.estado.modo not in ("desligado", "observando"):
            try:
                await self.wa.enviar_texto(self.cfg.avisar_admin + "@s.whatsapp.net", "🤖 " + texto)
            except Exception:  # noqa: BLE001
                log.exception("falha avisando admin")

    def _mesmo_perfume(self, a: str, b: str) -> bool:
        return mesmo_perfume(a, b)

    # ------------------------------------------------------------ mensagens
    async def receber(self, r: Recebida) -> None:
        e = self.arm.estado
        if not r.eh_grupo or r.chat != self.cfg.grupo_jid or e.modo == "desligado":
            return

        if r.apagou_id:
            with self.arm as est:
                for rat in est.rateios[:10]:   # inclui o que acabou de fechar: apagar um pedido reabre
                    novo = remover_por_msg(rat, r.apagou_id)
                    if novo:
                        self._trocar(est, novo)
                        est.registrar("apagou", f"{r.push_name} apagou o pedido")
                        self._agendar_lista(novo.id)
            return

        if not r.texto:
            return

        # post de decant (admin abre/atualiza; membro colou a lista)
        if parece_post(r.texto):
            await self._tratar_post(r, ler_post(r.texto))
            return

        if r.de_mim or self._eh_admin(r):
            # conversa de admin nao vira pedido, mas se cita um perfume aberto, ele passa a ser o da vez
            abertos = e.rateios_abertos()
            if len(abertos) > 1:
                citados = [x for x in abertos if cita(x, r.texto)]
                alvo = citados[0] if len(citados) == 1 else None
                if alvo:
                    with self.arm as est:
                        a2 = est.rateio(alvo.id)
                        destacar(a2, agora().isoformat())
                        est.registrar("destaque", f"admin falou do {a2.nome}: agora é o da vez")
            return

        it = interpretar(r.texto)
        # dono do APC aumentando: "30 +10ml", "O meu vai ser APC de 35+5=40 ml" -> soma na linha do APC
        if re.search(r"[+=]\s*\d", r.texto):
            cit = rateio_da_mensagem(e.rateios, r.citado_id)
            alvos = [cit] if cit and cit.status == "aberto" else e.rateios_abertos()
            for x in alvos:
                res = ajustar_apc(x, r.autor, r.texto, agora())
                if res is None:
                    continue
                if res.ok:
                    with self.arm as est:
                        self._trocar(est, res.rateio)
                        est.registrar("pedido", f"{r.push_name}: {r.texto!r} → APC agora com {res.rateio.dono_apc.ml} ml no {x.nome}")
                    if self.cfg.reagir_pedido and e.modo == "ao_vivo":
                        try:
                            await self.wa.reagir(r.chat, r.autor, r.msg_id, self.cfg.emoji_reacao or "👍")
                        except Exception:  # noqa: BLE001
                            log.exception("falha reagindo")
                    if res.rateio.status == "fechado":
                        await self.postar_lista(res.rateio.id)
                    else:
                        self._agendar_lista(res.rateio.id)
                elif res.resposta:
                    await self._mandar(f"@{r.autor.split('@')[0]} {res.resposta}", [r.autor])
                return
        if it["tipo"] in ("nada", "lista"):
            return
        if it["tipo"] == "duvida":
            # regra nao teve certeza: a IA tenta; se ela tambem nao souber, vai pro admin
            nomes = [x.nome for x in e.rateios_abertos()]
            via_ia = await self.ia.interpretar(r.texto, r.push_name, nomes) if self.ia.ligada else None
            if via_ia and via_ia["tipo"] != "nada":
                it = via_ia
                with self.arm as est:
                    est.registrar("ia", f"{r.push_name}: {r.texto!r} → {it['tipo']}")
            else:
                with self.arm as est:
                    est.registrar("duvida", f"{r.push_name}: {r.texto!r} ({it['motivo']})")
                    est.para_aprender("duvida", r.texto, autor=r.push_name, autor_id=r.autor, msg_id=r.msg_id, motivo=it["motivo"],
                                      abertos=[x.nome for x in est.rateios_abertos()])
                if not (via_ia and via_ia["tipo"] == "nada"):
                    await self._avisar_admin(f"Não entendi, confere aí:\n{r.push_name}: {r.texto}")
                return

        # fala de OUTRO perfume ("quero o apc do torino" com o Torino fechado): nunca anota no perfume errado
        citado = rateio_da_mensagem(e.rateios, r.citado_id)
        if citado and citado.status == "pausado":
            with self.arm as est:   # pausado no painel: nao anota e nao responde nada no grupo
                est.registrar("ignorado", f"{r.push_name}: {r.texto!r} -> {citado.nome} pausado")
            return
        if citado and citado.status != "aberto" and it["tipo"] in ("pedido", "apc"):
            with self.arm as est:
                est.registrar("recusado", f"{r.push_name}: {r.texto!r} → respondeu o {citado.nome}, que já fechou")
            await self._mandar(f"@{r.autor.split('@')[0]} O {citado.nome} já fechou 🙏", [r.autor])
            return
        citado_ok = citado is not None and citado.status == "aberto"
        # respondeu uma mensagem que nao e de nenhum perfume (ex. a imagem "DISPONIVEIS" com as sobras de outros):
        # so vale se o texto respondido cita um perfume aberto; senao nao anota no perfume da vez
        # (a mensagem respondida fala de sobras/"disponiveis" ou de perfume conhecido fora do ar). Reply numa foto ou numa
        # conversa qualquer ("Clara 3", "5 ml") segue o fluxo normal: perfume em destaque + confirmacao no grupo
        cit_txt = r.citado_texto if r.citado_texto is not None else None
        if (citado is None and r.citado_id and cit_txt is not None and it["tipo"] in ("pedido", "apc")
                and not any(cita(x, cit_txt) for x in e.rateios_abertos())
                and (re.search(r"dispon|sobra|estoque|restante", normalizar(cit_txt))
                     or outro_perfume(cit_txt, e.rateios_abertos(), e.rateios, e.perfumes_vistos) is not None)):
            with self.arm as est:
                est.registrar("outro perfume", f"{r.push_name}: {r.texto!r} (respondeu mensagem que não é de perfume aberto)")
                est.para_aprender("duvida", r.texto, autor=r.push_name, autor_id=r.autor, msg_id=r.msg_id, motivo="respondeu mensagem que não é de perfume aberto",
                                  respondeu=r.citado_texto[:200], abertos=[x.nome for x in est.rateios_abertos()])
            await self._avisar_admin(f"Pedido respondendo outra mensagem, não anotei:\n{r.push_name}: {r.texto}\n(respondeu: {r.citado_texto[:120] or 'foto'})")
            return
        if citado is None and r.citado_id and r.citado_texto is not None:
            # respondeu uma mensagem que nao e de perfume: quem citou o perfume ganha; senao segue como pedido solto
            # respondeu uma mensagem que cita UM perfume aberto (repost, conversa sobre ele): liga a mensagem a esse perfume
            alvo = [x for x in e.rateios_abertos() if cita(x, r.citado_texto)]
            if len(alvo) == 1:
                with self.arm as est:
                    est.rateio(alvo[0].id).lista_msg_ids.append(r.citado_id)
                citado, citado_ok = alvo[0], True
        if not citado_ok:
            outro = outro_perfume(r.texto, e.rateios_abertos(), e.rateios, e.perfumes_vistos)
            if outro is not None:
                with self.arm as est:
                    est.registrar("outro perfume", f"{r.push_name}: {r.texto!r} (não é de nenhum perfume aberto)")
                if isinstance(outro, Rateio) and outro.status != "pausado" and it["tipo"] in ("pedido", "apc"):
                    await self._mandar(f"@{r.autor.split('@')[0]} O {outro.nome} já fechou 🙏", [r.autor])
                elif outro is True and it["tipo"] in ("pedido", "apc", "alterar"):
                    with self.arm as est:
                        est.para_aprender("duvida", r.texto, autor=r.push_name, autor_id=r.autor, msg_id=r.msg_id, motivo="cita perfume que não está aberto",
                                          abertos=[x.nome for x in est.rateios_abertos()])
                    await self._avisar_admin(f"Pedido de um perfume que não está aberto:\n{r.push_name}: {r.texto}")
                return

        autor = Autor(id=r.autor, msg_id=r.msg_id, push_name=r.push_name)
        resultados = []
        chutes: list[Resultado] = []   # pedidos sem reply e sem nome com mais de um perfume aberto: confirma no grupo
        with self.arm as est:
            abertos = est.rateios_abertos()
            for parte, dica in self._partes(it, abertos):
                rat = escolher_rateio(abertos, citado_id=r.citado_id, dica=dica)
                if rat is None and parte["tipo"] in ("alterar", "cancelar"):
                    # "altera pra 10ml" / "desisto": vale no perfume onde a pessoa tem pedido (o mais recente)
                    meus = [(max(p.em for p in x.pedidos if p.autor_id == r.autor), x) for x in abertos if any(p.autor_id == r.autor for p in x.pedidos)]
                    # pedido em mais de um perfume: vale o que esta em destaque (ex. logo depois do "So 4 ml do X")
                    foco = em_foco(abertos)
                    rat = foco if foco in [x for _, x in meus] else (max(meus, key=lambda t: t[0])[1] if meus else None)
                    if rat is None and parte["tipo"] == "cancelar":
                        est.registrar("recusado", f"{r.push_name}: {r.texto!r} → não tem pedido pra cancelar")
                        continue
                if rat is None:
                    if not abertos:
                        return
                    # quase ninguem responde o post: o pedido solto e do perfume em destaque (como o admin faz)
                    if self.cfg.sem_reply == "recente":
                        if parte["tipo"] == "apc":
                            # "apc" solto: o da vez entre os que ainda tem APC livre
                            com_apc = [x for x in abertos if x.apc_ml and not x.dono_apc and x.disponivel >= x.apc_ml]
                            if not com_apc and any(x.dono_apc and x.dono_apc.autor_id == r.autor for x in abertos):
                                # quem ja tem o APC falando dele de novo ("o meu vai ser APC 35+5"): nao responde no grupo, admin ajusta
                                est.registrar("duvida", f"{r.push_name}: {r.texto!r} (já tem o APC; ajuste no painel se for o caso)")
                                est.para_aprender("duvida", r.texto, autor=r.push_name, autor_id=r.autor, msg_id=r.msg_id, motivo="já é dono do APC",
                                                  abertos=[x.nome for x in abertos])
                                asyncio.create_task(self._avisar_admin(f"{r.push_name} já tem o APC e escreveu:\n{r.texto}\n(se mudou a quantidade, ajuste no ✎ do painel)"))
                                continue
                            if not com_apc:
                                est.registrar("recusado", f"{r.push_name}: {r.texto!r} → nenhum APC disponível")
                                resultados.append(Resultado(rateio=abertos[0], ok=False, resposta="Nenhum APC disponível agora 🙏"))
                                continue
                            rat = em_foco(com_apc)
                            possiveis = com_apc
                        else:
                            rat = em_foco(abertos)
                            possiveis = abertos
                        est.registrar("assumido", f"{r.push_name}: {r.texto!r} → {rat.nome} (em destaque, sem reply)")
                        # so e duvida de verdade se outro perfume que PODERIA receber o pedido teve movimento na ultima hora
                        # (ex. "Apc" logo apos abrir o Damask, com o Bal parado e sem APC livre: nao confirma)
                        chutou = (bool(r.citado_id) and not citado_ok) or any(x is not rat and self._movimentou(x, 3600) for x in possiveis)
                    else:
                        est.registrar("ambiguo", f"{r.push_name}: {r.texto!r} (vários rateios abertos, sem reply)")
                        asyncio.create_task(self._avisar_admin(f"Pedido sem reply com {len(abertos)} rateios abertos:\n{r.push_name}: {r.texto}"))
                        return
                else:
                    chutou = False
                atual = est.rateio(rat.id)
                if parte.get("nome"):
                    chaves = {p for x in est.rateios for p in re.findall(r"[a-z]{3,}", normalizar(x.nome))}   # "bal", "ani"
                    sobra = [w for w in parte["nome"].split() if w.lower() not in chaves]
                    parte = {**parte, "nome": " ".join(sobra) or None}
                res = aplicar(atual, parte, autor, agora())
                if res.ok:
                    if r.citado_id or (dica and dica.strip() and len(abertos) > 1 and escolher_rateio(abertos, dica=dica) is rat):
                        destacar(res.rateio, agora().isoformat())
                    self._trocar(est, res.rateio)
                    est.registrar("pedido", f"{r.push_name}: {r.texto!r} → {rat.nome}")
                    if chutou:
                        chutes.append(res)
                else:
                    est.registrar("recusado", f"{r.push_name}: {r.texto!r} → {res.resposta or 'ignorado'}")
                resultados.append(res)

        if any(x.ok for x in resultados) and self.cfg.reagir_pedido and self.arm.estado.modo == "ao_vivo":
            try:
                await self.wa.reagir(r.chat, r.autor, r.msg_id, self.cfg.emoji_reacao or "👍")
            except Exception:  # noqa: BLE001
                log.exception("falha reagindo")
        if chutes and self.cfg.confirmar_sem_reply:
            # o robo escolheu o perfume sozinho: avisa na hora, pra pessoa corrigir antes da lista final
            nomes = " e ".join(dict.fromkeys(x.rateio.nome for x in chutes))
            await self._mandar(f"✅ @{r.autor.split('@')[0]} anotado no {nomes}. Se era de outro perfume, chame um admin 🙏", [r.autor])
        for res in resultados:
            if res.ok:
                if res.rateio.status == "fechado":
                    await self.postar_lista(res.rateio.id)   # bateu o frasco: FRASCO FECHADO na hora
                else:
                    self._agendar_lista(res.rateio.id)
            elif res.resposta:
                if self.cfg.responder_erro_no_grupo:
                    await self._mandar(f"@{r.autor.split('@')[0]} {res.resposta}", [r.autor])
                else:
                    await self._avisar_admin(f"{r.push_name}: {r.texto!r} → {res.resposta}")

    @staticmethod
    def _partes(it: dict, abertos: list) -> list[tuple[dict, str]]:
        """Separa "5ml do torino e 3ml do kirke" em um pedido por perfume. Devolve [(intencao, dica)]."""
        if it["tipo"] != "pedido":
            return [(it, it.get("dica") or "")]
        dica_geral = " ".join(i["dica"] for i in it["itens"]) + " " + it.get("resto", "")
        if len(it["itens"]) > 1 and len(abertos) > 1:
            alvos = [escolher_rateio(abertos, dica=i["dica"]) if i["dica"] else None for i in it["itens"]]
            if all(alvos) and len({a.id for a in alvos}) > 1:
                return [({**it, "itens": [i], "nome": None}, i["dica"]) for i in it["itens"]]
        return [(it, dica_geral)]

    async def _tratar_post(self, r: Recebida, post: Post) -> None:
        with self.arm as est:
            rat = next((x for x in est.rateios if x.status in ("aberto", "pausado") and self._mesmo_perfume(x.nome, post.nome)), None)
            if self._eh_admin(r) and not self._post_do_admin_abre():
                # lista/post que admin manda pelo celular NAO entra no sistema: o sistema so conta pedido de gente.
                # Perfume do sistema: guarda a mensagem (reply nela vale pro perfume) e, se a lista do admin
                # estiver diferente, so avisa no Aprender, sem mexer nos pedidos.
                if rat is None or rat.status != "aberto":
                    est.registrar("ignorado", f"post/lista do admin fora do sistema: {post.nome}")
                    return
                robo = sorted(("APC" if p.apc else str(p.ml)) + " " + p.nome for p in rat.pedidos)
                admin = sorted(("APC" if l.apc else str(l.ml)) + " " + l.nome for l in post.linhas_lista)
                if post.linhas_lista and sorted(x.split(" ")[0] for x in robo) != sorted(x.split(" ")[0] for x in admin):
                    if not any(a["tipo"] == "divergencia" and a["status"] == "pendente" and a.get("perfume") == rat.nome for a in est.aprender):
                        est.para_aprender("divergencia", f"Lista do {rat.nome}", perfume=rat.nome, robo=robo, admin=admin)
                    else:   # ja tem uma pendente: so atualiza a lista do admin nela
                        for a in est.aprender:
                            if a["tipo"] == "divergencia" and a["status"] == "pendente" and a.get("perfume") == rat.nome:
                                a["admin"], a["robo"] = admin, robo
                else:
                    est.resolver_divergencias(rat)
                rat.lista_msg_ids.append(r.msg_id)
                destacar(rat, agora().isoformat())
                return
            if self._eh_admin(r):
                if rat is None:
                    # perfume que nao foi aberto pelo sistema (admin postou no celular: sobra, repost de outro dia):
                    # entra PAUSADO — aparece no painel, mas o robo so anota depois que alguem clicar em Retomar
                    rat = adotar_lista_do_admin(novo_rateio(post, r.msg_id, agora()), post.linhas_lista)
                    rat.origem = "admin"
                    if not self._post_do_admin_abre():
                        rat.status = "pausado"
                    est.rateios.insert(0, rat)
                    if rat.nome not in est.perfumes_vistos:
                        est.perfumes_vistos.append(rat.nome)
                    est.registrar("rateio", f"postado pelo admin ({'aberto' if rat.status == 'aberto' else 'fora do sistema, pausado'}): {rat.nome} ({rat.reservado}/{rat.total_ml} ml)")
                else:
                    robo = sorted(("APC" if p.apc else str(p.ml)) + " " + p.nome for p in rat.pedidos)
                    admin = sorted(("APC" if l.apc else str(l.ml)) + " " + l.nome for l in post.linhas_lista)
                    sig = lambda xs: sorted(x.split(" ")[0] for x in xs)  # noqa: E731
                    if sig(robo) != sig(admin):
                        est.para_aprender("divergencia", f"Lista do {rat.nome}", perfume=rat.nome,
                                          robo=robo, admin=admin)
                    novo = adotar_lista_do_admin(rat, post.linhas_lista)
                    novo.lista_msg_ids.append(r.msg_id)
                    if rat.status == "pausado":
                        novo.status = "pausado"   # lista nova do admin nao reativa: so o Retomar do painel
                    else:
                        destacar(novo, agora().isoformat())
                    self._trocar(est, novo)
                    est.registrar("rateio", f"lista do admin adotada: {novo.nome}")
                return
            if rat is None or rat.status != "aberto":
                return
            # repost do post por qualquer pessoa: quem responder essa mensagem pede desse perfume
            rat.lista_msg_ids.append(r.msg_id)
            res = incorporar_lista_colada(rat, post.linhas_lista, Autor(id=r.autor, msg_id=r.msg_id, push_name=r.push_name), agora())
            if res.ok:
                self._trocar(est, res.rateio)
                est.registrar("pedido", f"{r.push_name} colou a lista com {len(res.novas)} linha(s) nova(s)")
                rid = res.rateio.id
            else:
                return
        self._agendar_lista(rid)

    def _trocar(self, est, novo: Rateio) -> None:
        est.rateios = [novo if x.id == novo.id else x for x in est.rateios]

    # ------------------------------------------------------------ lista
    def _agendar_lista(self, rid: str) -> None:
        with self.arm as est:
            r = est.rateio(rid)
            if r:
                r.lista_pendente = True
        loop = asyncio.get_event_loop()
        if t := self._timers.pop(rid, None):
            t.cancel()
        self._timers[rid] = loop.call_later(self.cfg.segundos_ate_postar_lista, lambda: asyncio.create_task(self.postar_lista(rid)))

    async def postar_lista(self, rid: str) -> None:
        if t := self._timers.pop(rid, None):
            t.cancel()   # lista saindo agora: o temporizador pendente nao pode postar de novo
        est = self.arm.estado
        rat = est.rateio(rid)
        if not rat:
            return
        texto, mencoes = renderizar(rat, agora())
        # a lista sai com a foto do perfume (a mesma do agendamento), quando tem
        foto = next((a.foto for a in est.aberturas if a.rateio_id == rid and a.foto), None)
        mid = await self._mandar(texto, mencoes, foto=foto)
        with self.arm as est2:
            r2 = est2.rateio(rid)
            if r2:
                r2.lista_pendente = False
            if r2 and mid:
                r2.lista_msg_ids.append(mid)
            # a lista do robo NAO muda o perfume da vez: ela sai por tempo, nao porque o grupo esta falando dele
            est2.registrar("lista", f"{rat.nome}: {rat.reservado}/{rat.total_ml} ml")

        if rat.status == "fechado":
            with self.arm as est3:
                for a in est3.aberturas:
                    if a.rateio_id == rid and a.status == "aberta":
                        a.status = "encerrada"
                        a.encerrou_em = rat.fechado_em or agora().isoformat()
        elif 0 < rat.disponivel < rat.minimo:
            # sobra que ninguem consegue pedir: nao faz sentido "quem arremata"; o admin decide
            if rat.urgencias == 0:
                with self.arm as est3:
                    est3.rateio(rid).urgencias = self.cfg.urgencia_max  # trava as urgencias
                    est3.registrar("sobra", f"{rat.nome}: sobraram {rat.disponivel} ml, abaixo do mínimo de {rat.minimo}")
                await self._avisar_admin(f"Sobraram {rat.disponivel} ml do {rat.nome}, abaixo do mínimo ({rat.minimo} ml). Fecha o frasco ou ajusta um pedido pelo painel.")
        elif 0 < rat.disponivel <= self.cfg.aviso_ultimos_ml and rat.urgencias == 0:
            ag = agora()
            outra_abrindo = any(a.rateio_id != rid and a.status in ("agendada", "contagem", "aberta")
                                and abs((datetime.fromisoformat(a.abre_em) - ag).total_seconds()) <= self.cfg.folga_abertura_min * 60
                                for a in self.arm.estado.aberturas)
            if not outra_abrindo:
                await self._urgencia(rid)

    async def _chamada(self, rid: str) -> None:
        """Ninguem interagiu faz tempo: '@all O X esta aberto, ainda temos N ml'. Alterna 3 textos."""
        rat = self.arm.estado.rateio(rid)
        if not rat or rat.status != "aberto":
            return
        chaves = ["chamada", "chamada_2", "chamada_3"]
        texto = self.cfg.textos.get(chaves[rat.chamadas % len(chaves)]) or self.cfg.textos.get("chamada", "")
        with self.arm as est:
            r2 = est.rateio(rid)
            r2.chamadas += 1   # mensagem do robo nao muda o perfume em destaque
            r2.ultima_chamada_em = agora().isoformat()
            est.registrar("chamada", f"{rat.nome}: nenhuma interação, {rat.disponivel} ml (chamada {r2.chamadas})")
        mid = await self._mandar(texto.format(ml=rat.disponivel, nome=rat.nome))
        if mid:
            with self.arm as est:
                r3 = est.rateio(rid)
                if r3:
                    r3.lista_msg_ids.append(mid)

    async def _urgencia(self, rid: str) -> None:
        """'So X ml, quem arremata?' Alterna os textos como o admin faz; repete a cada N min (relogio)."""
        rat = self.arm.estado.rateio(rid)
        if not rat or rat.status != "aberto" or rat.urgencias >= self.cfg.urgencia_max or rat.disponivel < rat.minimo:
            return
        chaves = ["ultimos", "ultimos_2", "ultimos_3"]
        texto = self.cfg.textos.get(chaves[rat.urgencias % len(chaves)], self.cfg.textos["ultimos"])
        mid = await self._mandar(texto.format(ml=rat.disponivel, nome=rat.nome))
        if mid:
            with self.arm as est:
                r3 = est.rateio(rid)
                if r3:
                    r3.lista_msg_ids.append(mid)
        with self.arm as est:
            r2 = est.rateio(rid)
            r2.urgencias += 1   # mensagem do robo nao muda o perfume em destaque
            r2.ultima_urgencia_em = agora().isoformat()
            est.registrar("urgencia", f"{rat.nome}: {rat.disponivel} ml (aviso {r2.urgencias})")

    # ------------------------------------------------------------ agenda
    async def relogio(self) -> None:
        # listas que ficaram na espera quando o robo caiu/reiniciou saem agora
        for r in self.arm.estado.rateios:
            if r.lista_pendente:
                log.info("lista pendente de antes do reinicio: %s", r.nome)
                self._agendar_lista(r.id)
        while True:
            try:
                await self._tique()
            except Exception:  # noqa: BLE001
                log.exception("erro no relogio")
            await asyncio.sleep(15)

    async def _tique(self) -> None:
        est = self.arm.estado
        agora_s = agora().timestamp()
        if agora_s - getattr(self, "_admins_lidos_em", 0) > 600:   # admins do grupo a cada 10 min
            if await self.atualizar_admins():                        # so marca quando conseguiu (tenta de novo no proximo tique)
                self._admins_lidos_em = agora_s
            # admin abre/fecha o grupo pelo celular: confere o estado real (senao o "fechar 1h antes" nao dispara)
            if self.cfg.grupo_jid:
                try:
                    aberto = await self.wa.grupo_esta_aberto(self.cfg.grupo_jid)
                    if aberto != est.grupo_aberto:
                        with self.arm as e2:
                            e2.grupo_aberto = aberto
                            e2.registrar("grupo", f"grupo {'aberto' if aberto else 'fechado'} (visto no WhatsApp)")
                except Exception:  # noqa: BLE001
                    log.warning("nao consegui ler se o grupo esta aberto")
        if est.modo in ("desligado", "observando") or not self.cfg.grupo_jid:
            return
        ag = agora()
        # abertura em andamento (30 min antes ate 30 min depois do horario): so o perfume que esta abrindo fala.
        # 30/09 11:00: "somente 7 ml do Bal" saiu junto com o GRUPO ABERTO e os pedidos do perfume novo foram pro Bal
        em_abertura = {a.rateio_id for a in est.aberturas if a.status in ("agendada", "contagem", "aberta")
                       and abs((datetime.fromisoformat(a.abre_em) - ag).total_seconds()) <= self.cfg.folga_abertura_min * 60}
        # urgencia repetida: rateio aberto com pouco ml e grupo aberto, a cada N min
        if self.cfg.urgencia_a_cada_min > 0 and est.grupo_aberto:
            for rat in est.rateios_abertos():
                if em_abertura and rat.id not in em_abertura:
                    continue
                if 0 < rat.disponivel < rat.minimo:
                    continue  # sobra que ninguem pode pedir: nunca pede arremate
                if 0 < rat.disponivel <= self.cfg.aviso_ultimos_ml and 0 < rat.urgencias < self.cfg.urgencia_max and rat.ultima_urgencia_em:
                    if (ag - datetime.fromisoformat(rat.ultima_urgencia_em)).total_seconds() >= self.cfg.urgencia_a_cada_min * 60:
                        await self._urgencia(rat.id)
        # chamada: perfume aberto, grupo aberto, nenhuma interacao ha N min
        # so o perfume da vez recebe chamada (varios abertos ao mesmo tempo nao viram varias chamadas)
        foco = em_foco(est.rateios_abertos())
        if self.cfg.chamada_silencio_min > 0 and est.grupo_aberto and foco and not (em_abertura and foco.id not in em_abertura):
            rat = foco
            if rat.disponivel > self.cfg.aviso_ultimos_ml and rat.chamadas < self.cfg.chamada_max:
                # silencio conta pro GRUPO todo: qualquer pedido em qualquer perfume zera o relogio
                ultimo = max([rat.ultima_chamada_em or ""] + [x.ultimo_movimento_em for x in est.rateios_abertos()])
                if (ag - datetime.fromisoformat(ultimo)).total_seconds() >= self.cfg.chamada_silencio_min * 60:
                    await self._chamada(rat.id)
        await self._regras_do_dia(est, ag)
        for ab in list(est.aberturas):
            abre = datetime.fromisoformat(ab.abre_em)
            # abertura que ja passou do horario de fechar (robo estava desligado): nunca abre/posta atrasada
            if ab.status in ("agendada", "contagem") and ag >= datetime.fromisoformat(ab.fecha_em):
                with self.arm as e2:
                    e2.abertura(ab.id).status = "cancelada"
                    e2.registrar("agenda", f"abertura vencida, nao abri: {ab.nome}")
                continue
            # fecha o grupo N min antes da abertura (o admin faz isso pra criar expectativa)
            janela = self.cfg.fechar_antes_min * 60
            # outra abertura do sistema abre (ou abriu) dentro da janela de fechar desta: nao fecha o grupo em cima dela.
            # ex. Orience 17h e Argentina 18h: o Argentina nao fecha o grupo as 17h; posta os valores so as 18h
            colada = any(o.id != ab.id and o.status in ("agendada", "contagem", "aberta")
                         and 0 < (abre - datetime.fromisoformat(o.abre_em)).total_seconds() <= janela
                         for o in est.aberturas)
            if (ab.status == "agendada" and self.cfg.fechar_antes_min > 0 and not ab.fechou_antes and not colada
                    and est.grupo_aberto is not False and 0 < (abre - ag).total_seconds() <= janela):
                with self.arm as e2:
                    e2.abertura(ab.id).fechou_antes = True
                    e2.grupo_aberto = False
                    e2.registrar("agenda", f"grupo fechado {self.cfg.fechar_antes_min} min antes: {ab.nome}")
                await self._mandar(self.cfg.textos["fechar_antes"].format(nome=ab.nome, hora=ab.hora_curta))
                if est.modo == "ao_vivo":
                    await self.wa.fechar_grupo(self.cfg.grupo_jid)
            # aviso "abertura de hoje", horas antes
            if ab.status == "agendada" and ab.aviso_em and not ab.aviso_feito and ab.aviso_texto.strip():
                if datetime.fromisoformat(ab.aviso_em) <= ag < abre:
                    with self.arm as e2:
                        e2.abertura(ab.id).aviso_feito = True
                        e2.registrar("agenda", f"aviso de abertura: {ab.nome}")
                    await self._mandar(ab.aviso_texto)   # so texto: a foto ja vai no post e nas listas
            # post com os valores sai depois do fechamento e do aviso; na abertura so abre
            if ab.status in ("agendada", "contagem") and ab.fechou_antes and not ab.rateio_id and ag < abre:
                await self._postar(ab, "junto com o fechamento")
            # "como pedir": N min antes da abertura (o grupo esta fechado, so o robo fala: o pessoal le)
            if (ab.status in ("agendada", "contagem") and not ab.regras_feito and self.cfg.regras_texto.strip()
                    and self.cfg.regras_antes_min > 0 and 0 < (abre - ag).total_seconds() <= self.cfg.regras_antes_min * 60):
                with self.arm as e2:
                    e2.abertura(ab.id).regras_feito = True
                    e2.regras_enviadas_em = ag.isoformat()
                    e2.registrar("agenda", f"regras do grupo ({self.cfg.regras_antes_min} min antes): {ab.nome}")
                await self._mandar(self.cfg.regras_texto.strip())
            if ab.status in ("agendada", "contagem") and ag < abre:
                faltam = (abre - ag).total_seconds() / 60
                for mins in sorted(self.cfg.contagem_min, reverse=True):
                    if mins not in ab.avisos_feitos and faltam <= mins:
                        # abertura agendada em cima da hora: contagem que ja passou de longe nao e enviada
                        atrasada = faltam < mins - 2
                        with self.arm as e2:
                            a2 = e2.abertura(ab.id)
                            a2.avisos_feitos.append(mins)
                            a2.status = "contagem"
                            if not atrasada:
                                e2.registrar("agenda", f"contagem {mins} min: {ab.nome}")
                        if not atrasada:
                            await self._mandar(self.cfg.textos["contagem"].format(min=mins, nome=ab.nome, hora=ab.hora_curta))
            elif ab.status in ("agendada", "contagem") and ag >= abre:
                await self._abrir(ab)

    async def _abrir(self, ab: Abertura, origem: str = "relógio") -> None:
        mid_aberto = None
        if self.arm.estado.modo == "ao_vivo":
            # grupo ja aberto (outra abertura rolando, ou admin abriu no celular): so posta o perfume
            try:
                ja_aberto = await self.wa.grupo_esta_aberto(self.cfg.grupo_jid)
            except Exception:  # noqa: BLE001
                ja_aberto = self.arm.estado.grupo_aberto is True
            if not ja_aberto:
                await self.wa.abrir_grupo(self.cfg.grupo_jid)
                mid_aberto = await self._mandar(self.cfg.textos["aberto"])
        elif not ab.rateio_id:
            await self._mandar("(abriria o grupo agora)")
        await self._postar(ab, origem, agora())   # nao repete se o post ja saiu junto com o fechamento
        with self.arm as est:
            a2 = est.abertura(ab.id)
            a2.status = "aberta"
            a2.abriu_em = agora().isoformat()
            rat = est.rateio(a2.rateio_id) if a2.rateio_id else None
            if rat:
                rat.aberto_em = agora().isoformat()
                destacar(rat, agora().isoformat())   # abriu agora: "5ml" solto e desse perfume (caso Cedar 29/09 14:00)
                if mid_aberto:   # "5ml" respondendo o "GRUPO ABERTO" e desse perfume
                    rat.lista_msg_ids.append(mid_aberto)
            est.grupo_aberto = True
            est.registrar("agenda", f"grupo aberto ({origem}): {ab.nome}")

    async def _postar(self, ab: Abertura, origem: str, quando: datetime | None = None) -> None:
        """Posta a foto com os valores e cria o rateio. Sai junto com o fechamento, antes da abertura."""
        texto = ab.post_texto(quando or datetime.fromisoformat(ab.abre_em))
        with self.arm as est:
            a2 = est.abertura(ab.id)
            if a2.rateio_id:
                return
            rat = novo_rateio(ler_post(texto), None, agora())
            est.rateios.insert(0, rat)
            if rat.nome not in est.perfumes_vistos:
                est.perfumes_vistos.append(rat.nome)
            a2.rateio_id = rat.id
            est.registrar("agenda", f"post ({origem}): {ab.nome}")
        try:
            if self.arm.estado.modo == "ao_vivo":
                mid = await (self.wa.enviar_imagem(self.cfg.grupo_jid, ab.foto, texto) if ab.foto else self.wa.enviar_texto(self.cfg.grupo_jid, texto))
            else:
                mid = await self._mandar("(postaria agora)\n\n" + texto)
        except Exception:
            # WhatsApp ainda reconectando: desfaz e o proximo tique tenta de novo
            with self.arm as est:
                est.rateios = [r for r in est.rateios if r.id != rat.id]
                est.abertura(ab.id).rateio_id = None
                est.registrar("erro", f"post nao saiu, tentando de novo: {ab.nome}")
            raise
        if mid:
            with self.arm as est:
                r = est.rateio(rat.id)
                if r:
                    r.post_msg_id = mid

    # ------------------------------------------------------------ comandos do painel
    async def forcar_lista(self, rid: str) -> None:
        await self.postar_lista(rid)

    async def fechar_rateio(self, rid: str) -> None:
        with self.arm as est:
            r = est.rateio(rid)
            if r:
                r.status, r.fechado_em = "fechado", agora().isoformat()
                est.registrar("painel", f"rateio fechado à mão: {r.nome}")
        await self.postar_lista(rid)

    async def abrir_agora(self, aid: str) -> None:
        ab = self.arm.estado.abertura(aid)
        if ab and ab.status in ("agendada", "contagem"):
            await self._abrir(ab, origem="botão Abrir agora")

    async def fechar_grupo_agora(self) -> None:
        if self.arm.estado.modo == "ao_vivo":
            await self.wa.fechar_grupo(self.cfg.grupo_jid)
        with self.arm as est:
            est.grupo_aberto = False
            for a in est.aberturas:
                if a.status == "aberta":
                    a.status = "encerrada"
            est.registrar("painel", "grupo fechado pelo painel")

    async def abrir_grupo_agora(self) -> None:
        if self.arm.estado.modo == "ao_vivo":
            await self.wa.abrir_grupo(self.cfg.grupo_jid)
        with self.arm as est:
            est.grupo_aberto = True
            est.registrar("painel", "grupo aberto pelo painel")

    async def descobrir_grupo(self) -> str | None:
        jid = await self.wa.grupo_por_nome(self.cfg.grupo_nome)
        self._admins_lidos_em = 0   # relê os admins no proximo tique
        if jid:
            with self.arm as est:
                est.config.grupo_jid = jid
                est.registrar("conexao", f"grupo encontrado: {jid}")
        return jid
