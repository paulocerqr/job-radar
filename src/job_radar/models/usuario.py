import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_radar.models.base import (
    Base,
    ComAtualizadoEm,
    ComCriadoEm,
    ComUUID,
    check_enum,
)
from job_radar.models.enums import Nivel, Papel, TipoCanal


class Usuario(ComUUID, ComCriadoEm, ComAtualizadoEm, Base):
    __tablename__ = "usuario"
    __table_args__ = (check_enum("papel", Papel),)

    email: Mapped[str] = mapped_column(unique=True)
    senha_hash: Mapped[str]
    nome: Mapped[str]
    papel: Mapped[str] = mapped_column(default=Papel.USUARIO, server_default=Papel.USUARIO)
    ativo: Mapped[bool] = mapped_column(default=True, server_default="true")
    limite_fila: Mapped[int] = mapped_column(default=30, server_default="30")
    limite_recomendadas: Mapped[int] = mapped_column(default=50, server_default="50")

    perfil: Mapped["Perfil | None"] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class Perfil(ComAtualizadoEm, Base):
    __tablename__ = "perfil"
    __table_args__ = (CheckConstraint("score_minimo BETWEEN 0 AND 100", name="score_minimo_faixa"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    curriculo_md: Mapped[str] = mapped_column(default="", server_default="")
    # regras em texto livre que vão para o prompt (ex.: "aceito remoto com idas esporádicas")
    instrucoes_ia: Mapped[str] = mapped_column(default="", server_default="")
    palavras_chave: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    palavras_excluidas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    niveis: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: [Nivel.ESTAGIO.value], server_default="{estagio}"
    )
    aceita_remoto: Mapped[bool] = mapped_column(default=True, server_default="true")
    # [{"cidade": "Brasília", "uf": "DF"}]
    localidades: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    score_minimo: Mapped[int] = mapped_column(default=60, server_default="60")
    ttl_pool_dias: Mapped[int] = mapped_column(default=7, server_default="7")
    ttl_recomendada_dias: Mapped[int] = mapped_column(default=14, server_default="14")

    usuario: Mapped[Usuario] = relationship(back_populates="perfil")


class CanalNotificacao(ComUUID, ComCriadoEm, Base):
    __tablename__ = "canal_notificacao"
    __table_args__ = (
        UniqueConstraint("usuario_id", "tipo", name="uq_canal_notificacao_usuario_tipo"),
        check_enum("tipo", TipoCanal),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    tipo: Mapped[str]
    destino: Mapped[str | None]  # chat_id ou e-mail
    token_vinculo: Mapped[str | None] = mapped_column(unique=True)  # /start <token>
    verificado: Mapped[bool] = mapped_column(default=False, server_default="false")
    ativo: Mapped[bool] = mapped_column(default=True, server_default="true")


class Convite(ComUUID, ComCriadoEm, Base):
    """Convite de cadastro (Fase 3): link de uso único. Só o hash do token fica no banco."""

    __tablename__ = "convite"

    token_hash: Mapped[str] = mapped_column(unique=True)  # sha256 hex do token do link
    email: Mapped[str]  # o cadastro só aceita este e-mail
    criado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL")
    )
    expira_em: Mapped[datetime]
    usado_em: Mapped[datetime | None]
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL")
    )  # quem se cadastrou com ele
    revogado_em: Mapped[datetime | None]
