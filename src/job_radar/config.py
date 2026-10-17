from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração 100% por variáveis de ambiente (RNF09)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    log_format: Literal["json", "text"] = "json"
    log_level: str = "INFO"
    tz: str = "America/Sao_Paulo"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # false no Kubernetes: a coleta vem de CronJobs (`job-radar coletar <fonte>`)
    coleta_no_worker: bool = True
    coleta_inicio: time = time(8, 0)
    coleta_fim: time = time(20, 0)

    worker_heartbeat_path: Path = Path("/tmp/job-radar-worker.heartbeat")
    worker_heartbeat_max_idade_s: int = 120

    # usados pelo `job-radar seed`
    admin_email: str | None = None
    admin_nome: str = "Admin"
    admin_senha: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
