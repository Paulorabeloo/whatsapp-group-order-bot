"""Correcao manual no painel: adicionar/remover/reabrir em qualquer perfume, e o mais recente no topo."""

import io
from datetime import timedelta

from robo.post import ler_post
from robo.rateio import novo_rateio
from robo.texto import agora
from tests.test_painel import PNG, cli  # noqa: F401  (fixture)

POST = "✨ {n}\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 10 ml: R$ 100,00 | APC\nQUANTIDADE DO FRASCO: 20 ml"


def rateio(cli, nome, minutos_atras=0):
    r = novo_rateio(ler_post(POST.format(n=nome)), None, agora() - timedelta(minutes=minutos_atras))
    with cli.arm as e:
        e.rateios.append(r)
    return r.id


def test_mais_recente_no_topo(cli):
    rateio(cli, "VELHO | A", 120)
    rateio(cli, "NOVO | B", 0)
    rateio(cli, "MEIO | C", 60)
    html = cli.get("/").text
    assert html.index("NOVO | B") < html.index("MEIO | C") < html.index("VELHO | A")


def test_adicionar_em_frasco_fechado_com_sobra(cli):
    rid = rateio(cli, "X | Y")
    cli.post(f"/rateio/{rid}/add", data={"ml": "5", "nome": "Ana"})
    cli.post(f"/rateio/{rid}/fechar")
    assert cli.arm.estado.rateio(rid).status == "fechado"
    html = cli.get("/").text
    assert f"/rateio/{rid}/add" in html and f"/rateio/{rid}/reabrir" in html      # formulario aparece no fechado
    cli.post(f"/rateio/{rid}/add", data={"ml": "5", "nome": "Bia"})
    r = cli.arm.estado.rateio(rid)
    assert [p.nome for p in r.pedidos] == ["Ana", "Bia"] and r.status == "fechado"


def test_adicionar_que_nao_cabe_e_recusado_com_aviso(cli):
    rid = rateio(cli, "X | Y")
    cli.post(f"/rateio/{rid}/add", data={"ml": "15", "nome": "Ana"})
    r = cli.post(f"/rateio/{rid}/add", data={"ml": "10", "nome": "Bia"})
    assert "aviso=" in r.headers["location"]
    assert [p.nome for p in cli.arm.estado.rateio(rid).pedidos] == ["Ana"]
    assert "Não cabe: sobram 5 ml" in cli.get(r.headers["location"]).text


def test_apc_pelo_painel_e_unico(cli):
    rid = rateio(cli, "X | Y")
    cli.post(f"/rateio/{rid}/add", data={"nome": "Ana", "apc": "on"})
    r = cli.post(f"/rateio/{rid}/add", data={"nome": "Bia", "apc": "on"})
    assert "j%C3%A1%20%C3%A9%20de%20Ana" in r.headers["location"]
    assert cli.arm.estado.rateio(rid).dono_apc.nome == "Ana"


def test_validacoes(cli):
    rid = rateio(cli, "X | Y")
    for dados, trecho in [({"ml": "5", "nome": ""}, "nome"), ({"ml": "abc", "nome": "Ana"}, "inv"), ({"ml": "0", "nome": "Ana"}, "Informe")]:
        r = cli.post(f"/rateio/{rid}/add", data=dados)
        assert "aviso=" in r.headers["location"]
    assert cli.arm.estado.rateio(rid).pedidos == []


def test_reabrir(cli):
    rid = rateio(cli, "X | Y")
    cli.post(f"/rateio/{rid}/add", data={"ml": "5", "nome": "Ana"})
    cli.post(f"/rateio/{rid}/fechar")
    cli.post(f"/rateio/{rid}/reabrir")
    r = cli.arm.estado.rateio(rid)
    assert r.status == "aberto" and r.fechado_em is None
    # cheio nao reabre: avisa
    cli.post(f"/rateio/{rid}/add", data={"ml": "15", "nome": "Bia"})
    assert cli.arm.estado.rateio(rid).status == "fechado"
    resp = cli.post(f"/rateio/{rid}/reabrir")
    assert "aviso=" in resp.headers["location"] and cli.arm.estado.rateio(rid).status == "fechado"


def test_remover_reabre_frasco_cheio(cli):
    rid = rateio(cli, "X | Y")
    cli.post(f"/rateio/{rid}/add", data={"ml": "20", "nome": "Ana"})
    assert cli.arm.estado.rateio(rid).status == "fechado"
    cli.post(f"/rateio/{rid}/remover", data={"i": "0"})
    r = cli.arm.estado.rateio(rid)
    assert r.status == "aberto" and r.fechado_em is None and r.pedidos == []


