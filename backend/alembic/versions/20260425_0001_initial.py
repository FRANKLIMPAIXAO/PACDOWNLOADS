"""initial schema

Revision ID: 20260425_0001
Revises:
Create Date: 2026-04-25 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260425_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "empresas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column("razao_social", sa.String(length=255), nullable=False),
        sa.Column("nome_fantasia", sa.String(length=255), nullable=True),
        sa.Column("municipio", sa.String(length=120), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("regime_tributario", sa.String(length=80), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("data_cadastro", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_empresas_id", "empresas", ["id"])
    op.create_index("ix_empresas_cnpj", "empresas", ["cnpj"], unique=True)

    # Deixa o create_table criar o ENUM sozinho (default do SQLAlchemy).
    # Antes a migration tinha um .create() explícito + uso na Column, mas
    # isso gerava DUAS instruções "CREATE TYPE tipodocumento" no Postgres
    # (a segunda falhava). Em SQLite nem percebia (ENUM vira VARCHAR).
    tipo_documento = sa.Enum("NFE", "CTE", "NFSE", name="tipodocumento")
    op.create_table(
        "documentos_fiscais",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("tipo_documento", tipo_documento, nullable=False),
        sa.Column("chave_acesso", sa.String(length=64), nullable=False),
        sa.Column("numero", sa.String(length=30), nullable=True),
        sa.Column("serie", sa.String(length=20), nullable=True),
        sa.Column("data_emissao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cnpj_emitente", sa.String(length=14), nullable=True),
        sa.Column("nome_emitente", sa.String(length=255), nullable=True),
        sa.Column("cnpj_destinatario", sa.String(length=14), nullable=True),
        sa.Column("nome_destinatario", sa.String(length=255), nullable=True),
        sa.Column("valor_total", sa.Numeric(15, 2), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("xml_path", sa.String(length=1024), nullable=False),
        sa.Column("json_original", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("empresa_id", "tipo_documento", "chave_acesso", name="uq_documento_empresa_tipo_chave"),
    )
    op.create_index("ix_documentos_fiscais_id", "documentos_fiscais", ["id"])

    op.create_table(
        "consultas_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=True),
        sa.Column("tipo_documento", sa.String(length=20), nullable=True),
        sa.Column("periodo_inicio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("periodo_fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("detalhes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consultas_logs_id", "consultas_logs", ["id"])

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usuarios_id", "usuarios", ["id"])
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_usuarios_email", table_name="usuarios")
    op.drop_index("ix_usuarios_id", table_name="usuarios")
    op.drop_table("usuarios")
    op.drop_index("ix_consultas_logs_id", table_name="consultas_logs")
    op.drop_table("consultas_logs")
    op.drop_index("ix_documentos_fiscais_id", table_name="documentos_fiscais")
    op.drop_table("documentos_fiscais")
    op.drop_index("ix_empresas_cnpj", table_name="empresas")
    op.drop_index("ix_empresas_id", table_name="empresas")
    op.drop_table("empresas")
    sa.Enum(name="tipodocumento").drop(op.get_bind(), checkfirst=True)
