from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from job_radar.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def nova_sessao() -> Session:
    return sessionmaker(get_engine(), expire_on_commit=False)()


def alembic_config() -> Config:
    """Config do Alembic sem depender do alembic.ini (a imagem só contém o pacote)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    return cfg
