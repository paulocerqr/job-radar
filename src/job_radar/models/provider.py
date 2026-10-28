import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_radar.models.base import Base, ComCriadoEm, ComUUID, check_enum
from job_radar.models.enums import TipoProvider


class ProviderIA(ComUUID, ComCriadoEm, Base):
    __tablename__ = "provider_ia"
    __table_args__ = (
        UniqueConstraint("usuario_id", "prioridade", name="uq_provider_ia_usuario_prioridade"),
        check_enum("tipo", TipoProvider),
        CheckConstraint(
            "(tipo = 'cli' AND comando IS NOT NULL)"
            " OR (tipo = 'openai_compatible' AND base_url IS NOT NULL)",
            name="config_por_tipo",
        ),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    nome: Mapped[str]
    tipo: Mapped[str]
    base_url: Mapped[str | None]
    modelo: Mapped[str]
    comando: Mapped[str | None]
    api_key_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)  # Fernet
    api_key_sufixo: Mapped[str | None]  # últimos 4 caracteres, para exibição
    prioridade: Mapped[int] = mapped_column(default=1, server_default="1")  # menor = primeiro
    tamanho_lote: Mapped[int] = mapped_column(default=5, server_default="5")
    rpm: Mapped[int | None]
    rpd: Mapped[int | None]
    tpm: Mapped[int | None]
    timeout_s: Mapped[int] = mapped_column(default=120, server_default="120")
    ativo: Mapped[bool] = mapped_column(default=True, server_default="true")
    ultimo_erro: Mapped[str | None]
    ultimo_erro_em: Mapped[datetime | None]
    teste_conexao: Mapped[dict | None] = mapped_column(JSONB)


class UsoProvider(Base):
    __tablename__ = "uso_provider"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_ia.id", ondelete="CASCADE"), primary_key=True
    )
    dia: Mapped[date] = mapped_column(primary_key=True)
    requisicoes: Mapped[int] = mapped_column(default=0, server_default="0")
    tokens_entrada: Mapped[int] = mapped_column(default=0, server_default="0")
    tokens_saida: Mapped[int] = mapped_column(default=0, server_default="0")
    erros: Mapped[int] = mapped_column(default=0, server_default="0")
