"""apuracoes: tabela de apuracoes mensais (PGDAS-D)

Revision ID: 20260502_0008
Revises: 20260502_0007
Create Date: 2026-05-02 19:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0008"
down_revision = "20260502_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apuracoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("ano_mes", sa.String(length=6), nullable=False),
        sa.Column(
            "regime",
            sa.Enum("SIMPLES_NACIONAL", "LUCRO_PRESUMIDO", "LUCRO_REAL", "MEI", name="regimeapuracao"),
            nullable=False,
            server_default="SIMPLES_NACIONAL",
        ),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "TRANSMITIDA", "DAS_GERADO", "PAGO", "ERRO", name="statusapuracao"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("receita_bruta", sa.Numeric(15, 2), nullable=True),
        sa.Column("valor_devido", sa.Numeric(15, 2), nullable=True),
        sa.Column("numero_declaracao", sa.String(length=80), nullable=True),
        sa.Column("recibo", sa.String(length=80), nullable=True),
        sa.Column("transmitida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("das_numero_documento", sa.String(length=80), nullable=True),
        sa.Column("das_codigo_barras", sa.String(length=120), nullable=True),
        sa.Column("das_data_vencimento", sa.String(length=10), nullable=True),
        sa.Column("das_pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("raw_declaracao", sa.JSON(), nullable=True),
        sa.Column("raw_das", sa.JSON(), nullable=True),
        sa.Column("receitas_segregadas", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("empresa_id", "ano_mes", name="uq_apuracoes_empresa_ano_mes"),
    )
    op.create_index("ix_apuracoes_empresa_id", "apuracoes", ["empresa_id"])
    op.create_index("ix_apuracoes_ano_mes", "apuracoes", ["ano_mes"])


def downgrade() -> None:
    op.drop_index("ix_apuracoes_ano_mes", table_name="apuracoes")
    op.drop_index("ix_apuracoes_empresa_id", table_name="apuracoes")
    op.drop_table("apuracoes")
