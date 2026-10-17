import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, MetaData, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONVENCAO_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)
    type_annotation_map = {  # noqa: RUF012
        str: Text(),
        datetime: DateTime(timezone=True),
    }


class ComUUID:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class ComCriadoEm:
    criado_em: Mapped[datetime] = mapped_column(server_default=func.now())


class ComAtualizadoEm:
    atualizado_em: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


def check_enum(coluna: str, enum: type[StrEnum]) -> CheckConstraint:
    """Enum como `text` + CHECK (facilita migrações, ver PLANO §6)."""
    valores = ", ".join(f"'{membro.value}'" for membro in enum)
    return CheckConstraint(f"{coluna} IN ({valores})", name=f"{coluna}_valido")