def test_pausar_retomar_e_excluir_rateio(cli):
    from robo.estado import Abertura
    from robo.post import ler_post
    from robo.rateio import novo_rateio
    r = novo_rateio(ler_post("✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 30 ml"), None)
    with cli.arm as e:
        e.rateios.append(r)
        e.aberturas.append(Abertura(id="ab", nome="X | Y", valor_ml=10, total_ml=30, minimo=3, tamanhos=[5], apc_ml=None,
                                    abre_em="2026-09-26T14:00:00-03:00", fecha_em="2026-09-27T14:00:00-03:00", rateio_id=r.id))
    assert "Pausar" in cli.get("/").text and "Excluir" in cli.get("/").text
    cli.post(f"/rateio/{r.id}/pausar")
    assert cli.arm.estado.rateio(r.id).status == "pausado" and cli.arm.estado.rateios_abertos() == []
    assert "Retomar" in cli.get("/").text
    cli.post(f"/rateio/{r.id}/retomar")
    assert cli.arm.estado.rateio(r.id).status == "aberto"
    cli.post(f"/rateio/{r.id}/excluir")
    assert cli.arm.estado.rateio(r.id) is None and cli.arm.estado.abertura("ab").status == "cancelada"


def test_telefones_normalizados():
    from robo.painel import fone
    assert fone("5511 912345678") == "5511912345678"
    assert fone("11912345678") == "5511912345678"
    assert fone("(11) 91234-5678") == "5511912345678"
    assert fone(" ") == ""


def test_renomear_pedido_mantem_o_numero(cli):
    # caso real 28/09: "Quero 3ml para conhecer" virou "Conhecer"; apagar e adicionar perdia a marcacao da Lara
    from robo.post import ler_post
    from robo.rateio import Pedido, novo_rateio
    r = novo_rateio(ler_post("✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 30 ml"), None)
    r.pedidos.append(Pedido("5511987654321@s.whatsapp.net", "m1", "2026-09-28T14:16:16-03:00", "Conhecer", 3))
    with cli.arm as e:
        e.rateios.append(r)
    assert "Salvar" in cli.get("/").text
    cli.post(f"/rateio/{r.id}/renomear", data={"i": "0", "nome": "Lara"})
    p = cli.arm.estado.rateio(r.id).pedidos[0]
    assert p.nome == "Lara" and p.autor_id == "5511987654321@s.whatsapp.net" and p.ml == 3


def test_numero_de_quem_pediu_aparece():
    from robo.painel import fone_bonito, fone_link
    assert fone_bonito("5511987654321@s.whatsapp.net") == "+55 11 98765-4321"
    assert fone_bonito("556433334444@s.whatsapp.net") == "+55 64 3333-4444"
    assert fone_bonito("108611233685506@lid") is None and fone_bonito(None) is None
    assert 'href="https://wa.me/5511987654321"' in fone_link("5511987654321@s.whatsapp.net")


def test_galeria_mostra_4_e_ver_mais(cli):
    from robo.estado import Abertura
    import os
    os.makedirs("data/fotos", exist_ok=True)
    with cli.arm as e:
        for i in range(7):
            caminho = f"data/fotos/g{i}.png"
            open(caminho, "wb").write(b"x")
            e.aberturas.append(Abertura(id=f"g{i}", nome=f"PERFUME {i} | MARCA", valor_ml=1, total_ml=10, minimo=3, tamanhos=[3],
                                        apc_ml=None, abre_em=f"2026-09-2{i}T12:00:00-03:00", fecha_em="2026-10-01T12:00:00-03:00",
                                        foto=caminho))
    html = cli.get("/nova").text
    assert html.count('class=mais hidden') == 3 and "Ver mais (3)" in html and "Buscar pelo nome" in html


