"""gupy: mais termos e buscas por filtro (DF e remoto)

Revision ID: a7c3e91d4b20
Revises: d2281a1297ff
Create Date: 2026-10-25 10:00:00

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e91d4b20"
down_revision: str | None = "d2281a1297ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores fixos (não importados do coletor): a migration precisa continuar igual
# mesmo que os padrões do código mudem depois.
TERMOS_ANTES = ["ti", "tecnologia", "desenvolvimento", "infraestrutura", "software"]
TERMOS = [*TERMOS_ANTES, "sistemas", "dados", "suporte", "produto"]
FILTROS = [{"state": "Distrito Federal"}, {"workplaceType": "remote"}]
TIPOS = ["vacancy_type_internship"]


def _atualizar(config: dict, max_itens: int) -> None:
    # O seed não sobrescreve fontes existentes; a config da Gupy no banco muda aqui.
    op.get_bind().execute(
        sa.text(
            "UPDATE fonte SET config = CAST(:config AS jsonb), max_itens_execucao = :max"
            " WHERE id = 'gupy'"
        ),
        {"config": json.dumps(config), "max": max_itens},
    )


def upgrade() -> None:
    _atualizar({"termos": TERMOS, "filtros": FILTROS, "tipos": TIPOS}, 400)


def downgrade() -> None:
    _atualizar({"termos": TERMOS_ANTES, "filtros": [], "tipos": TIPOS}, 200)
