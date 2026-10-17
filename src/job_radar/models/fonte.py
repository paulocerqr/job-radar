from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_radar.models.base import Base, ComUUID, check_enum
from job_radar.models.enums import StatusExecucao


class Fonte(Base):
    __tablename__ = "fonte"
    __table_args__ = (
        CheckConstraint("confiabilidade BETWEEN 0 AND 100", name="confiabilidade_faixa"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # 'gupy', 'github_backendbr', ...
    nome: Mapped[str]
    ativa: Mapped[bool] = mapped_column(default=True, server_default="true")
    intervalo_min: Mapped[int] = mapped_column(default=60, server_default="60")
    max_itens_execucao: Mapped[int] = mapped_column(default=20, server_default="20")
    confiabilidade: Mapped[int] = mapped_column(default=50, server_default="50")
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    ultima_execucao_em: Mapped[datetime | None]


class ExecucaoColeta(ComUUID, Base):
    __tablename__ = "execucao_coleta"
    __table_args__ = (check_enum("status", StatusExecucao),)

    fonte_id: Mapped[str] = mapped_column(ForeignKey("fonte.id"))
    iniciada_em: Mapped[datetime] = mapped_column(server_default=func.now())
    finalizada_em: Mapped[datetime | None]
    status: Mapped[str]
    itens_coletados: Mapped[int] = mapped_column(default=0, server_default="0")
    itens_novos: Mapped[int] = mapped_column(default=0, server_default="0")
    itens_duplicados: Mapped[int] = mapped_column(default=0, server_default="0")
    erro: Mapped[str | None]


Index(
    "ix_execucao_coleta_fonte_iniciada",
    ExecucaoColeta.fonte_id,
    ExecucaoColeta.iniciada_em.desc(),
)
