"""Painel inteiro pelo cliente de teste: login, cada tela, cada botao, seguranca de arquivos."""

import io
import os

import pytest
from fastapi.testclient import TestClient

from robo.estado import Armazem
from robo.motor import Motor
from robo.painel import criar_app
from tests.test_motor import GRUPO, WaFake

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("PAINEL_SENHA", "s3nha")
    monkeypatch.chdir(tmp_path)          # data/fotos fica no tmp
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.config.grupo_jid, e.config.grupo_nome, e.modo = GRUPO, "Grupo teste", "ao_vivo"
        e.config.segundos_ate_postar_lista = 0
    wa = WaFake()
    motor = Motor(arm, wa)
    app = criar_app(arm, motor)
    c = TestClient(app, follow_redirects=False)
    c.auth = ("x", "s3nha")
    c.arm, c.wa, c.motor = arm, wa, motor
    return c


def test_sem_senha_401(cli):
    cli.auth = None
    assert cli.get("/").status_code == 401
    cli.auth = ("x", "errada")
    assert cli.get("/agenda").status_code == 401


@pytest.mark.parametrize("rota", ["/", "/agenda", "/nova", "/conexao", "/config"])
def test_todas_as_telas_abrem(cli, rota):
    r = cli.get(rota)
    assert r.status_code == 200 and "Robô do Grupo" in r.text and "Fraunces" in r.text


def test_modo_e_pausar(cli):
    assert cli.post("/modo", data={"modo": "sombra"}).status_code == 303
    assert cli.arm.estado.modo == "sombra"
    cli.post("/modo", data={"modo": "invalido"})
    assert cli.arm.estado.modo == "sombra"
    cli.post("/modo", data={"modo": "desligado"})
    assert cli.arm.estado.modo == "desligado"


def test_nova_abertura_exige_foto(cli):
    r = cli.post("/nova", data={"nome": "X | Y", "valor_ml": "10", "total_ml": "50", "dia": "2026-10-01", "abre": "18:00"})
    assert r.status_code == 400 and "Falta a foto" in r.text
    assert cli.arm.estado.aberturas == []


