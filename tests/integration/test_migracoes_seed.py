"""Requer Postgres: defina TEST_DATABASE_URL (o CI define; localmente use o compose)."""

from alembic import command
from sqlalchemy import inspect, select, text

from job_radar.config import get_settings
from job_radar.db import alembic_config, get_engine, nova_sessao
from job_radar.models import Base, Perfil, Usuario
from job_radar.seed import FONTES_PADRAO, executar_seed


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


def test_migracao_acrescenta_palavras_de_area_sem_duplicar(banco_com_seed):
    cfg = alembic_config()
    command.downgrade(cfg, "a7c3e91d4b20")
    # SQL direto: nesta revisão o banco ainda não tem as colunas mais novas do modelo
    with nova_sessao() as sessao:
        sessao.execute(text("UPDATE perfil SET palavras_chave = '{devops,dados}'"))  # não duplica
        sessao.commit()

    command.upgrade(cfg, "head")
    with nova_sessao() as sessao:
        palavras = sessao.scalars(select(Perfil)).one().palavras_chave
    assert palavras[:3] == ["devops", "dados", "machine learning"]
    assert palavras.count("dados") == 1
    assert "suporte" in palavras
