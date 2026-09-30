"""Painel web (FastAPI). Telas: Ao vivo, Agenda, Nova abertura, Conexao, Ajustes. Senha unica no .env.
O visual mora em ui.py; aqui ficam as rotas e o HTML de cada tela."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .estado import MODOS, Abertura, Armazem, novo_id
from .motor import Motor
from .rateio import Pedido, renderizar
from .texto import SP, agora
from .ui import botao, card, e, pagina

seguranca = HTTPBasic()
FOTOS = Path("data/fotos")
def fone(txt: str) -> str:
    """'(11) 91234-5678', '5511 912345678' -> '5511912345678' (so digitos, com 55)"""
    d = "".join(ch for ch in txt if ch.isdigit())
    return "55" + d if len(d) in (10, 11) else d


def fone_bonito(autor_id: str | None) -> str | None:
    """'5511912345678@s.whatsapp.net' -> '+55 11 91234-5678' (lid e pedido do painel nao tem numero)"""
    if not autor_id or not autor_id.endswith("@s.whatsapp.net"):
        return None
    d = autor_id.split("@")[0]
    if d.startswith("55") and len(d) in (12, 13):
        return f"+55 {d[2:4]} {d[4:-4]}-{d[-4:]}"
    return "+" + d


def numero_conhecido(est, nome: str) -> str | None:
    """pedido adicionado a mao: se so UMA pessoa com esse nome ja pediu pelo grupo, usa o numero dela (pra lista marcar)"""
    from .texto import normalizar
    alvo = normalizar(nome.strip())
    ids = {p.autor_id for r in est.rateios for p in r.pedidos if p.autor_id and normalizar(p.nome) == alvo}
    return ids.pop() if len(ids) == 1 else None


def fone_link(autor_id: str | None) -> str:
    f = fone_bonito(autor_id)
    if not f:
        return ""
    return f' <a class="fone" href="https://wa.me/{autor_id.split("@")[0]}" target="_blank" rel="noopener">{f}</a>'


ROTULO_STATUS = {"agendada": "agendada", "contagem": "em contagem", "aberta": "aberta", "encerrada": "encerrada", "cancelada": "cancelada", "aberto": "aberto", "fechado": "fechado", "pausado": "pausado"}


DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def data_longa(iso: str | None) -> str:
    if not iso:
        return ""
    d = datetime.fromisoformat(iso)
    return f"{DIAS[d.weekday()]}, {d:%d/%m/%Y}"


def hora(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M") if iso else "—"


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def criar_app(arm: Armazem, motor: Motor, sem_senha: bool = False) -> FastAPI:
    """sem_senha=True so no demo.py (roda em 127.0.0.1, com dados ficticios)"""
    app = FastAPI(title="Robô do Grupo")
    senha = os.environ.get("PAINEL_SENHA", "")

    def auth(cred: HTTPBasicCredentials = Depends(seguranca)):
        if not senha or not secrets.compare_digest(cred.password, senha):
            raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})

    dep = [] if sem_senha else [Depends(auth)]

    def tela(titulo: str, subtitulo: str, corpo: str, ativo: str) -> HTMLResponse:
        est = arm.estado
        return HTMLResponse(pagina(titulo, subtitulo, corpo, ativo=ativo, modo=est.modo, conectado=motor.wa.conectado,
                                   grupo_aberto=est.grupo_aberto, grupo_nome=est.config.grupo_nome))

    def foto_url(caminho: str | None) -> str | None:
        return f"/fotos/{e(Path(caminho).name)}" if caminho else None

    def abriu_de(r) -> str | None:
        """hora REAL em que o grupo abriu pra esse perfume (o post sai 1h antes, com o grupo fechado)"""
        ab = next((a for a in arm.estado.aberturas if a.rateio_id == r.id), None)
        return ab.abriu_em if ab else r.aberto_em

    # ------------------------------------------------------------ ao vivo
    @app.get("/", response_class=HTMLResponse, dependencies=dep)
    def ao_vivo(aviso: str = ""):
        est = arm.estado
        blocos = [card(f'<p style="margin:0;color:var(--vinho);font-weight:600">⚠️ {e(aviso)}</p>', tight=True)] if aviso else []
        # o mais recente sempre no topo
        # so o que foi cadastrado no sistema (post que admin manda pelo celular nao aparece aqui)
        for r in sorted((x for x in est.rateios if x.origem != "admin"), key=lambda x: x.aberto_em, reverse=True)[:8]:
            pct = int(100 * r.reservado / r.total_ml) if r.total_ml else 0
            linhas = "".join(
                f'<div class="row"><span class="gem">{"👑" if p.apc else "💎"}</span><span class="grow"><b>{p.ml} ml</b> · {e(p.nome)}{" · APC" if p.apc else ""}{fone_link(p.autor_id)}'
                f'<details class="renomear"><summary title="corrigir nome ou quantidade (mantém o número da pessoa)">✎</summary>'
                f'<form method="post" action="/rateio/{r.id}/editar" class="add"><input type="hidden" name="i" value="{i}">'
                f'<input class="ml" name="ml" value="{p.ml}" inputmode="numeric" title="ml">'
                f'<input class="nome" name="nome" value="{e(p.nome)}">'
                f'<input class="ml" style="flex:1" name="fone" placeholder="número (opcional)" inputmode="tel"><button class="btn sm">Salvar</button></form></details></span>'
                + (f'<form class="inline" method="post" action="/rateio/{r.id}/remover" onsubmit="return confirm(this.dataset.msg)" '
                   f'data-msg="Tirar {p.ml} ml de {e(p.nome)}{" (APC)" if p.apc else ""} da lista?">'
                   f'<input type="hidden" name="i" value="{i}"><button class="btn x sm" title="tirar da lista">✕</button></form>')
                + "</div>"
                for i, p in enumerate(r.pedidos))
            if r.status == "aberto":
                botoes_status = (botao("Pausar", f"/rateio/{r.id}/pausar", icone="Ⅱ")
                                 + botao("Fechar frasco", f"/rateio/{r.id}/fechar", estilo="vinho", icone="✕"))
            elif r.status == "pausado":
                botoes_status = botao("Retomar", f"/rateio/{r.id}/retomar", icone="▶")
            else:
                botoes_status = botao("Reabrir frasco", f"/rateio/{r.id}/reabrir", icone="↺")
            botoes_status += (f'<form class="inline" method="post" action="/rateio/{r.id}/excluir" '
                              'onsubmit="return confirm(this.dataset.msg)" '
                              f'data-msg="Excluir o {e(r.nome)} do painel? O robô para de anotar pedidos dele. Não apaga nada no WhatsApp.">'
                              '<button class="btn ghost sm">Excluir <span class="ic">🗑</span></button></form>')
            pausado = ('<p class="hint" style="color:var(--vinho);font-weight:600">⏸ Pausado: o robô não anota pedidos, não manda lista nem chamada deste perfume.</p>'
                       if r.status == "pausado" else "")
            acoes = f"""<form method="post" action="/rateio/{r.id}/add" class="add">
  <input class="ml" name="ml" placeholder="ml" inputmode="numeric"><input class="nome" name="nome" placeholder="Nome"><input class="fone-in" name="fone" placeholder="WhatsApp (pra marcar)" inputmode="tel">
  <label class="check" style="margin:0"><input type="checkbox" name="apc"> APC</label><button class="btn sm">Adicionar <span class="ic">+</span></button></form>
