import uuid
from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_radar.models.base import Base, ComAtualizadoEm, ComCriadoEm, ComUUID, check_enum
from job_radar.models.enums import Modalidade, Nivel


class Vaga(ComUUID, ComCriadoEm, ComAtualizadoEm, Base):
    """Vaga global, coletada e deduplicada uma única vez (D04)."""

    __tablename__ = "vaga"
    __table_args__ = (
        check_enum("modalidade", Modalidade),
        check_enum("nivel", Nivel),
    )

    hash_dedupe: Mapped[str] = mapped_column(unique=True)
    titulo: Mapped[str]
    empresa: Mapped[str | None]
    descricao: Mapped[str | None]
    cidade: Mapped[str | None]
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    modalidade: Mapped[str] = mapped_column(
        default=Modalidade.DESCONHECIDA, server_default=Modalidade.DESCONHECIDA
    )
    nivel: Mapped[str] = mapped_column(
        default=Nivel.DESCONHECIDO, server_default=Nivel.DESCONHECIDO
    )
    url_canonica: Mapped[str]
    publicada_em: Mapped[datetime | None]
    ativa: Mapped[bool] = mapped_column(default=True, server_default="true")
    verificada_em: Mapped[datetime | None]


class VagaFonte(Base):
    """Onde cada vaga foi vista; a mesma vaga pode vir de várias fontes (RN06)."""

    __tablename__ = "vaga_fonte"

    vaga_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vaga.id", ondelete="CASCADE"), index=True
    )
    fonte_id: Mapped[str] = mapped_column(ForeignKey("fonte.id"), primary_key=True)
    id_externo: Mapped[str] = mapped_column(primary_key=True)
    url: Mapped[str]
    dados_brutos: Mapped[dict | None] = mapped_column(JSONB)
    visto_em: Mapped[datetime] = mapped_column(server_default=func.now())


Index("ix_vaga_publicada_em", Vaga.publicada_em.desc())
Index(
    "ix_vaga_titulo_trgm",
    Vaga.titulo,
    postgresql_using="gin",
    postgresql_ops={"titulo": "gin_trgm_ops"},
)
