from datetime import datetime

from robo.interpretar import interpretar
from robo.post import ler_post
from robo.rateio import Autor, adotar_lista_do_admin, aplicar, escolher_rateio, incorporar_lista_colada, novo_rateio, remover_por_msg, renderizar
from robo.texto import SP

POST = """21/09/2026

🌹FRENCH LEATHER | MEMO PARIS

Valor por ml: R$ 24,00
Pedido mínimo: 3 ml

VALORES DOS DECANTS

💎 3 ml: R$ 72,00
💎 5 ml: R$ 120,00 | MAIS SOLICITADO
💎 10 ml: R$ 240,00
💎 15 ml: R$ 360,00
💎 20 ml: R$ 480,00
👑 30 ml: R$ 720,00 | O primeiro a pedir o APC leva o frasco original com frete grátis

Pagamento via PIX ou cartão em até 12x com taxa.

Quantidade do frasco: 75ml"""

AG = datetime(2026, 9, 24, 18, 0, tzinfo=SP)


def rateio():
    return novo_rateio(ler_post(POST), "post1", AG)


def test_le_post_novo():
    p = ler_post(POST)
    assert p.nome == "FRENCH LEATHER | MEMO PARIS"
    assert (p.valor_ml, p.minimo, p.total_ml, p.apc_ml) == (24.0, 3, 75, 30)
    assert p.tamanhos == [3, 5, 10, 15, 20, 30]


def test_interpreta_frases_reais():
    assert interpretar("5ml")["itens"][0]["ml"] == 5
    assert interpretar("quero 3 ml por favor")["itens"][0]["ml"] == 3
    assert interpretar("clara 3") == {"tipo": "pedido", "itens": [{"ml": 3, "qtd": 1, "dica": ""}], "nome": "Clara", "resto": "clara", "sem_unidade": True}
    assert interpretar("2x 5ml")["itens"][0]["qtd"] == 2
    assert interpretar("apc")["tipo"] == "apc"
    assert interpretar("altera pra 10ml")["tipo"] == "alterar"
    assert interpretar("desisto do meu")["tipo"] == "cancelar"
    assert interpretar("Brasil 2 x 1 Noruega")["tipo"] == "nada"
    assert interpretar("falta 17ml pra fechar")["tipo"] == "nada"
    assert interpretar("ainda tem torino 5?")["tipo"] == "nada"
    assert interpretar("eu quero")["tipo"] == "duvida"
    assert interpretar("5 ml do torino")["itens"][0]["dica"] == "torino"


def test_fluxo_completo():
    r = rateio()
    a = Autor("111@s.whatsapp.net", "m1", "Mariane Martins")
    r = aplicar(r, interpretar("3ml"), a, AG).rateio
    assert r.pedidos[0].nome == "Mariane" and r.disponivel == 72

    b = Autor("222@s.whatsapp.net", "m2", "Flavia")
    r = aplicar(r, interpretar("quero 5 ml"), b, AG).rateio
    res = aplicar(r, interpretar("apc"), Autor("333@s.whatsapp.net", "m3", "Carlos"), AG)
    r = res.rateio
    assert r.dono_apc.nome == "Carlos" and r.disponivel == 37

    # segundo APC e recusado
    res = aplicar(r, interpretar("apc"), Autor("444@s.whatsapp.net", "m4", "Ana"), AG)
    assert not res.ok and "já foi" in res.resposta

    # pedido maior que o disponivel
    res = aplicar(r, interpretar("40ml"), Autor("555@s.whatsapp.net", "m5", "Joao"), AG)
    assert not res.ok and "Restam só 37" in res.resposta

    # abaixo do minimo
    assert "mínimo" in aplicar(r, interpretar("2ml"), b, AG).resposta

    # alterar e cancelar
    r = aplicar(r, interpretar("aumenta pra 10ml"), b, AG).rateio
    assert [p.ml for p in r.pedidos if p.autor_id == b.id] == [10]
    r = aplicar(r, interpretar("cancela o meu"), b, AG).rateio
    assert all(p.autor_id != b.id for p in r.pedidos)

    # mensagem apagada remove
    assert remover_por_msg(r, "m1").disponivel == r.disponivel + 3

    # esgotar fecha
    r = aplicar(r, interpretar("20ml"), b, AG).rateio
    r = aplicar(r, interpretar("20ml"), Autor("666@s.whatsapp.net", "m6", "Bia"), AG).rateio
    assert "mínimo" in aplicar(r, interpretar("1ml"), Autor("777@s.whatsapp.net", "m7", "Cris"), AG).resposta  # 1 nao e a sobra
    texto, mencoes = renderizar(r, AG)
    assert "Disponível 2 ml" in texto and "👑 Carlos | APC + 30 ml 👑 @333" in texto and "333@s.whatsapp.net" in mencoes
    r = aplicar(r, interpretar("2ml"), Autor("777@s.whatsapp.net", "m7", "Cris"), AG).rateio  # a sobra exata fecha o frasco
    assert r.disponivel == 0 and r.status == "fechado"


