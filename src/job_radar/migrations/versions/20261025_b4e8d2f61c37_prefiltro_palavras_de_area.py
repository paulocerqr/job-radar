"""pré-filtro: palavras-chave de área no perfil

Revision ID: b4e8d2f61c37
Revises: a7c3e91d4b20
Create Date: 2026-10-25 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8d2f61c37"
down_revision: str | None = "a7c3e91d4b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sem palavra-chave no título a nota máxima do pré-filtro é 43, abaixo dos 50 da fila:
# "Estágio em Machine Learning" e "Estagiário(a) de Suporte" nunca chegavam à IA.
# Simulado com as 270 vagas do banco em 25/10: fila de 6 para 15.
NOVAS = [
    "machine learning", "inteligencia artificial",
    "dados", "ciencia de dados", "engenharia de dados",
    "desenvolvedor", "programador", "desenvolvimento de sistemas",
    "computacao", "engenharia de software", "ciencia da computacao",
    "suporte", "suporte tecnico", "help desk", "service desk",
    "seguranca da informacao", "ciberseguranca",
    "automacao", "monitoracao", "monitoramento",
    "sql", "javascript", "typescript", "react", "api",
]  # fmt: skip


def upgrade() -> None:
    # Só acrescenta o que falta, na ordem acima; não mexe no que o usuário já tem.
    op.get_bind().execute(
        sa.text(
            "UPDATE perfil SET palavras_chave = palavras_chave || ARRAY("
            " SELECT n FROM unnest(CAST(:novas AS text[])) WITH ORDINALITY AS t(n, i)"
            " WHERE n <> ALL(palavras_chave) ORDER BY i)"
        ),
        {"novas": NOVAS},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE perfil SET palavras_chave = ARRAY("
            " SELECT p FROM unnest(palavras_chave) WITH ORDINALITY AS t(p, i)"
            " WHERE p <> ALL(CAST(:novas AS text[])) ORDER BY i)"
        ),
        {"novas": NOVAS},
    )
