import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_radar.models.base import Base, ComCriadoEm, ComUUID, check_enum
from job_radar.models.enums import OrigemTransicao, StatusVaga


class VagaUsuario(ComUUID, ComCriadoEm, Base):
    """Estado de uma vaga para um usuário: pool → fila → recomendada → confirmada (§4)."""

    __tablename__ = "vaga_usuario"
    __table_args__ = (
        UniqueConstraint("vaga_id", "usuario_id", name="uq_vaga_usuario_vaga_usuario"),
        check_enum("status", StatusVaga),
    )

    vaga_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vaga.id", ondelete="CASCADE"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    status: Mapped[str]
    score_prefiltro: Mapped[int] = mapped_column(default=0, server_default="0")
    score_ia: Mapped[int | None]
    tentativas: Mapped[int] = mapped_column(default=0, server_default="0")
    proxima_tentativa_em: Mapped[datetime | None]
    motivo_usuario: Mapped[str | None]
    expira_em: Mapped[datetime | None]
    status_em: Mapped[datetime] = mapped_column(server_default=func.now())


class Auditoria(ComUUID, ComCriadoEm, Base):
    __tablename__ = "auditoria"

    vaga_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vaga_usuario.id", ondelete="CASCADE")
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_ia.id", ondelete="SET NULL")
    )
    modelo: Mapped[str]
    versao_prompt: Mapped[str]
    sucesso: Mapped[bool]
    resultado: Mapped[dict | None] = mapped_column(JSONB)
    erro: Mapped[str | None]
    duracao_ms: Mapped[int | None]
    tokens_entrada: Mapped[int | None]
    tokens_saida: Mapped[int | None]


class HistoricoStatus(ComCriadoEm, Base):
    __tablename__ = "historico_status"
    __table_args__ = (check_enum("origem", OrigemTransicao),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    vaga_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vaga_usuario.id", ondelete="CASCADE"), index=True
    )
    de: Mapped[str | None]
    para: Mapped[str]
    origem: Mapped[str]
    detalhe: Mapped[str | None]


# Índices das consultas quentes da fila (PLANO §6.4)
Index("ix_vaga_usuario_status", VagaUsuario.usuario_id, VagaUsuario.status)
Index(
    "ix_vaga_usuario_pool",
    VagaUsuario.usuario_id,
    VagaUsuario.score_prefiltro.desc(),
    postgresql_where=text("status = 'pool'"),
)
Index(
    "ix_vaga_usuario_fila",
    VagaUsuario.usuario_id,
    VagaUsuario.proxima_tentativa_em.asc().nulls_first(),
    postgresql_where=text("status = 'fila'"),
)
Index(
    "ix_vaga_usuario_expira",
    VagaUsuario.expira_em,
    postgresql_where=text("status IN ('pool', 'recomendada')"),
)
Index("ix_auditoria_vaga_usuario_criado", Auditoria.vaga_usuario_id, Auditoria.criado_em.desc())