<div class="actions">{botao("Postar lista agora", f"/rateio/{r.id}/postar", icone="↗")}{botoes_status}</div>"""
            texto, _ = renderizar(r)
            blocos.append(card(f"""<div class="card-title"><h2>{e(r.nome)}</h2><small>{ROTULO_STATUS.get(r.status, r.status)} · {brl(r.valor_ml)}/ml{" · APC " + str(r.apc_ml) + " ml" if r.apc_ml else ""}</small></div>
<div class="datas"><span><small>data</small>{data_longa(r.aberto_em)}</span><span><small>abriu</small>{hora(abriu_de(r))}</span><span><small>frasco fechou</small>{hora(r.fechado_em)}</span></div>
<div class="bar"><i style="width:{pct}%"></i></div><div class="bar-legend"><span>{r.reservado} de {r.total_ml} ml reservados</span><span>{r.disponivel} ml livres</span></div>
<div style="margin-top:8px">{linhas or '<p class="hint">Nenhum pedido ainda.</p>'}</div>{acoes}{pausado}
<details><summary>ver como fica no WhatsApp</summary><pre>{e(texto)}</pre></details>"""))
        logs = "".join(f'<div class="row"><span class="t">{l["em"][11:16]}</span><span class="grow"><span class="tag {e(l["tipo"])}">{e(l["tipo"])}</span>{e(l["texto"])}</span></div>' for l in est.log[:30])
        corpo = ("".join(blocos) or card('<div class="empty">Nenhum rateio ainda. Agende uma abertura ou poste um decant no grupo.</div>')) + card(f"<h2>Últimas ações</h2><div style='margin-top:10px'>{logs or '<p class=hint>Nada registrado.</p>'}</div>", tight=False)
        abertos = len(est.rateios_abertos())
        return tela("Ao vivo", f"{abertos} rateio{'s' if abertos != 1 else ''} aberto{'s' if abertos != 1 else ''} agora", corpo, "vivo")

    def proxima_abertura(horas: float):
        """abertura agendada que ainda vai abrir nas proximas N horas (a mais cedo)"""
        ag = agora()
        vem = [a for a in arm.estado.aberturas if a.status in ("agendada", "contagem")
               and 0 <= (datetime.fromisoformat(a.abre_em) - ag).total_seconds() <= horas * 3600]
        return min(vem, key=lambda a: a.abre_em) if vem else None

    @app.get("/saude")
    def saude():
        """Sem senha, pro monitor externo (UptimeRobot): 200 = tudo certo; 503 = alguem precisa olhar."""
        from fastapi.responses import PlainTextResponse
        import time as _t
        wa = motor.wa
        if not getattr(wa, "conectado", False) and _t.time() - getattr(wa, "caiu_em", 0) > 180:
            return PlainTextResponse(f"robo sem WhatsApp ha {int((_t.time() - wa.caiu_em) // 60)} min", 503)
        ab = proxima_abertura(1)
        if arm.estado.modo in ("desligado", "observando") and ab:
            return PlainTextResponse(f"robo {arm.estado.modo} com abertura as {hora(ab.abre_em)}", 503)
        return PlainTextResponse("ok")

    @app.post("/modo", dependencies=dep)
    def mudar_modo(modo: str = Form(...), confirmar: str = Form("")):
        ab = proxima_abertura(2)
        if modo in ("desligado", "observando") and ab and not confirmar:
            aviso = (f'<h2>Tem abertura às {hora(ab.abre_em)}</h2>'
                     f'<p style="margin:10px 0 0">O <b>{e(ab.nome)}</b> abre às {hora(ab.abre_em)}. Com o robô em '
                     f'<b>{"Desligado" if modo == "desligado" else "Observando"}</b>, ele <b>não fecha nem abre o grupo</b> '
                     f'e não posta nada dessa abertura.</p>'
                     f'<div class="actions">{botao("Desligar mesmo assim", "/modo", estilo="vinho", icone="✕", hidden={"modo": modo, "confirmar": "1"})}'
                     f'<a class="btn ghost sm" href="/">Deixar ligado <span class="ic">✓</span></a></div>')
            return tela("Tem certeza?", "Abertura chegando", card(aviso), "vivo")
        with arm as est:
            if modo in MODOS:
                est.modo = modo
                est.registrar("painel", f"modo → {modo}")
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/remover", dependencies=dep)
    async def remover(rid: str, i: int = Form(...)):
        with arm as est:
            r = est.rateio(rid)
            if r and 0 <= i < len(r.pedidos):
                p = r.pedidos.pop(i)
                est.para_aprender("correcao", f"Removido {p.ml} ml de {p.nome} no {r.nome}", perfume=r.nome, acao="removeu",
                                  ml=p.ml, nome=p.nome)
                if r.status == "fechado" and r.disponivel > 0:
                    r.status, r.fechado_em = "aberto", None
                est.registrar("painel", f"removido {p.ml}ml {p.nome} de {r.nome}")
                est.resolver_divergencias(r)
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/renomear", dependencies=dep)
    async def renomear(rid: str, i: int = Form(...), nome: str = Form("")):
        with arm as est:
            r = est.rateio(rid)
            if r and 0 <= i < len(r.pedidos) and nome.strip():
                antigo, r.pedidos[i].nome = r.pedidos[i].nome, nome.strip()
                est.para_aprender("correcao", f"Nome corrigido: {antigo} → {nome.strip()} no {r.nome}", perfume=r.nome,
                                  acao="renomeou", nome=nome.strip())
                est.registrar("painel", f"nome corrigido: {antigo} → {nome.strip()} em {r.nome}")
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/editar", dependencies=dep)
    async def editar(rid: str, i: int = Form(...), nome: str = Form(""), ml: str = Form(""), fone_novo: str = Form("", alias="fone")):
        """corrige nome e/ou quantidade de um pedido (ex. APC 35 + 5 = 40), sem perder o numero de quem pediu"""
        from urllib.parse import quote
        with arm as est:
            r = est.rateio(rid)
            if not r or not (0 <= i < len(r.pedidos)):
                return RedirectResponse("/", 303)
            p = r.pedidos[i]
            try:
                novo_ml = int(ml) if ml.strip() else p.ml
            except ValueError:
                return RedirectResponse("/?aviso=" + quote("Quantidade inválida."), 303)
            if novo_ml <= 0:
                return RedirectResponse("/?aviso=" + quote("Informe os ml (pra tirar o pedido, use o ✕)."), 303)
            if novo_ml - p.ml > r.disponivel:
                return RedirectResponse("/?aviso=" + quote(f"Não cabe: sobram {r.disponivel} ml no {r.nome}."), 303)
            antes = f"{p.ml} ml {p.nome}"
            p.nome, p.ml = (nome.strip() or p.nome), novo_ml
            if fone(fone_novo):   # pedido do privado: com o numero a lista passa a marcar a pessoa
                p.autor_id = fone(fone_novo) + "@s.whatsapp.net"
                est.registrar("painel", f"número de {p.nome} adicionado em {r.nome}")
            depois = f"{p.ml} ml {p.nome}"
            if antes != depois:
                if r.disponivel <= 0 and r.status == "aberto":
                    r.status, r.fechado_em = "fechado", r.fechado_em or agora().isoformat()
                elif r.status == "fechado" and r.disponivel > 0:
                    r.status, r.fechado_em = "aberto", None
                est.para_aprender("correcao", f"Pedido corrigido: {antes} → {depois} no {r.nome}", perfume=r.nome,
                                  acao="editou", ml=p.ml, nome=p.nome)
                est.registrar("painel", f"pedido corrigido: {antes} → {depois} em {r.nome}")
                est.resolver_divergencias(r)
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/add", dependencies=dep)
    async def adicionar(rid: str, ml: str = Form(""), nome: str = Form(""), apc: str = Form(""), fone_novo: str = Form("", alias="fone")):
        from urllib.parse import quote
        with arm as est:
            r = est.rateio(rid)
            if not r:
                return RedirectResponse("/", 303)
            import re as _re
            nome = _re.sub(r"@\S+", "", nome).strip()
            if not nome:
                return RedirectResponse("/?aviso=" + quote("Escreva o nome de quem pediu."), 303)
            if apc and not r.apc_ml:
                return RedirectResponse("/?aviso=" + quote(f"O {r.nome} não tem APC."), 303)
            if apc and r.dono_apc:
                return RedirectResponse("/?aviso=" + quote(f"O APC do {r.nome} já é de {r.dono_apc.nome}. Remova antes de trocar."), 303)
            try:
                q = r.apc_ml if apc else int(ml or 0)
            except ValueError:
                return RedirectResponse("/?aviso=" + quote("Quantidade inválida."), 303)
            if q <= 0:
                return RedirectResponse("/?aviso=" + quote("Informe os ml."), 303)
            if q > r.disponivel:
                return RedirectResponse("/?aviso=" + quote(f"Não cabe: sobram {r.disponivel} ml no {r.nome}. Remova um pedido antes."), 303)
            autor_id = (fone(fone_novo) + "@s.whatsapp.net") if fone(fone_novo) else numero_conhecido(est, nome)
            r.pedidos.append(Pedido(autor_id, None, agora().isoformat(), nome.strip(), q, apc=bool(apc)))
            est.para_aprender("correcao", f"Adicionado {q} ml de {nome.strip()} no {r.nome}", perfume=r.nome, acao="adicionou",
                              ml=q, nome=nome.strip())
            if r.disponivel <= 0:
                r.status, r.fechado_em = "fechado", r.fechado_em or agora().isoformat()
            est.registrar("painel", f"adicionado {q}ml {nome.strip()} em {r.nome}")
            est.resolver_divergencias(r)
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/reabrir", dependencies=dep)
    async def reabrir(rid: str):
        from urllib.parse import quote
        with arm as est:
            r = est.rateio(rid)
            if not r:
                return RedirectResponse("/", 303)
            if r.disponivel <= 0:
                return RedirectResponse("/?aviso=" + quote(f"O {r.nome} está cheio. Remova um pedido que ele reabre sozinho."), 303)
            r.status, r.fechado_em = "aberto", None
            est.registrar("painel", f"rateio reaberto à mão: {r.nome}")
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/pausar", dependencies=dep)
    async def pausar(rid: str):
        with arm as est:
            r = est.rateio(rid)
            if r and r.status == "aberto":
                r.status, r.lista_pendente = "pausado", False
                est.registrar("painel", f"rateio pausado: {r.nome}")
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/retomar", dependencies=dep)
    async def retomar(rid: str):
        with arm as est:
            r = est.rateio(rid)
            if r and r.status == "pausado":
                r.status = "fechado" if r.disponivel <= 0 else "aberto"
                est.registrar("painel", f"rateio retomado: {r.nome}")
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/excluir", dependencies=dep)
    async def excluir(rid: str):
        with arm as est:
            r = est.rateio(rid)
            if r:
                est.rateios = [x for x in est.rateios if x.id != rid]
                for a in est.aberturas:   # a abertura ligada nao pode voltar a abrir/postar sozinha
                    if a.rateio_id == rid and a.status in ("agendada", "contagem", "aberta"):
                        a.status = "cancelada"
                est.registrar("painel", f"rateio excluido: {r.nome} ({r.reservado}/{r.total_ml} ml, {len(r.pedidos)} pedidos)")
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/postar", dependencies=dep)
    async def postar(rid: str):
        await motor.forcar_lista(rid)
        return RedirectResponse("/", 303)

    @app.post("/rateio/{rid}/fechar", dependencies=dep)
    async def fechar(rid: str):
        await motor.fechar_rateio(rid)
        return RedirectResponse("/", 303)

    # ------------------------------------------------------------ aprender
    EXEMPLOS = Path("data/exemplos.jsonl")

    @app.get("/aprender", response_class=HTMLResponse, dependencies=dep)
    def aprender(ver: str = "pendentes"):
        est = arm.estado
        itens = [a for a in est.aprender if (a["status"] == "pendente") == (ver == "pendentes")][:60]
        abertos = sorted({r.nome for r in est.rateios[:15]})
        opcoes = "".join(f'<option value="{e(n)}">{e(n)}</option>' for n in abertos)
        cards = []
        for a in itens:
            quando = datetime.fromisoformat(a["em"]).strftime("%d/%m %H:%M")
            topo = f'<div class="card-title"><h2 style="font-size:1rem"><span class="tag {e(a["tipo"])}">{e(a["tipo"])}</span>{e(a.get("autor") or a.get("perfume") or "")}</h2><small>{quando}</small></div>'
            if a["tipo"] == "duvida":
                corpo = f'<pre>{e(a["texto"])}</pre><div class="hint">motivo: {e(a.get("motivo", ""))}</div>'
                acao = f"""<form method="post" action="/aprender/{a['id']}" class="add">
  <input type="hidden" name="rotulo" value="pedido"><input class="ml" name="ml" placeholder="ml" inputmode="numeric">
  <select name="perfume" style="flex:1;min-width:160px"><option value="">perfume…</option>{opcoes}</select>
  <label class="check" style="margin:0"><input type="checkbox" name="apc"> APC</label><button class="btn sm">Era pedido <span class="ic">✓</span></button></form>