def test_editar_quantidade_do_apc(cli):
    # caso real 29/09: "O meu vai ser APC de 35+5=40 ml" -> o admin ajusta a quantidade no painel
    from robo.post import ler_post
    from robo.rateio import Pedido, novo_rateio
    r = novo_rateio(ler_post("✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 35 ml: R$ 350,00 | APC\nQUANTIDADE DO FRASCO: 100 ml"), None)
    r.pedidos.append(Pedido("5511996363338@s.whatsapp.net", "m1", "2026-09-29T11:08:02-03:00", "Flavia", 35, apc=True))
    with cli.arm as e:
        e.rateios.append(r)
    cli.post(f"/rateio/{r.id}/editar", data={"i": "0", "nome": "Flavia", "ml": "40"})
    p = cli.arm.estado.rateio(r.id).pedidos[0]
    assert (p.ml, p.apc, p.autor_id) == (40, True, "5511996363338@s.whatsapp.net")
    assert "passou" not in cli.get("/").text
    r2 = cli.post(f"/rateio/{r.id}/editar", data={"i": "0", "nome": "Flavia", "ml": "200"})   # nao cabe
    assert r2.status_code == 303 and "Não cabe" in r2.headers["location"] or "N%C3%A3o%20cabe" in r2.headers["location"]
    assert cli.arm.estado.rateio(r.id).pedidos[0].ml == 40
    cli.post(f"/rateio/{r.id}/editar", data={"i": "0", "nome": "Flavia", "ml": "100"})   # enche o frasco -> fecha
    assert cli.arm.estado.rateio(r.id).status == "fechado"


def test_tirar_pedido_pede_confirmacao(cli):
    # 29/09: APC apagado sem querer duas vezes no mesmo dia
    from robo.post import ler_post
    from robo.rateio import Pedido, novo_rateio
    r = novo_rateio(ler_post("✨ X | Y\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\nQUANTIDADE DO FRASCO: 100 ml"), None)
    r.pedidos.append(Pedido("5511912345678@s.whatsapp.net", "m1", "2026-09-29T11:00:00-03:00", "Sofia", 40, apc=True))
    with cli.arm as e:
        e.rateios.append(r)
    html = cli.get("/").text
    assert 'data-msg="Tirar 40 ml de Sofia (APC) da lista?"' in html and "confirm(this.dataset.msg)" in html


def _rateio_com(cli, *pedidos):
    from robo.post import ler_post
    from robo.rateio import novo_rateio
    r = novo_rateio(ler_post("✨ BAL | BYREDO\nValor por ml: R$ 10,00\nPedido mínimo: 3 ml\n💎 5 ml: R$ 50,00\n👑 30 ml: R$ 300,00 | APC\nQUANTIDADE DO FRASCO: 100 ml"), None)
    r.pedidos += list(pedidos)
    with cli.arm as e:
        e.rateios.append(r)
    return r


def test_adicionar_a_mao_usa_o_numero_de_quem_ja_pediu(cli):
    # caso real 29/09: Diana adicionada pelo painel saiu sem @marcacao
    from robo.rateio import Pedido
    antigo = _rateio_com(cli, Pedido("5511999000001@s.whatsapp.net", "m1", "2026-09-25T18:30:17-03:00", "Diana", 5))
    antigo.status = "fechado"
    r = _rateio_com(cli)
    cli.post(f"/rateio/{r.id}/add", data={"ml": "10", "nome": "Diana"})
    cli.post(f"/rateio/{r.id}/add", data={"ml": "10", "nome": "Gustavo"})        # nunca pediu pelo grupo
    ps = cli.arm.estado.rateio(r.id).pedidos
    assert [(p.nome, p.autor_id) for p in ps] == [("Diana", "5511999000001@s.whatsapp.net"), ("Gustavo", None)]
    cli.post(f"/rateio/{r.id}/editar", data={"i": "1", "nome": "Gustavo", "ml": "10", "fone": "(11) 91234-5678"})
    assert cli.arm.estado.rateio(r.id).pedidos[1].autor_id == "5511912345678@s.whatsapp.net"


def test_aprender_era_pedido_entra_na_lista_com_numero(cli):
    r = _rateio_com(cli)
    with cli.arm as e:
        item = e.para_aprender("duvida", "Quero 10ml.\nMinha irmã amou, dei o meu decant pra ela", autor="Diana Souza",
                               autor_id="5511999000001@s.whatsapp.net", msg_id="m9", motivo="mensagem longa", abertos=[r.nome])
    cli.post(f"/aprender/{item['id']}", data={"rotulo": "pedido", "ml": "10", "perfume": r.nome})
    p = cli.arm.estado.rateio(r.id).pedidos[0]
    assert (p.nome, p.ml, p.autor_id) == ("Diana", 10, "5511999000001@s.whatsapp.net")


def test_adicionar_com_telefone_marca_a_pessoa(cli):
    # 29/09: "Clara @clara" adicionada a mao saiu sem marcar; agora tem campo de WhatsApp
    r = _rateio_com(cli)
    assert 'name="fone"' in cli.get("/").text
    cli.post(f"/rateio/{r.id}/add", data={"ml": "3", "nome": "Clara @clara", "fone": "(19) 98765-4321"})
    p = cli.arm.estado.rateio(r.id).pedidos[0]
    assert (p.nome, p.autor_id) == ("Clara", "5519987654321@s.whatsapp.net")


