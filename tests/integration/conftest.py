import os

import pytest
from alembic import command

from job_radar.config import get_settings
from job_radar.db import alembic_config, get_engine, nova_sessao
from job_radar.seed import executar_seed


@pytest.fixture(autouse=True)
def _exige_banco():
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL não definido")


@pytest.fixture
def banco_migrado():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    get_engine().dispose()
    command.downgrade(cfg, "base")


@pytest.fixture
def banco_com_seed(banco_migrado, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@teste.local")
    monkeypatch.setenv("ADMIN_SENHA", "senha-de-teste")
    get_settings.cache_clear()
    with nova_sessao() as sessao:
        executar_seed(sessao, get_settings())
