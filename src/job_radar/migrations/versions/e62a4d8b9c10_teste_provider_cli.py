"""Resultado e solicitação de teste do provider no worker."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e62a4d8b9c10"
down_revision = "d5a2c8e14f93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_ia", sa.Column("teste_conexao", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_ia", "teste_conexao")