<div class="actions">{botao("Não era pedido", f"/aprender/{a['id']}", hidden={"rotulo": "nada"}, icone="✕")}</div>"""
            elif a["tipo"] == "divergencia":
                corpo = (f'<div class="grid2"><div><label>Robô tinha</label><pre>{e(chr(10).join(a.get("robo", [])) or "(vazio)")}</pre></div>'
                         f'<div><label>Admin postou</label><pre>{e(chr(10).join(a.get("admin", [])) or "(vazio)")}</pre></div></div>')
                acao = ('<div class="actions">' + botao("Robô errou", f"/aprender/{a['id']}", hidden={"rotulo": "robo_errou"}, estilo="vinho", icone="✕")
                        + botao("Admin corrigiu à mão (ok)", f"/aprender/{a['id']}", hidden={"rotulo": "admin_ajustou"}, icone="✓") + "</div>")
            else:
                corpo = f'<div class="meta">{e(a["texto"])}</div>'
                acao = ('<div class="actions">' + botao("Robô tinha errado", f"/aprender/{a['id']}", hidden={"rotulo": "robo_errou"}, estilo="vinho", icone="✕")
                        + botao("Só ajuste nosso", f"/aprender/{a['id']}", hidden={"rotulo": "ajuste"}, icone="✓") + "</div>")
            if a["status"] == "registrado":
                acao = '<div class="hint">só registro, não precisa revisar</div>'
            elif a["status"] != "pendente":
                acao = f'<div class="hint">marcado: <b>{e(str(a.get("rotulo")))}</b></div>'
            cards.append(card(topo + corpo + acao))
        n_pend = sum(1 for a in est.aprender if a["status"] == "pendente")
        n_ex = sum(1 for _ in EXEMPLOS.open(encoding="utf-8")) if EXEMPLOS.exists() else 0
        abas = (f'<div class="actions" style="margin:0 0 6px"><a class="btn {"" if ver == "pendentes" else "ghost"} sm" href="/aprender">Pendentes ({n_pend})</a>'
                f'<a class="btn {"" if ver != "pendentes" else "ghost"} sm" href="/aprender?ver=revisados">Revisados</a></div>')
        explica = card(f'<p style="margin:0">O que o robô não soube resolver, onde a lista dele ficou diferente da do admin, e as correções feitas à mão. '
                       f'Cada marcação vira um exemplo real ({n_ex} até agora) que é usado pra melhorar as regras.</p>', tight=True)
        return tela("Aprender", "Casos pra revisar com um clique.", explica + abas + ("".join(cards) or card('<div class="empty">Nada pendente. 🎉</div>')), "aprender")

    @app.post("/aprender/{aid}", dependencies=dep)
    async def rotular(aid: str, rotulo: str = Form(...), ml: str = Form(""), perfume: str = Form(""), apc: str = Form("")):
        import json
        with arm as est:
            a = next((x for x in est.aprender if x["id"] == aid), None)
            if not a:
                return RedirectResponse("/aprender", 303)
            a["status"], a["rotulo"] = "revisado", rotulo
            exemplo = {"em": a["em"], "tipo": a["tipo"], "texto": a["texto"], "rotulo": rotulo}
            if rotulo == "pedido":
                exemplo.update({"ml": int(ml) if ml.strip().isdigit() else None, "perfume": perfume or None, "apc": bool(apc)})
                a["rotulo"] = f"pedido {'APC' if apc else (ml or '?') + ' ml'} {perfume}".strip()
                # e ja coloca na lista do perfume (se estiver aberto), com o numero de quem mandou
                rat = next((x for x in est.rateios_abertos() if x.nome == perfume), None)
                q = (rat.apc_ml if apc else (int(ml) if ml.strip().isdigit() else 0)) if rat else 0
                if rat and q and q <= rat.disponivel and not (apc and rat.dono_apc):
                    from .texto import primeiro_nome
                    rat.pedidos.append(Pedido(a.get("autor_id"), a.get("msg_id"), agora().isoformat(),
                                              primeiro_nome(a.get("autor") or "") or "Acervista", q, apc=bool(apc)))
                    if rat.disponivel <= 0:
                        rat.status, rat.fechado_em = "fechado", agora().isoformat()
                    a["rotulo"] += " (entrou na lista)"
                    est.registrar("painel", f"Aprender: {q}ml {primeiro_nome(a.get('autor') or '')} adicionado em {rat.nome}")
            for k in ("robo", "admin", "perfume", "acao", "abertos", "motivo"):
                if k in a and k not in exemplo:
                    exemplo[k] = a[k]
            EXEMPLOS.parent.mkdir(parents=True, exist_ok=True)
            with EXEMPLOS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(exemplo, ensure_ascii=False) + "\n")
            est.registrar("aprender", f"{a['tipo']} marcado como {a['rotulo']}")
        return RedirectResponse("/aprender", 303)

    # ------------------------------------------------------------ agenda
    @app.get("/agenda", response_class=HTMLResponse, dependencies=dep)
    def agenda():
        est = arm.estado
        itens = []
        for a in sorted(est.aberturas, key=lambda x: x.abre_em, reverse=True)[:20]:
            abre = datetime.fromisoformat(a.abre_em).strftime("%d/%m às %H:%M")
            datas = (f'<div class="datas"><span><small>data</small>{data_longa(a.abre_em)}</span>'
                     f'<span><small>abertura programada</small>{hora(a.abre_em)}</span>'
                     f'<span><small>abriu de fato</small>{hora(a.abriu_em)}</span>'
                     f'<span><small>frasco fechou</small>{hora(a.encerrou_em)}</span></div>')
            btns = ""
            if a.status in ("agendada", "contagem"):
                btns = botao("Abrir agora", f"/abertura/{a.id}/abrir", icone="↗") + botao("Cancelar", f"/abertura/{a.id}/cancelar", estilo="x", icone="✕")
            aviso = ""
            if a.aviso_em:
                aviso_h = datetime.fromisoformat(a.aviso_em).strftime("%H:%M")
                aviso = f'<div class="meta">📣 aviso às {aviso_h}{" · enviado" if a.aviso_feito else ""}</div><details><summary>texto do aviso</summary><pre>{e(a.aviso_texto)}</pre></details>'
            mini = f'<img class="thumb" src="{foto_url(a.foto)}" alt="">' if a.foto else ""
            itens.append(card(f"""{mini}<div class="card-title"><h2>{e(a.nome)}</h2><small>{ROTULO_STATUS.get(a.status, a.status)}</small></div>
{datas}<div class="meta">{a.total_ml} ml · {brl(a.valor_ml)}/ml{" · APC " + str(a.apc_ml) + " ml" if a.apc_ml else ""}</div>{aviso}
<div class="actions">{btns}</div>"""))
        topo = card(f'<div class="actions" style="margin:0">{botao("Abrir grupo agora", "/grupo/abrir", icone="🔓")}{botao("Fechar grupo agora", "/grupo/fechar", estilo="vinho", icone="🔒")}<a class="btn" href="/nova">Nova abertura <span class="ic">+</span></a></div>', tight=True)
        futuras = sum(1 for a in est.aberturas if a.status in ("agendada", "contagem"))
        return tela("Agenda", f"{futuras} abertura{'s' if futuras != 1 else ''} programada{'s' if futuras != 1 else ''}", topo + ("".join(itens) or card('<div class="empty">Nada agendado ainda.</div>')), "agenda")

    @app.get("/fotos/{nome}", dependencies=dep)
    def foto(nome: str):
        caminho = FOTOS / Path(nome).name
        if not caminho.exists():
            raise HTTPException(404)
        return FileResponse(caminho)

    @app.get("/nova", response_class=HTMLResponse, dependencies=dep)
    def nova():
        est = arm.estado
        cfg = est.config
        hoje = agora().strftime("%Y-%m-%d")
        vistas, anteriores = set(), []
        for a in sorted(est.aberturas, key=lambda x: x.abre_em, reverse=True):
            if a.foto and a.foto not in vistas and Path(a.foto).exists():
                vistas.add(a.foto)
                anteriores.append(a)
        # as 4 mais recentes aparecem; o resto fica atras do "ver mais" (com busca pelo nome)
        galeria = "".join(
            f'<label{" class=mais hidden" if n >= 4 else ""} data-nome="{e(a.nome.lower())}"><input type="radio" name="foto_anterior" value="{e(Path(a.foto).name)}" onchange="usarAnterior(this)" hidden><img src="{foto_url(a.foto)}" alt="" loading="lazy"><span class="hint">{e(a.nome[:20])}</span></label>'
            for n, a in enumerate(anteriores[:60]))
        if len(anteriores) > 4:
            galeria += (f'<button type="button" class="btn ghost sm gal-mais" onclick="verMaisFotos(this)">Ver mais ({min(len(anteriores), 60) - 4}) <span class="ic">▾</span></button>'
                        '<input class="gal-busca" hidden placeholder="Buscar pelo nome do perfume" oninput="buscarFoto(this.value)">')
        corpo = card(f"""<form method="post" action="/nova" enctype="multipart/form-data">
