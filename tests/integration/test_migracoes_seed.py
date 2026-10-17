"""Requer Postgres: defina TEST_DATABASE_URL (o CI define; localmente use o compose)."""

import os

import pytest
from alembic import command
from sqlalchemy import inspect, select

from job_radar.config import get_settings
from job_radar.db import alembic_config, get_engine, nova_sessao
from job_radar.models import Base, Usuario
from job_radar.seed import FONTES_PADRAO, executar_seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL não definido"
)


@pytest.fixture
def banco_migrado():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    get_engine().dispose()
    command.downgrade(cfg, "base")


def test_migracao_cria_todas_as_tabelas(banco_migrado):
    tabelas = set(inspect(get_engine()).get_table_names())
    assert set(Base.metadata.tables) <= tabelas


def test_seed_idempotente(banco_migrado, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@teste.local")
    monkeypatch.setenv("ADMIN_SENHA", "senha-de-teste")
    get_settings.cache_clear()

    with nova_sessao() as sessao:
        primeira = executar_seed(sessao, get_settings())
    with nova_sessao() as sessao:
        segunda = executar_seed(sessao, get_settings())
        admin = sessao.scalar(select(Usuario).where(Usuario.email == "admin@teste.local"))
        assert admin is not None
        assert admin.perfil is not None
        assert admin.perfil.localidades == [{"cidade": "Brasília", "uf": "DF"}]

    assert primeira.fontes_criadas == len(FONTES_PADRAO)
    assert primeira.admin_criado
    assert segunda.fontes_criadas == 0
    assert not segunda.admin_criado