def test_ao_vivo_so_mostra_o_que_foi_cadastrado_no_sistema(cli):
    r = _rateio_com(cli)
    copia = _rateio_com(cli)
    with cli.arm as e:
        e.rateio(copia.id).nome, e.rateio(copia.id).origem = "TOBACCO | COPIA DO ADMIN", "admin"
    html = cli.get("/").text
    assert r.nome in html and "TOBACCO | COPIA DO ADMIN" not in html


def _abertura_em(cli, minutos):
    from datetime import timedelta
    from robo.estado import Abertura
    from robo.texto import agora
    ag = agora()
    with cli.arm as e:
        e.modo = "ao_vivo"
        e.aberturas.append(Abertura(id="z", nome="CEDAR CHIC", valor_ml=20, total_ml=100, minimo=3, tamanhos=[3],
                                    apc_ml=None, abre_em=(ag + timedelta(minutes=minutos)).isoformat(),
                                    fecha_em=(ag + timedelta(days=1)).isoformat()))


def test_desligar_perto_de_abertura_pede_confirmacao(cli):
    # 29/09: robo desligado as 13:57 com o Cedar abrindo as 14:00
    _abertura_em(cli, 30)
    html = cli.post("/modo", data={"modo": "desligado"}).text
    assert "Desligar mesmo assim" in html and cli.arm.estado.modo == "ao_vivo"
    cli.post("/modo", data={"modo": "desligado", "confirmar": "1"})
    assert cli.arm.estado.modo == "desligado"


def test_desligar_sem_abertura_perto_nao_pergunta(cli):
    _abertura_em(cli, 5 * 60)
    r = cli.post("/modo", data={"modo": "desligado"})
    assert r.status_code == 303 and cli.arm.estado.modo == "desligado"


def test_saude(cli):
    import time
    assert cli.get("/saude", auth=None).status_code == 200
    _abertura_em(cli, 30)
    with cli.arm as e:
        e.modo = "desligado"
    r = cli.get("/saude", auth=None)
    assert r.status_code == 503 and "desligado" in r.text
    with cli.arm as e:
        e.modo = "ao_vivo"
    cli.wa.conectado, cli.wa.caiu_em = False, time.time() - 600
    r = cli.get("/saude", auth=None)
    assert r.status_code == 503 and "sem WhatsApp" in r.text
    cli.wa.conectado = True


def test_abriu_so_aparece_depois_que_o_grupo_abre(cli):
    # 30/09: o card mostrava "ABRIU 10:00" (hora do post, 1h antes) com o grupo ainda fechado
    from datetime import timedelta
    from robo.estado import Abertura
    from robo.texto import agora
    r = _rateio_com(cli)
    ag = agora()
    with cli.arm as e:
        e.aberturas.append(Abertura(id="q", nome=r.nome, valor_ml=10, total_ml=100, minimo=3, tamanhos=[5], apc_ml=30,
                                    abre_em=(ag + timedelta(hours=1)).isoformat(), fecha_em=(ag + timedelta(days=1)).isoformat(),
                                    rateio_id=r.id, status="agendada"))
    html = cli.get("/").text
    assert "<small>abriu</small>—" in html
    with cli.arm as e:
        e.abertura("q").abriu_em = ag.replace(hour=11, minute=0).isoformat()
    assert "<small>abriu</small>11:00" in cli.get("/").text


def test_reacao_e_coracao_e_configuravel(cli):
    import asyncio
    from tests.test_motor import msg
    r = _rateio_com(cli)
    asyncio.run(cli.motor.receber(msg("5ml", citado=r.post_msg_id, mid="p1")))
    assert cli.wa.emojis[-1] == "👍"
    cli.post("/config", data={"grupo_nome": cli.arm.estado.config.grupo_nome, "reagir": "on", "emoji_reacao": "❤️", "contagem": "30,5"})
    assert cli.arm.estado.config.emoji_reacao == "❤️"


def test_ajustes_salvam_as_regras(cli):
    html = cli.get("/config").text if cli.get("/config").status_code == 200 else cli.get("/ajustes").text
    assert "Como pedir" in html
    cli.post("/config", data={"grupo_nome": cli.arm.estado.config.grupo_nome, "contagem": "30,5", "regras_texto": "Oi\r\nregra", "regras_antes": "15", "regras_cada": "6", "regras_horario": "10:00-20:00"})
    c = cli.arm.estado.config
    assert (c.regras_texto, c.regras_antes_min, c.regras_a_cada_h, c.regras_horario) == ("Oi\nregra", 15, 6, "10:00-20:00")