<h2>O perfume</h2>
<label>Nome, como vai aparecer no post</label><input name="nome" placeholder="UNIQUE'E LUXURY | CHICELLE" required>
<div class="grid2"><div><label>Valor por ml (R$)</label><input name="valor_ml" type="number" step="0.01" inputmode="decimal" required></div>
<div><label>Tamanho do frasco (ml)</label><input name="total_ml" type="number" inputmode="numeric" required></div>
<div><label>Pedido mínimo (ml)</label><input name="minimo" type="number" value="3"></div>
<div><label>APC (ml) · vazio se não tiver</label><input name="apc_ml" type="number" value="20"></div></div>
<label>Tamanhos oferecidos</label><input name="tamanhos" value="3,5,10,15,20">
<label>Foto do perfume · obrigatória</label><input name="foto" type="file" accept="image/*" onchange="previa(this)">
<img id="previa" style="display:none;max-width:240px;border-radius:18px;margin:8px 0">
{f'<label>ou usar uma foto já enviada</label><div class="gal">{galeria}</div>' if galeria else ''}
<label>Texto extra do post (pagamento, frete)</label><textarea name="texto_extra" rows="4">Pagamento via PIX ou cartão em até 12x com taxa.

O pagamento deverá ser realizado apenas aos administradores: @~Financeiro