def test_nova_abertura_completa_e_agenda(cli):
    r = cli.post("/nova", data={"nome": "🤎 UNIQUE’E | CHICELLE", "valor_ml": "40", "total_ml": "50", "minimo": "3", "tamanhos": "3,5,10", "apc_ml": "20",
                                "dia": "2026-10-01", "abre": "18:00", "aviso_hora": "11:00", "descricao": "Doce e cremosa.",
                                "aviso_modelo": "💗 HOJE ÀS {hora}! {nome}: {descricao}", "texto_extra": "Frete grátis."},
                 files={"foto": ("chicelle.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 303
    a = cli.arm.estado.aberturas[0]
    assert a.foto and os.path.exists(a.foto) and a.apc_ml == 20 and a.abre_em.startswith("2026-10-01T18:00")
    assert a.aviso_texto == "💗 HOJE ÀS 18h! 🤎 UNIQUE’E | CHICELLE: Doce e cremosa."
    assert "QUANTIDADE DO FRASCO: 50 ml" in a.post_texto() and a.post_texto().startswith("01/10/2026")
    assert "✨ 🤎" not in a.post_texto()          # nome com emoji nao ganha outro emoji
    pagina = cli.get("/agenda").text
    assert "CHICELLE" in pagina and "aviso às 11:00" in pagina and "quinta, 01/10/2026" in pagina
    # foto servida e reaproveitavel
    nome = os.path.basename(a.foto)
    assert cli.get(f"/fotos/{nome}").status_code == 200
    assert nome in cli.get("/nova").text
    r2 = cli.post("/nova", data={"nome": "OUTRO | Z", "valor_ml": "10", "total_ml": "20", "dia": "2026-10-02", "abre": "19:00", "foto_anterior": nome})
    assert r2.status_code == 303 and cli.arm.estado.aberturas[1].foto == a.foto


def test_fotos_nao_sai_da_pasta(cli):
    assert cli.get("/fotos/../estado.json").status_code in (404, 400)
    assert cli.get("/fotos/..%2F..%2F.env").status_code in (404, 400)
    assert cli.get("/fotos/inexistente.png").status_code == 404


def test_abrir_agora_cancelar_e_grupo(cli):
    cli.post("/nova", data={"nome": "A | B", "valor_ml": "10", "total_ml": "20", "dia": "2026-10-01", "abre": "18:00"},
             files={"foto": ("a.png", io.BytesIO(PNG), "image/png")})
    aid = cli.arm.estado.aberturas[0].id
    assert cli.post(f"/abertura/{aid}/abrir").status_code == 303
    assert cli.arm.estado.aberturas[0].status == "aberta" and cli.arm.estado.rateios[0].total_ml == 20
    assert cli.wa.anuncio[-1] == "abriu" and any("GRUPO ABERTO" in t for _, t, _ in cli.wa.enviadas)
    cli.post("/nova", data={"nome": "C | D", "valor_ml": "10", "total_ml": "20", "dia": "2026-10-03", "abre": "18:00"},
             files={"foto": ("a.png", io.BytesIO(PNG), "image/png")})
    aid2 = cli.arm.estado.aberturas[1].id
    cli.post(f"/abertura/{aid2}/cancelar")
    assert cli.arm.estado.aberturas[1].status == "cancelada"
    cli.post("/grupo/fechar")
    assert cli.arm.estado.grupo_aberto is False and cli.wa.anuncio[-1] == "fechou"
    cli.post("/grupo/abrir")
    assert cli.arm.estado.grupo_aberto is True


def test_rateio_add_remover_postar_fechar(cli):
    cli.post("/nova", data={"nome": "A | B", "valor_ml": "10", "total_ml": "20", "apc_ml": "10", "dia": "2026-10-01", "abre": "18:00"},
             files={"foto": ("a.png", io.BytesIO(PNG), "image/png")})
    cli.post(f"/abertura/{cli.arm.estado.aberturas[0].id}/abrir")
    rid = cli.arm.estado.rateios[0].id
    cli.post(f"/rateio/{rid}/add", data={"ml": "5", "nome": "Bruno"})
    cli.post(f"/rateio/{rid}/add", data={"ml": "", "nome": "Ana", "apc": "on"})
    cli.post(f"/rateio/{rid}/add", data={"ml": "5", "nome": ""})           # sem nome: ignorado
    r = cli.arm.estado.rateios[0]
    assert [(p.ml, p.nome, p.apc) for p in r.pedidos] == [(5, "Bruno", False), (10, "Ana", True)] and r.disponivel == 5
    assert cli.post(f"/rateio/{rid}/postar").status_code == 303
    assert any("💎 5ml - Bruno" in t for _, t, _ in cli.wa.enviadas)
    cli.post(f"/rateio/{rid}/remover", data={"i": "0"})
    cli.post(f"/rateio/{rid}/remover", data={"i": "99"})                  # indice invalido: ignorado
    assert [p.nome for p in cli.arm.estado.rateios[0].pedidos] == ["Ana"]
    cli.post(f"/rateio/{rid}/fechar")
    assert cli.arm.estado.rateios[0].status == "fechado" and "FRASCO FECHADO" in cli.wa.enviadas[-1][1]
    assert cli.post("/rateio/naoexiste/fechar").status_code == 303
    assert "A | B" in cli.get("/").text


def test_config_salva_e_le(cli):
    r = cli.post("/config", data={"grupo_nome": "Grupo teste", "admins": "5519111, 5519222", "avisar_admin": "5519111", "segundos": "30",
                                  "ultimos": "8", "contagem": "30,5", "fechar_antes": "60", "urg_min": "90", "urg_max": "4", "sem_reply": "perguntar",
                                  "reagir": "on", "tx_aberto": "GRUPO ABERTO 🥂🥂"})
    assert r.status_code == 303
    c = cli.arm.estado.config
    assert c.admins == ["5519111", "5519222"] and c.segundos_ate_postar_lista == 30 and c.contagem_min == [30, 5]
    assert c.fechar_antes_min == 60 and c.sem_reply == "perguntar" and c.reagir_pedido and not c.responder_erro_no_grupo
    assert c.textos["aberto"] == "GRUPO ABERTO 🥂🥂" and c.grupo_jid == GRUPO
    assert "5519111" in cli.get("/config").text


def test_trocar_nome_do_grupo_esquece_o_id(cli):
    cli.wa.conectado = False
    cli.post("/config", data={"grupo_nome": "Outro grupo", "contagem": "30,5"})
    assert cli.arm.estado.config.grupo_jid == "" and cli.arm.estado.config.grupo_nome == "Outro grupo"
    # conectado, ele ja procura o grupo novo na hora
    cli.wa.conectado = True
    r = cli.post("/config", data={"grupo_nome": "Grupo teste", "contagem": "30,5"})
    assert r.headers["location"] == "/conexao" and cli.arm.estado.config.grupo_jid == GRUPO


def test_escolher_grupo_na_conexao(cli):
    r = cli.post("/conexao/escolher", data={"jid": "555@g.us", "nome": "Grupo Real"})
    assert r.status_code == 303 and cli.arm.estado.config.grupo_jid == "555@g.us"
    assert "Grupo Real" in cli.get("/conexao").text


def test_conexao_sem_qr_e_com_qr(cli):
    cli.wa.conectado = False
    assert "Gerando um QR" in cli.get("/conexao").text
    cli.wa.qr_svg = "<svg id='qr'></svg>"
    assert "id='qr'" in cli.get("/conexao").text


def test_abrir_agora_usa_a_data_de_hoje_no_post(cli):
    from robo.texto import agora
    cli.post("/nova", data={"nome": "A | B", "valor_ml": "10", "total_ml": "20", "dia": "2026-12-31", "abre": "18:00"},
             files={"foto": ("a.png", io.BytesIO(PNG), "image/png")})
    cli.post(f"/abertura/{cli.arm.estado.aberturas[0].id}/abrir")
    post = next(t for _, t, _ in cli.wa.enviadas if "QUANTIDADE DO FRASCO" in t)
    assert post.startswith(agora().strftime("%d/%m/%Y")) and "31/12/2026" not in post