def test_numero_solto_vale_qualquer_valor_a_partir_do_minimo():
    r = rateio()
    a = Autor("1@s.whatsapp.net", "m", "X")
    assert aplicar(r, interpretar("5"), a, AG).ok
    assert aplicar(r, interpretar("7"), a, AG).ok          # valor quebrado
    assert aplicar(r, interpretar("7ml"), a, AG).rateio.pedidos[0].ml == 7
    assert not aplicar(r, interpretar("2"), a, AG).ok      # abaixo do minimo (3): ignorado
    assert not aplicar(r, interpretar("99"), a, AG).ok     # acima do frasco: ignorado


def test_escolhe_rateio_por_reply_e_por_dica():
    r1, r2 = rateio(), rateio()
    r2.nome, r2.post_msg_id = "TORINO 21 | XERJOFF", "post2"
    assert escolher_rateio([r1, r2], citado_id="post2") is r2
    assert escolher_rateio([r1, r2], dica="torino") is r2
    assert escolher_rateio([r1, r2]) is None
    assert escolher_rateio([r1]) is r1


def test_lista_colada_e_lista_do_admin():
    r = aplicar(rateio(), interpretar("3ml"), Autor("1@s.whatsapp.net", "m1", "Fabia"), AG).rateio
    colada = ler_post(POST + "\n\n💎3ml - Fabia\n💎5ml - Hellen")
    res = incorporar_lista_colada(r, colada.linhas_lista, Autor("2@s.whatsapp.net", "m2", "Hellen"), AG)
    assert res.ok and len(res.novas) == 1 and res.rateio.pedidos[-1].autor_id == "2@s.whatsapp.net"

    admin = ler_post(POST + "\n\n🫅🏼Cris APC + 30ml 🫅🏼\n💎5ml - Hellen\n💎10 ml - Rita")
    r = adotar_lista_do_admin(res.rateio, admin.linhas_lista)
    assert [(p.ml, p.nome, p.apc) for p in r.pedidos] == [(30, "Cris", True), (5, "Hellen", False), (10, "Rita", False)]
    assert r.pedidos[1].autor_id == "2@s.whatsapp.net"  # manteve quem era


def test_sobra_abaixo_do_minimo_pode_ser_pedida_exata():
    r = rateio()  # 75 ml, minimo 3
    a = Autor("1@s.whatsapp.net", "m1", "A")
    r = aplicar(r, interpretar("73ml"), a, AG).rateio            # sobram 2
    b = Autor("2@s.whatsapp.net", "m2", "B")
    assert not aplicar(r, interpretar("1ml"), b, AG).ok          # nao e a sobra exata
    assert "mínimo" in aplicar(r, interpretar("1ml"), b, AG).resposta
    res = aplicar(r, interpretar("2ml"), b, AG)                  # a sobra exata: aceita e fecha
    assert res.ok and res.rateio.status == "fechado"
    r2 = aplicar(rateio(), interpretar("73ml"), a, AG).rateio
    assert aplicar(r2, interpretar("2"), b, AG).ok               # numero solto tambem


def test_apc_fora_dos_tamanhos_entra_no_post():
    # caso real 26/09: APC 50 ml com tamanhos 3,5,10,15,20 -> o post saia sem APC e ninguem conseguia pedir
    from robo.estado import Abertura
    from robo.post import ler_post
    ab = Abertura(id="v", nome="VIBRATO | SOSPIRO", valor_ml=20, total_ml=100, minimo=3, tamanhos=[3, 5, 10, 15, 20],
                  apc_ml=50, abre_em="2026-09-26T12:00:00-03:00", fecha_em="2026-09-27T12:00:00-03:00")
    texto = ab.post_texto()
    assert "👑 50 ml: R$ 1.000,00 | O primeiro que pedir leva o APC" in texto
    assert texto.index("20 ml") < texto.index("50 ml")
    assert ler_post(texto).apc_ml == 50
