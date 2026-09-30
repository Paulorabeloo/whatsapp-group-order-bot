"""Casca visual do painel: layout, CSS e pecinhas de HTML. Nada de regra de negocio aqui.

Visual: creme quente, dourado, texto espresso, serif editorial (Fraunces) + Plus Jakarta Sans.
"""

from __future__ import annotations

import html

e = html.escape

CSS = """
:root{
  --creme:#F3F2EF;--creme-2:#E8E6E1;--papel:#FAFAF8;--espresso:#1D2226;--cafe:#454D55;--areia:#868D95;
  --ouro:#2F6F62;--ouro-2:#5A9A8B;--ouro-suave:rgba(47,111,98,.13);--verde:#3F7D5B;--verde-suave:rgba(63,125,91,.14);
  --vinho:#8E3B3B;--vinho-suave:rgba(142,59,59,.12);--linha:rgba(29,34,38,.08);
  --r:1.75rem;--r-in:calc(1.75rem - .5rem);--ease:cubic-bezier(.32,.72,0,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--creme);color:var(--espresso);font-family:"Plus Jakarta Sans",system-ui,sans-serif;font-size:15px;line-height:1.5;
  background-image:radial-gradient(900px 500px at 10% -10%,rgba(90,154,139,.16),transparent 60%),radial-gradient(700px 400px at 110% 10%,rgba(47,111,98,.10),transparent 55%);min-height:100dvh}
body::after{content:"";position:fixed;inset:0;pointer-events:none;opacity:.035;z-index:40;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E")}
a{color:inherit;text-decoration:none}
h1,h2,h3{font-family:"Fraunces",Georgia,serif;font-weight:500;letter-spacing:-.01em;margin:0}
h1{font-size:clamp(1.9rem,4vw,2.6rem);line-height:1.05}
h2{font-size:1.25rem}
.wrap{max-width:820px;margin:0 auto;padding:0 16px 96px}

/* nav flutuante */
.nav{position:sticky;top:12px;z-index:30;display:flex;justify-content:center;padding-top:12px}
.nav-pill{display:flex;gap:2px;padding:6px;border-radius:999px;background:rgba(251,248,242,.72);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
  box-shadow:0 1px 0 rgba(255,255,255,.7) inset,0 20px 50px -24px rgba(29,34,38,.35);border:1px solid rgba(29,34,38,.06);max-width:100%;overflow-x:auto;scrollbar-width:none}
.nav-pill::-webkit-scrollbar{display:none}
.nav-pill a{white-space:nowrap;padding:8px 14px;border-radius:999px;font-size:13px;font-weight:600;color:var(--cafe);transition:all .5s var(--ease)}
.nav-pill a:hover{background:rgba(29,34,38,.05);color:var(--espresso)}
.nav-pill a.on{background:var(--espresso);color:var(--creme)}

/* cabecalho da pagina */
.head{padding:44px 0 22px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;padding:5px 12px;border-radius:999px;font-size:10px;letter-spacing:.2em;text-transform:uppercase;font-weight:600;color:var(--cafe);background:rgba(29,34,38,.05);margin-bottom:14px}
.eyebrow i{width:6px;height:6px;border-radius:50%;background:var(--ouro);box-shadow:0 0 0 4px var(--ouro-suave)}
.sub{color:var(--areia);margin-top:6px;font-size:14px}

/* barra de estado */
.status{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:18px 0 28px}
.chip{display:inline-flex;align-items:center;gap:7px;padding:7px 12px;border-radius:999px;font-size:12px;font-weight:600;background:var(--papel);box-shadow:0 1px 0 rgba(255,255,255,.8) inset,0 8px 20px -14px rgba(29,34,38,.4);border:1px solid var(--linha)}
.chip i{width:7px;height:7px;border-radius:50%}
.chip.ok i{background:var(--verde);box-shadow:0 0 0 3px var(--verde-suave)}
.chip.off i{background:var(--vinho);box-shadow:0 0 0 3px var(--vinho-suave)}
.chip.neutro i{background:var(--areia)}
.chip.modo-desligado{background:rgba(29,34,38,.06)}
.chip.modo-observando{background:rgba(63,90,125,.12);color:#2f4a6b}
.chip.modo-sombra{background:var(--ouro-suave);color:#1f5047}
.chip.modo-ao_vivo{background:var(--verde-suave);color:#2c5c42}
.status .spacer{flex:1}
select.modo{appearance:none;border:0;border-radius:999px;padding:8px 34px 8px 14px;font:inherit;font-size:12px;font-weight:600;color:var(--espresso);background:var(--papel) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%235C4A3A' stroke-width='1.5'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") no-repeat right 12px center;border:1px solid var(--linha);cursor:pointer}

/* cartoes em duas camadas */
.shell{background:rgba(29,34,38,.045);border:1px solid var(--linha);border-radius:var(--r);padding:6px;margin:14px 0;transition:transform .7s var(--ease),box-shadow .7s var(--ease)}
.shell:hover{transform:translateY(-1px)}
.core{background:var(--papel);border-radius:var(--r-in);padding:20px 22px;box-shadow:0 1px 1px rgba(255,255,255,.9) inset,0 30px 60px -40px rgba(29,34,38,.45)}
.core.tight{padding:14px 16px}
.card-title{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}
.card-title small{color:var(--areia);font-size:12px}
.meta{color:var(--cafe);font-size:13px;margin-top:4px}

/* bloco de datas */
.datas{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px 14px;margin:12px 0 4px;padding:12px 14px;border-radius:16px;background:var(--creme-2)}
.datas span{display:flex;flex-direction:column;font-weight:600;font-size:14px;color:var(--espresso);font-variant-numeric:tabular-nums}
.datas small{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--areia);font-weight:600;margin-bottom:2px}

/* barra de ml */
.bar{height:6px;border-radius:999px;background:rgba(29,34,38,.08);overflow:hidden;margin:14px 0 6px}
.bar i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--ouro),var(--ouro-2));transition:width 1.2s var(--ease)}
.bar-legend{display:flex;justify-content:space-between;font-size:12px;color:var(--areia)}

/* linhas de pedido / log */
.row{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--linha)}
.row:last-child{border-bottom:0}
.row .grow{flex:1;min-width:0}
.row .t{font-variant-numeric:tabular-nums;color:var(--areia);font-size:12px;width:44px;flex:none}
.tag{display:inline-block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;padding:3px 8px;border-radius:999px;background:rgba(29,34,38,.06);color:var(--cafe);margin-right:6px}
.tag.pedido,.tag.lista,.tag.agenda{background:var(--verde-suave);color:#2c5c42}
.tag.recusado,.tag.duvida,.tag.ambiguo,.tag.divergencia{background:var(--vinho-suave);color:var(--vinho)}
.tag.urgencia,.tag.chamada,.tag.ia,.tag.assumido{background:var(--ouro-suave);color:#1f5047}
.gem{font-size:15px;width:22px;text-align:center}

/* botoes */
.btn{display:inline-flex;align-items:center;gap:10px;padding:10px 16px 10px 18px;border-radius:999px;border:0;font:inherit;font-size:13px;font-weight:600;cursor:pointer;
  background:var(--espresso);color:var(--creme);transition:transform .5s var(--ease),box-shadow .5s var(--ease),background .5s var(--ease);box-shadow:0 14px 30px -18px rgba(29,34,38,.8)}
.btn:hover{transform:translateY(-1px)} .btn:active{transform:scale(.98)}
.btn .ic{width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.14);display:inline-flex;align-items:center;justify-content:center;font-size:12px;transition:transform .5s var(--ease)}
.btn:hover .ic{transform:translate(2px,-1px) scale(1.05)}
.btn.ghost{background:var(--papel);color:var(--espresso);border:1px solid var(--linha);box-shadow:none}
.btn.ghost .ic{background:rgba(29,34,38,.06)}
.btn.ouro{background:linear-gradient(135deg,var(--ouro),#24574d);color:#fff}
.btn.vinho{background:var(--vinho);color:#fff}
.btn.sm{padding:7px 12px;font-size:12px} .btn.sm .ic{width:20px;height:20px}
.btn.x{padding:6px 9px;background:transparent;color:var(--areia);box-shadow:none;border:1px solid transparent}
.btn.x:hover{color:var(--vinho);border-color:var(--linha)}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
form.inline{display:inline}

/* formularios */
label{display:block;font-size:12px;font-weight:600;color:var(--cafe);margin:14px 0 6px;letter-spacing:.02em}
label.check{display:flex;align-items:center;gap:10px;font-weight:500;margin:10px 0}
input,textarea,select{width:100%;padding:11px 14px;border-radius:14px;border:1px solid var(--linha);background:var(--creme-2);font:inherit;font-size:14px;color:var(--espresso);transition:box-shadow .5s var(--ease),background .5s var(--ease)}
input:focus,textarea:focus,select:focus{outline:0;background:#fff;box-shadow:0 0 0 4px var(--ouro-suave)}
input[type=checkbox],input[type=radio]{width:auto;accent-color:var(--ouro)}
input[type=file]{background:transparent;border-style:dashed;padding:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 14px} @media(max-width:560px){.grid2{grid-template-columns:1fr}}
.add{display:flex;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap}
.add input{margin:0} .add .ml{width:78px;flex:none} .add .nome{flex:1;min-width:120px} .add .fone-in{flex:1;min-width:150px}
.sep{height:1px;background:var(--linha);margin:20px 0}
.hint{font-size:12px;color:var(--areia)}
.gal{display:flex;gap:10px;flex-wrap:wrap} .gal label{cursor:pointer;text-align:center;margin:0;font-weight:500}
.gal img{width:84px;height:84px;object-fit:cover;border-radius:16px;display:block;margin-bottom:4px;transition:transform .5s var(--ease)}
.gal input:checked+img{outline:3px solid var(--ouro);outline-offset:2px}
.gal-mais{align-self:center} .gal-busca{flex-basis:100%;margin-top:4px}
.thumb{width:72px;height:72px;object-fit:cover;border-radius:18px;float:right;margin:0 0 8px 12px}

pre{white-space:pre-wrap;font:13px/1.55 ui-monospace,Menlo,Consolas,monospace;background:var(--creme-2);padding:14px 16px;border-radius:16px;margin:10px 0 0;color:var(--cafe)}
details summary{cursor:pointer;color:var(--areia);font-size:12px;margin-top:10px;list-style:none}
details summary::before{content:"▸ ";color:var(--ouro)} details[open] summary::before{content:"▾ "}
.renomear{display:inline} .renomear summary{display:inline;margin:0 0 0 8px;font-size:13px} .renomear summary::before,.renomear[open] summary::before{content:""} .renomear form{margin-top:6px}
.fone{color:var(--areia);font-size:12px;margin-left:6px;text-decoration:none} .fone:hover{color:var(--ouro)}
.empty{padding:26px;text-align:center;color:var(--areia)}
.qr{background:#fff;padding:18px;border-radius:20px;display:inline-block;margin:12px 0}
.qr svg{display:block;max-width:100%;height:auto}

/* entrada suave */
.reveal{animation:up .9s var(--ease) both}
.reveal:nth-child(2){animation-delay:.06s}.reveal:nth-child(3){animation-delay:.12s}.reveal:nth-child(4){animation-delay:.18s}.reveal:nth-child(5){animation-delay:.24s}
@keyframes up{from{opacity:0;transform:translateY(14px);filter:blur(4px)}to{opacity:1;transform:none;filter:none}}
@media(prefers-reduced-motion:reduce){.reveal{animation:none}}
"""

