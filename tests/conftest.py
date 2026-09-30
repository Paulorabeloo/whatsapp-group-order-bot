"""Os testes antigos usam "admin posta no grupo -> rateio aberto" como atalho pra montar o cenario.
Em producao o padrao e o contrario (post do admin fora do sistema entra pausado); os testes da regra nova usam
o marcador `regra_pausado` pra rodar com o padrao de producao."""

import pytest

from robo.motor import Motor


def pytest_configure(config):
    config.addinivalue_line("markers", "regra_pausado: roda com o padrao de producao (post do admin entra pausado)")


@pytest.fixture(autouse=True)
def _post_do_admin_abre(request, monkeypatch):
    if request.node.get_closest_marker("regra_pausado") is None:
        monkeypatch.setattr(Motor, "_post_do_admin_abre", lambda self: True)
