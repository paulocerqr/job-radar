"""schema inicial

Revision ID: 357c6ecafa75
Revises:
Create Date: 2026-10-17 15:40:08.055769

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "357c6ecafa75"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # índice de similaridade em vaga.titulo (dedupe secundário, PLANO §13)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "fonte",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("intervalo_min", sa.Integer(), server_default="60", nullable=False),
        sa.Column("max_itens_execucao", sa.Integer(), server_default="20", nullable=False),
        sa.Column("confiabilidade", sa.Integer(), server_default="50", nullable=False),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("ultima_execucao_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "confiabilidade BETWEEN 0 AND 100", name=op.f("ck_fonte_confiabilidade_faixa")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fonte")),
    )
    op.create_table(
        "usuario",
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("papel", sa.Text(), server_default="usuario", nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("limite_fila", sa.Integer(), server_default="30", nullable=False),
        sa.Column("limite_recomendadas", sa.Integer(), server_default="50", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("papel IN ('admin', 'usuario')", name=op.f("ck_usuario_papel_valido")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario")),
        sa.UniqueConstraint("email", name=op.f("uq_usuario_email")),
    )
    op.create_table(
        "vaga",
        sa.Column("hash_dedupe", sa.Text(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("empresa", sa.Text(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("cidade", sa.Text(), nullable=True),
        sa.Column("uf", sa.CHAR(length=2), nullable=True),
        sa.Column("modalidade", sa.Text(), server_default="desconhecida", nullable=False),
        sa.Column("nivel", sa.Text(), server_default="desconhecido", nullable=False),
        sa.Column("url_canonica", sa.Text(), nullable=False),
        sa.Column("publicada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ativa", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("verificada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "modalidade IN ('remoto', 'presencial', 'hibrido', 'desconhecida')",
            name=op.f("ck_vaga_modalidade_valido"),
        ),
        sa.CheckConstraint(
            "nivel IN ('estagio', 'trainee', 'junior', 'pleno', 'senior', 'desconhecido')",
            name=op.f("ck_vaga_nivel_valido"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vaga")),
        sa.UniqueConstraint("hash_dedupe", name=op.f("uq_vaga_hash_dedupe")),
    )
    op.create_index(
        "ix_vaga_publicada_em", "vaga", [sa.literal_column("publicada_em DESC")], unique=False
    )
    op.create_index(
        "ix_vaga_titulo_trgm",
        "vaga",
        ["titulo"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"titulo": "gin_trgm_ops"},
    )
    op.create_table(
        "canal_notificacao",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("destino", sa.Text(), nullable=True),
        sa.Column("token_vinculo", sa.Text(), nullable=True),
        sa.Column("verificado", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "tipo IN ('telegram', 'email')", name=op.f("ck_canal_notificacao_tipo_valido")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_canal_notificacao_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_canal_notificacao")),
        sa.UniqueConstraint("token_vinculo", name=op.f("uq_canal_notificacao_token_vinculo")),
        sa.UniqueConstraint("usuario_id", "tipo", name="uq_canal_notificacao_usuario_tipo"),
    )
    op.create_table(
        "execucao_coleta",
        sa.Column("fonte_id", sa.Text(), nullable=False),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("itens_coletados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("itens_novos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("itens_duplicados", sa.Integer(), server_default="0", nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('rodando', 'ok', 'erro', 'parcial')",
            name=op.f("ck_execucao_coleta_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["fonte_id"], ["fonte.id"], name=op.f("fk_execucao_coleta_fonte_id_fonte")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execucao_coleta")),
    )
    op.create_index(
        "ix_execucao_coleta_fonte_iniciada",
        "execucao_coleta",
        ["fonte_id", sa.literal_column("iniciada_em DESC")],
        unique=False,
    )
    op.create_table(
        "perfil",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("curriculo_md", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "palavras_chave", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "palavras_excluidas", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "niveis", postgresql.ARRAY(sa.Text()), server_default="{estagio}", nullable=False
        ),
        sa.Column("aceita_remoto", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "localidades",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("score_minimo", sa.Integer(), server_default="70", nullable=False),
        sa.Column("ttl_pool_dias", sa.Integer(), server_default="7", nullable=False),
        sa.Column("ttl_recomendada_dias", sa.Integer(), server_default="14", nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "score_minimo BETWEEN 0 AND 100", name=op.f("ck_perfil_score_minimo_faixa")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_perfil_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("usuario_id", name=op.f("pk_perfil")),
    )
    op.create_table(
        "provider_ia",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("modelo", sa.Text(), nullable=False),
        sa.Column("comando", sa.Text(), nullable=True),
        sa.Column("api_key_cifrada", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_sufixo", sa.Text(), nullable=True),
        sa.Column("prioridade", sa.Integer(), server_default="1", nullable=False),
        sa.Column("tamanho_lote", sa.Integer(), server_default="5", nullable=False),
        sa.Column("rpm", sa.Integer(), nullable=True),
        sa.Column("rpd", sa.Integer(), nullable=True),
        sa.Column("tpm", sa.Integer(), nullable=True),
        sa.Column("timeout_s", sa.Integer(), server_default="120", nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("ultimo_erro_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "(tipo = 'cli' AND comando IS NOT NULL) OR (tipo = 'openai_compatible' AND base_url IS NOT NULL)",
            name=op.f("ck_provider_ia_config_por_tipo"),
        ),
        sa.CheckConstraint(
            "tipo IN ('cli', 'openai_compatible')", name=op.f("ck_provider_ia_tipo_valido")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_provider_ia_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_ia")),
        sa.UniqueConstraint("usuario_id", "prioridade", name="uq_provider_ia_usuario_prioridade"),
    )
    op.create_table(
        "vaga_fonte",
        sa.Column("vaga_id", sa.Uuid(), nullable=False),
        sa.Column("fonte_id", sa.Text(), nullable=False),
        sa.Column("id_externo", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("dados_brutos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "visto_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["fonte_id"], ["fonte.id"], name=op.f("fk_vaga_fonte_fonte_id_fonte")
        ),
        sa.ForeignKeyConstraint(
            ["vaga_id"], ["vaga.id"], name=op.f("fk_vaga_fonte_vaga_id_vaga"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("fonte_id", "id_externo", name=op.f("pk_vaga_fonte")),
    )
    op.create_index(op.f("ix_vaga_fonte_vaga_id"), "vaga_fonte", ["vaga_id"], unique=False)
    op.create_table(
        "vaga_usuario",
        sa.Column("vaga_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("score_prefiltro", sa.Integer(), server_default="0", nullable=False),
        sa.Column("score_ia", sa.Integer(), nullable=True),
        sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proxima_tentativa_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_usuario", sa.Text(), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pool', 'fila', 'recomendada', 'confirmada', 'descartada', 'ignorada', 'expirada', 'erro')",
            name=op.f("ck_vaga_usuario_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_vaga_usuario_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vaga_id"], ["vaga.id"], name=op.f("fk_vaga_usuario_vaga_id_vaga"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vaga_usuario")),
        sa.UniqueConstraint("vaga_id", "usuario_id", name="uq_vaga_usuario_vaga_usuario"),
    )
    op.create_index(
        "ix_vaga_usuario_expira",
        "vaga_usuario",
        ["expira_em"],
        unique=False,
        postgresql_where=sa.text("status IN ('pool', 'recomendada')"),
    )
    op.create_index(
        "ix_vaga_usuario_fila",
        "vaga_usuario",
        ["usuario_id", sa.literal_column("proxima_tentativa_em ASC NULLS FIRST")],
        unique=False,
        postgresql_where=sa.text("status = 'fila'"),
    )
    op.create_index(
        "ix_vaga_usuario_pool",
        "vaga_usuario",
        ["usuario_id", sa.literal_column("score_prefiltro DESC")],
        unique=False,
        postgresql_where=sa.text("status = 'pool'"),
    )
    op.create_index(
        "ix_vaga_usuario_status", "vaga_usuario", ["usuario_id", "status"], unique=False
    )
    op.create_table(
        "auditoria",
        sa.Column("vaga_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=True),
        sa.Column("modelo", sa.Text(), nullable=False),
        sa.Column("versao_prompt", sa.Text(), nullable=False),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("resultado", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_entrada", sa.Integer(), nullable=True),
        sa.Column("tokens_saida", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["provider_ia.id"],
            name=op.f("fk_auditoria_provider_id_provider_ia"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vaga_usuario_id"],
            ["vaga_usuario.id"],
            name=op.f("fk_auditoria_vaga_usuario_id_vaga_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria")),
    )
    op.create_index(
        "ix_auditoria_vaga_usuario_criado",
        "auditoria",
        ["vaga_usuario_id", sa.literal_column("criado_em DESC")],
        unique=False,
    )
    op.create_table(
        "historico_status",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("vaga_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("de", sa.Text(), nullable=True),
        sa.Column("para", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "origem IN ('sistema', 'ia', 'usuario')", name=op.f("ck_historico_status_origem_valido")
        ),
        sa.ForeignKeyConstraint(
            ["vaga_usuario_id"],
            ["vaga_usuario.id"],
            name=op.f("fk_historico_status_vaga_usuario_id_vaga_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_historico_status")),
    )
    op.create_index(
        op.f("ix_historico_status_vaga_usuario_id"),
        "historico_status",
        ["vaga_usuario_id"],
        unique=False,
    )
    op.create_table(
        "uso_provider",
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("requisicoes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_entrada", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_saida", sa.Integer(), server_default="0", nullable=False),
        sa.Column("erros", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["provider_ia.id"],
            name=op.f("fk_uso_provider_provider_id_provider_ia"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("provider_id", "dia", name=op.f("pk_uso_provider")),
    )


def downgrade() -> None:
    op.drop_table("uso_provider")
    op.drop_index(op.f("ix_historico_status_vaga_usuario_id"), table_name="historico_status")
    op.drop_table("historico_status")
    op.drop_index("ix_auditoria_vaga_usuario_criado", table_name="auditoria")
    op.drop_table("auditoria")
    op.drop_index("ix_vaga_usuario_status", table_name="vaga_usuario")
    op.drop_index(
        "ix_vaga_usuario_pool",
        table_name="vaga_usuario",
        postgresql_where=sa.text("status = 'pool'"),
    )
    op.drop_index(
        "ix_vaga_usuario_fila",
        table_name="vaga_usuario",
        postgresql_where=sa.text("status = 'fila'"),
    )
    op.drop_index(
        "ix_vaga_usuario_expira",
        table_name="vaga_usuario",
        postgresql_where=sa.text("status IN ('pool', 'recomendada')"),
    )
    op.drop_table("vaga_usuario")
    op.drop_index(op.f("ix_vaga_fonte_vaga_id"), table_name="vaga_fonte")
    op.drop_table("vaga_fonte")
    op.drop_table("provider_ia")
    op.drop_table("perfil")
    op.drop_index("ix_execucao_coleta_fonte_iniciada", table_name="execucao_coleta")
    op.drop_table("execucao_coleta")
    op.drop_table("canal_notificacao")
    op.drop_index(
        "ix_vaga_titulo_trgm",
        table_name="vaga",
        postgresql_using="gin",
        postgresql_ops={"titulo": "gin_trgm_ops"},
    )
    op.drop_index("ix_vaga_publicada_em", table_name="vaga")
    op.drop_table("vaga")
    op.drop_table("usuario")
    op.drop_table("fonte")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