Frete grátis: Americana, SBO e Nova Odessa.</textarea>
<div class="sep"></div><h2>Horários</h2>
<div class="grid2"><div><label>Dia</label><input name="dia" type="date" value="{hoje}" required></div>
<div><label>Abre às</label><input name="abre" type="time" value="18:00" required></div>
<div><label>Aviso "abertura de hoje" às · vazio = não manda</label><input name="aviso_hora" type="time" value="11:00"></div></div>
<div class="sep"></div><h2>Aviso de abertura</h2>
<label>Descrição do perfume (1 ou 2 frases)</label><textarea name="descricao" rows="3" placeholder="Uma fragrância doce, cremosa e feminina, com morango, flores delicadas, pralinê e baunilha..."></textarea>
<label>Texto do aviso <span class="hint">{{nome}}, {{hora}} e {{descricao}} são preenchidos na hora</span></label><textarea name="aviso_modelo" rows="8">{e(cfg.textos.get("aviso", ""))}</textarea>
<p class="hint" id="erro-foto" style="display:none;color:var(--vinho);font-weight:600">Escolha a foto do perfume antes de agendar.</p>
<div class="actions"><button class="btn ouro" style="padding:12px 20px">Agendar abertura <span class="ic">→</span></button></div></form>
<script>
document.querySelector('form[action="/nova"]').addEventListener('submit',ev=>{{
  const f=document.querySelector('[name=foto]');const ant=document.querySelector('[name=foto_anterior]:checked');
  if(!f.files[0]&&!ant){{ev.preventDefault();const p=document.getElementById('erro-foto');p.style.display='block';f.scrollIntoView({{behavior:'smooth',block:'center'}})}}
}});
function previa(inp){{const img=document.getElementById('previa');if(!inp.files[0]){{img.style.display='none';return}}
img.src=URL.createObjectURL(inp.files[0]);img.style.display='block';document.querySelectorAll('[name=foto_anterior]').forEach(r=>r.checked=false)}}
function usarAnterior(r){{const f=document.querySelector('[name=foto]');f.value='';const img=document.getElementById('previa');img.src='/fotos/'+r.value;img.style.display='block'}}
function verMaisFotos(b){{const abrir=b.dataset.aberto!=='1';b.dataset.aberto=abrir?'1':'';document.querySelectorAll('.gal label.mais').forEach(l=>l.hidden=!abrir);const q=document.querySelector('.gal-busca');q.hidden=!abrir;if(!abrir){{q.value='';buscarFoto('')}}b.dataset.txt=b.dataset.txt||b.firstChild.textContent;b.firstChild.textContent=abrir?'Ver menos ':b.dataset.txt;if(abrir)q.focus()}}
function buscarFoto(t){{t=t.trim().toLowerCase();document.querySelectorAll('.gal label').forEach(l=>{{if(!t){{l.hidden=l.classList.contains('mais')&&document.querySelector('.gal-mais').dataset.aberto!=='1';return}}l.hidden=!l.dataset.nome.includes(t)}})}}
</script>""")
        return tela("Nova abertura", "Preencha uma vez; o robô cuida do aviso, da contagem, do post e do fechamento.", corpo, "nova")

    @app.post("/nova", dependencies=dep)
    async def criar(nome: str = Form(...), valor_ml: float = Form(...), total_ml: int = Form(...), minimo: int = Form(3),
                    tamanhos: str = Form("3,5,10,15,20"), apc_ml: str = Form(""), texto_extra: str = Form(""),
                    dia: str = Form(...), abre: str = Form(...), foto: UploadFile | None = None,
                    foto_anterior: str = Form(""), descricao: str = Form(""), aviso_hora: str = Form(""), aviso_modelo: str = Form("")):
        abre_dt = datetime.fromisoformat(f"{dia}T{abre}").replace(tzinfo=SP)
        fecha_dt = abre_dt + timedelta(hours=24)   # so registro; o grupo nao fecha por horario
        caminho = None
        if foto_anterior and (FOTOS / Path(foto_anterior).name).exists():
            caminho = str(FOTOS / Path(foto_anterior).name)
        elif foto and foto.filename:
            FOTOS.mkdir(parents=True, exist_ok=True)
            caminho = str(FOTOS / f"{novo_id()}{Path(foto.filename).suffix.lower() or '.jpg'}")
            Path(caminho).write_bytes(await foto.read())
        if not caminho:
            return HTMLResponse(pagina("Falta a foto", "Toda abertura sai com a imagem do perfume.", card('<div class="empty">Volte e escolha a foto do perfume (nova ou uma já enviada).<div class="actions" style="justify-content:center"><a class="btn" href="/nova">Voltar <span class="ic">←</span></a></div></div>'),
                                       ativo="nova", modo=arm.estado.modo, conectado=motor.wa.conectado, grupo_aberto=arm.estado.grupo_aberto, grupo_nome=arm.estado.config.grupo_nome), status_code=400)
        ab = Abertura(id=novo_id(), nome=nome.strip(), valor_ml=valor_ml, total_ml=total_ml, minimo=minimo,
                      tamanhos=[int(t) for t in tamanhos.replace(" ", "").split(",") if t], apc_ml=int(apc_ml) if apc_ml.strip() else None,
                      abre_em=abre_dt.isoformat(), fecha_em=fecha_dt.isoformat(), foto=caminho, texto_extra=texto_extra,
                      descricao=descricao.strip())
        if aviso_hora.strip():
            aviso_dt = datetime.fromisoformat(f"{dia}T{aviso_hora}").replace(tzinfo=SP)
            if aviso_dt < abre_dt:
                ab.aviso_em = aviso_dt.isoformat()
                ab.aviso_texto = (aviso_modelo or arm.estado.config.textos["aviso"]).replace("{nome}", ab.nome).replace("{hora}", ab.hora_curta).replace("{descricao}", ab.descricao)
                ab.aviso_texto = ab.aviso_texto.replace("\n\n\n", "\n\n").strip()
        with arm as est:
            est.aberturas.append(ab)
            est.registrar("painel", f"agendado: {ab.nome} {abre_dt:%d/%m %H:%M}")
        return RedirectResponse("/agenda", 303)

    @app.post("/abertura/{aid}/abrir", dependencies=dep)
    async def abrir_agora(aid: str):
        await motor.abrir_agora(aid)
        return RedirectResponse("/", 303)

    @app.post("/abertura/{aid}/cancelar", dependencies=dep)
    async def cancelar(aid: str):
        with arm as est:
            a = est.abertura(aid)
            if a:
                a.status = "cancelada"
        return RedirectResponse("/agenda", 303)

    @app.post("/grupo/abrir", dependencies=dep)
    async def grupo_abrir():
        await motor.abrir_grupo_agora()
        return RedirectResponse("/agenda", 303)

    @app.post("/grupo/fechar", dependencies=dep)
    async def grupo_fechar():
        await motor.fechar_grupo_agora()
        return RedirectResponse("/agenda", 303)

    # ------------------------------------------------------------ conexao / ajustes
    @app.get("/conexao", response_class=HTMLResponse, dependencies=dep)
    async def conexao():
        wa = motor.wa
        cfg = arm.estado.config
        if wa.conectado:
            try:
                lista = await wa.grupos()
            except Exception:  # noqa: BLE001
                lista = []
            linhas = "".join(
                f'<div class="row"><span class="gem">{"✅" if g["jid"] == cfg.grupo_jid else "·"}</span><span class="grow"><b>{e(g["nome"])}</b><div class="hint">{g["pessoas"]} pessoas · {"admin" if g["sou_admin"] else "⚠️ o chip não é admin"} · {"fechado" if g["fechado"] else "aberto"}</div></span>'
                + botao("Usar este", "/conexao/escolher", hidden={"jid": g["jid"], "nome": g["nome"]}) + "</div>"
                for g in lista)
            grupo = f'<b>{e(cfg.grupo_nome)}</b> <span class="hint">{e(cfg.grupo_jid)}</span>' if cfg.grupo_jid else f'⚠️ grupo <b>{e(cfg.grupo_nome)}</b> não encontrado'
            corpo = card(f'<h2>Conectado</h2><div class="meta">chip <b>{e(wa.meu_jid)}</b></div><div class="meta">robô apontado para {grupo}</div>') \
                + card(f'<h2>Grupos em que o chip está</h2><p class="hint">Clique em "Usar este" para apontar o robô.</p><div style="margin-top:8px">{linhas or "<p class=hint>nenhum grupo encontrado</p>"}</div>')
            sub = "Tudo certo por aqui."
        elif wa.qr_svg:
            corpo = card(f'<h2>Escaneie com o celular do chip</h2><p class="hint">WhatsApp → Aparelhos conectados → Conectar aparelho</p><div class="qr">{wa.qr_svg}</div><p class="hint">O código muda a cada ~20 s e esta página se atualiza sozinha. Se o celular disser "não foi possível conectar", espere o próximo código.</p><script>setTimeout(()=>location.reload(),10000)</script>')
            sub = "Aguardando o chip."
        else:
            corpo = card('<div class="empty">Gerando um QR novo… esta página se atualiza sozinha.</div><script>setTimeout(()=>location.reload(),8000)</script>')
            sub = "Aguardando o WhatsApp."
        return tela("Conexão", sub, corpo, "conexao")

    @app.post("/conexao/escolher", dependencies=dep)
    async def escolher_grupo(jid: str = Form(...), nome: str = Form(...)):
        with arm as est:
            if jid != est.config.grupo_jid:
                est.rateios = [r for r in est.rateios if r.status != "aberto"]
            est.config.grupo_jid, est.config.grupo_nome = jid, nome
            est.grupo_aberto = None
            est.registrar("conexao", f"robô apontado pro grupo: {nome} ({jid})")
        return RedirectResponse("/conexao", 303)

    @app.post("/conexao/grupo", dependencies=dep)
    async def achar_grupo():
        await motor.descobrir_grupo()
        return RedirectResponse("/conexao", 303)

    @app.get("/config", response_class=HTMLResponse, dependencies=dep)
    def config():
        c = arm.estado.config
        rotulos = {"aviso": "Aviso de abertura", "fechar_antes": "Fechando o grupo antes", "contagem": "Contagem regressiva", "aberto": "Grupo aberto",
                   "chamada": "Chamada sem interação (1ª)", "chamada_2": "Chamada sem interação (2ª)", "chamada_3": "Chamada sem interação (3ª)", "ultimos": "Últimos ml (1º aviso)", "ultimos_2": "Últimos ml (2º aviso)", "ultimos_3": "Últimos ml (3º aviso)", "fechado_frasco": "Frasco fechado"}
        tx = "".join(f"<label>{e(rotulos.get(k, k))}</label><textarea name='tx_{k}' rows='{3 if chr(10) in v else 1}'>{e(v)}</textarea>" for k, v in c.textos.items())
        corpo = card(f"""<form method="post" action="/config">