MODOS_ROTULO = {"desligado": "Desligado", "observando": "Observando", "sombra": "Sombra", "ao_vivo": "Ao vivo"}


def pagina(titulo: str, subtitulo: str, corpo: str, *, ativo: str, modo: str, conectado: bool, grupo_aberto: bool | None, grupo_nome: str) -> str:
    nav = "".join(
        f'<a href="{href}" class="{"on" if chave == ativo else ""}">{rotulo}</a>'
        for chave, href, rotulo in [("vivo", "/", "Ao vivo"), ("agenda", "/agenda", "Agenda"), ("nova", "/nova", "Nova abertura"), ("aprender", "/aprender", "Aprender"), ("conexao", "/conexao", "Conexão"), ("config", "/config", "Ajustes")]
    )
    con = '<span class="chip ok"><i></i>Conectado</span>' if conectado else '<span class="chip off"><i></i>Desconectado</span>'
    grupo = {True: '<span class="chip ok"><i></i>Grupo aberto</span>', False: '<span class="chip neutro"><i></i>Grupo fechado</span>', None: '<span class="chip neutro"><i></i>Grupo ?</span>'}[grupo_aberto]
    opcoes = "".join(f'<option value="{m}" {"selected" if m == modo else ""}>{r}</option>' for m, r in MODOS_ROTULO.items())
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(titulo)} · Robô do Grupo</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<nav class="nav"><div class="nav-pill">{nav}</div></nav>
<main class="wrap">
<header class="head reveal"><span class="eyebrow"><i></i>{e(grupo_nome or "sem grupo")}</span><h1>{e(titulo)}</h1><p class="sub">{e(subtitulo)}</p></header>
<div class="status reveal">
  <span class="chip modo-{modo}"><i></i>{MODOS_ROTULO.get(modo, modo)}</span>{con}{grupo}<span class="spacer"></span>
  <form class="inline" method="post" action="/modo"><select class="modo" name="modo" onchange="this.form.submit()">{opcoes}</select></form>
  <form class="inline" method="post" action="/modo"><input type="hidden" name="modo" value="desligado"><button class="btn vinho sm">Pausar tudo <span class="ic">‖</span></button></form>
</div>
{corpo}
</main></body></html>"""


def card(inner: str, *, tight: bool = False) -> str:
    return f'<section class="shell reveal"><div class="core{" tight" if tight else ""}">{inner}</div></section>'


def botao(texto: str, action: str, *, estilo: str = "ghost", icone: str = "→", hidden: dict | None = None, sm: bool = True) -> str:
    campos = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (hidden or {}).items())
    return f'<form class="inline" method="post" action="{action}">{campos}<button class="btn {estilo}{" sm" if sm else ""}">{e(texto)} <span class="ic">{icone}</span></button></form>'
