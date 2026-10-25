"""convite de cadastro

Revision ID: d5a2c8e14f93
Revises: c91f0a7e2d58
Create Date: 2026-10-26 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5a2c8e14f93"
down_revision: str | None = "c91f0a7e2d58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "convite",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("criado_por", sa.Uuid(), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["criado_por"], ["usuario.id"], name="fk_convite_criado_por_usuario", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_convite_usuario_id_usuario", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_convite"),
        sa.UniqueConstraint("token_hash", name="uq_convite_token_hash"),
    )  # fmt: skip


def downgrade() -> None:
    op.drop_table("convite")
