"""perfil: instruções para a IA

Revision ID: c91f0a7e2d58
Revises: b4e8d2f61c37
Create Date: 2026-10-25 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c91f0a7e2d58"
down_revision: str | None = "b4e8d2f61c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "perfil", sa.Column("instrucoes_ia", sa.Text(), server_default="", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("perfil", "instrucoes_ia")