<h2>Grupo e admins</h2>
<label>Nome exato do grupo</label><input name="grupo_nome" value="{e(c.grupo_nome)}">
<label>Telefones dos admins (com 55, separados por vírgula)</label><input name="admins" value="{e(','.join(c.admins))}">
<label>Telefone que recebe a lista no modo sombra e as dúvidas</label><input name="avisar_admin" value="{e(c.avisar_admin)}">
<div class="sep"></div><h2>Ritmo</h2>
<div class="grid2">
<div><label>Segundos juntando pedidos antes da lista</label><input name="segundos" type="number" value="{c.segundos_ate_postar_lista}"></div>
<div><label>Fechar o grupo quantos minutos antes da abertura</label><input name="fechar_antes" type="number" value="{c.fechar_antes_min}"></div>
<div><label>Contagem regressiva (minutos antes)</label><input name="contagem" value="{','.join(map(str, c.contagem_min))}"></div>
<div><label>Aviso de "últimos ml" quando sobrar até</label><input name="ultimos" type="number" value="{c.aviso_ultimos_ml}"></div>
<div><label>Repetir esse aviso a cada (min) · 0 = uma vez</label><input name="urg_min" type="number" value="{c.urgencia_a_cada_min}"></div>
<div><label>Máximo de avisos por perfume</label><input name="urg_max" type="number" value="{c.urgencia_max}"></div>
<div><label>Chamada se ninguém interagir por (min) · 0 = desliga</label><input name="cham_min" type="number" value="{c.chamada_silencio_min}"></div>
<div><label>Máximo de chamadas por perfume</label><input name="cham_max" type="number" value="{c.chamada_max}"></div>
<div><label>Pedido solto com vários perfumes abertos</label><select name="sem_reply"><option value="recente" {"selected" if c.sem_reply == "recente" else ""}>vai pro mais recente</option><option value="perguntar" {"selected" if c.sem_reply == "perguntar" else ""}>não anota, avisa o admin</option></select></div>
</div>
<label class="check"><input type="checkbox" name="reagir" {"checked" if c.reagir_pedido else ""}> Reagir nos pedidos com</label> <input name="emoji_reacao" value="{e(c.emoji_reacao)}" style="width:64px;text-align:center;margin-left:6px">
<label class="check"><input type="checkbox" name="erro_grupo" {"checked" if c.responder_erro_no_grupo else ""}> Responder "restam só X ml" no grupo (senão só avisa o admin)</label>
<label class="check"><input type="checkbox" name="admin_abre" {"checked" if c.post_do_admin_abre else ""}> Post que um admin manda pelo celular já abre o rateio (desligado: entra <b>pausado</b> e só conta depois do Retomar)</label>
<div class="sep"></div><h2>Como pedir (regras pro grupo)</h2>
<p class="hint">Sai {c.regras_antes_min} min antes de cada abertura e, ao longo do dia, no máximo a cada {c.regras_a_cada_h} h (só com o grupo aberto, perfume aberto e pedido novo desde a última vez). Deixe em branco pra não mandar.</p>
<div class="grid2"><div><label>Mandar X min antes da abertura (0 = não)</label><input name="regras_antes" type="number" value="{c.regras_antes_min}"></div>
<div><label>Repetir no dia a cada X horas (0 = só antes da abertura)</label><input name="regras_cada" type="number" value="{c.regras_a_cada_h}"></div>
<div><label>Horário em que pode repetir</label><input name="regras_horario" value="{e(c.regras_horario)}" placeholder="09:00-21:00"></div></div>
<label>Texto</label><textarea name="regras_texto" rows="14">{e(c.regras_texto)}</textarea>
<div class="sep"></div><h2>Textos</h2><p class="hint">{{nome}}, {{hora}}, {{min}}, {{ml}} e {{data}} são trocados na hora.</p>{tx}
<div class="actions"><button class="btn ouro" style="padding:12px 20px">Salvar ajustes <span class="ic">✓</span></button></div></form>""")
        return tela("Ajustes", "Como o robô fala e em que ritmo.", corpo, "config")

    @app.post("/config", dependencies=dep)
    async def salvar_config(request: Request):
        f = await request.form()
        with arm as est:
            c = est.config
            nome_novo = f.get("grupo_nome", c.grupo_nome).strip()
            if nome_novo != c.grupo_nome:
                c.grupo_jid = ""
                est.rateios = [r for r in est.rateios if r.status != "aberto"]
            c.grupo_nome = nome_novo
            c.admins = [x for x in (fone(a) for a in f.get("admins", "").split(",")) if x]
            c.avisar_admin = fone(f.get("avisar_admin", ""))
            c.segundos_ate_postar_lista = int(f.get("segundos") or 60)
            c.aviso_ultimos_ml = int(f.get("ultimos") or 10)
            c.contagem_min = [int(x) for x in f.get("contagem", "").split(",") if x.strip().isdigit()]
            c.hora_fechar_padrao = f.get("hora_fechar", "22:00")
            if "regras_texto" in f:
                c.regras_texto = f.get("regras_texto", "").replace("\r\n", "\n").strip()
                c.regras_antes_min = int(f.get("regras_antes") or 0)
                c.regras_a_cada_h = int(f.get("regras_cada") or 0)
                c.regras_horario = (f.get("regras_horario") or "09:00-21:00").strip()
            c.fechar_antes_min = int(f.get("fechar_antes") or 0)
            c.urgencia_a_cada_min = int(f.get("urg_min") or 0)
            c.urgencia_max = int(f.get("urg_max") or 1)
            c.chamada_silencio_min = int(f.get("cham_min") or 0)
            c.chamada_max = int(f.get("cham_max") or 0)
            c.sem_reply = f.get("sem_reply", "recente")
            c.reagir_pedido = "reagir" in f
            c.emoji_reacao = (f.get("emoji_reacao") or "👍").strip()[:4]
            c.responder_erro_no_grupo = "erro_grupo" in f
            c.post_do_admin_abre = "admin_abre" in f
            for k in list(c.textos):
                if f.get(f"tx_{k}"):
                    c.textos[k] = f[f"tx_{k}"]
            est.registrar("painel", "ajustes salvos")
        if not arm.estado.config.grupo_jid and motor.wa.conectado:
            await motor.descobrir_grupo()
            return RedirectResponse("/conexao", 303)
        return RedirectResponse("/config", 303)

    return app
