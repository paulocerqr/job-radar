from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
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

    # opcional: aumenta o rate limit da API do GitHub (60 → 5000 req/h)
    github_token: SecretStr | None = None

    # cifra as chaves de API dos providers no banco (gere com `job-radar chave-fernet`)
    fernet_key: SecretStr | None = None

    # sessão da Web UI: sem SESSAO_SECRET, a chave é derivada da FERNET_KEY
    sessao_secret: SecretStr | None = None
    # true quando a UI é servida por HTTPS (cookie só vai em HTTPS); false no compose local
    sessao_cookie_seguro: bool = False

    # build do frontend (Next, `pnpm build` gera frontend/out); na imagem: /app/frontend
    frontend_dir: Path | None = None

    # bot do Telegram (crie com o @BotFather); sem ele, as notificações ficam desligadas
    telegram_bot_token: SecretStr | None = None
    resumo_diario: time = time(20, 30)

    @field_validator(
        "admin_email",
        "admin_senha",
        "github_token",
        "fernet_key",
        "telegram_bot_token",
        "sessao_secret",
        mode="before",
    )
    @classmethod
    def _vazio_e_ausente(cls, valor: object) -> object:
        """`CHAVE=` no .env (linha presente, sem valor) significa "não configurado"."""
        return None if isinstance(valor, str) and not valor.strip() else valor


@lru_cache
def get_settings() -> Settings:
    return Settings()
