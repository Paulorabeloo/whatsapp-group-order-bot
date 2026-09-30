"""O aviso "abertura de hoje" sai na hora marcada, uma vez so, e nao sai depois que o grupo abriu."""

import asyncio
from datetime import timedelta

from robo.estado import Abertura, Armazem, Config
from robo.motor import Motor
from robo.texto import agora
from tests.test_motor import GRUPO, WaFake


def test_aviso_sai_uma_vez(tmp_path):
    arm = Armazem(tmp_path / "estado.json")
    with arm as e:
        e.modo, e.config.grupo_jid = "ao_vivo", GRUPO
    ag = agora()
    ab = Abertura(id="a1", nome="CHICELLE | UNIQUE'E LUXURY", valor_ml=24, total_ml=50, minimo=3, tamanhos=[3, 5],
                  apc_ml=None, abre_em=(ag + timedelta(hours=3)).isoformat(), fecha_em=(ag + timedelta(hours=8)).isoformat(),
                  descricao="Doce, cremosa e feminina.", aviso_em=(ag - timedelta(minutes=1)).isoformat())
    ab.aviso_texto = Config().textos["aviso"].replace("{nome}", ab.nome).replace("{hora}", ab.hora_curta).replace("{descricao}", ab.descricao)
    with arm as e:
        e.aberturas.append(ab)
    wa = WaFake()
    m = Motor(arm, wa)

    async def roda():
        await m._tique()
        await m._tique()
        avisos = [t for _, t, _ in wa.enviadas if "ABERTURA DE HOJE" in t]
        assert len(avisos) == 1
        assert "O CHICELLE | UNIQUE'E LUXURY será aberto" in avisos[0] and "Doce, cremosa" in avisos[0]
        assert f"às {ab.hora_curta}" in avisos[0]
        assert arm.estado.abertura("a1").aviso_feito

    asyncio.run(roda())
