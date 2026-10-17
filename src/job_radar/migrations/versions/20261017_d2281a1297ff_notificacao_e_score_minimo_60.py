"""notificacao e score minimo 60

Revision ID: d2281a1297ff
Revises: 357c6ecafa75
Create Date: 2026-10-17 17:48:04.138321

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2281a1297ff"
down_revision: str | None = "357c6ecafa75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vaga_usuario", sa.Column("notificado_em", sa.DateTime(timezone=True), nullable=True)
    )

    # calibração de 17/10: 60-79 é "boa aderência" no próprio prompt
    op.alter_column("perfil", "score_minimo", server_default="60")
    op.execute("UPDATE perfil SET score_minimo = 60 WHERE score_minimo = 70")


def downgrade() -> None:
    op.alter_column("perfil", "score_minimo", server_default="70")
    op.drop_column("vaga_usuario", "notificado_em")
