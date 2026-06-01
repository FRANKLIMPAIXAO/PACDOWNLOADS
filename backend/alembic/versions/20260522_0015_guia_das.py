"""Cria tabela guias_das pra controle de DAS Simples Nacional.

Revision ID: 20260522_0015
Revises: 20260522_0014
Create Date: 2026-05-22 18:00:00

Uma linha por (empresa, periodo_apuracao) com unique constraint pra idempotência.
Sincronizada via Integra Contador CONSDECREC13 (declarações do ano) +
PAGAMENTOS71 (pagamentos para detectar pagas). Guia atualizada (com Selic+mora)
emitida via GERARDAS12 quando atrasa — PDF salvo em `storage/guias/{cnpj}/`.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260522_0015"
down_revision = "20260522_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guias_das",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("periodo_apuracao", sa.String(length=6), nullable=False),
        sa.Column("numero_declaracao", sa.String(length=64), nullable=True),
        sa.Column("recibo_declaracao", sa.String(length=64), nullable=True),
        sa.Column("data_transmissao", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "valor_principal",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column("data_vencimento_original", sa.Date(), nullable=False),
        sa.Column("valor_atualizado", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("data_vencimento_atualizada", sa.Date(), nullable=True),
        sa.Column("numero_das", sa.String(length=32), nullable=True),
        sa.Column("codigo_barras", sa.String(length=64), nullable=True),
        sa.Column("pdf_path", sa.String(length=512), nullable=True),
        sa.Column("emitida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "situacao",
            sa.String(length=20),
            nullable=False,
            server_default="em_aberto",
        ),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("valor_pago", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "sincronizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id", "periodo_apuracao", name="uq_guia_das_empresa_pa",
        ),
    )
    op.create_index("ix_guias_das_id", "guias_das", ["id"])
    op.create_index("ix_guias_das_empresa_id", "guias_das", ["empresa_id"])
    op.create_index("ix_guias_das_periodo_apuracao", "guias_das", ["periodo_apuracao"])
    op.create_index("ix_guias_das_situacao", "guias_das", ["situacao"])


def downgrade() -> None:
    op.drop_index("ix_guias_das_situacao", table_name="guias_das")
    op.drop_index("ix_guias_das_periodo_apuracao", table_name="guias_das")
    op.drop_index("ix_guias_das_empresa_id", table_name="guias_das")
    op.drop_index("ix_guias_das_id", table_name="guias_das")
    op.drop_table("guias_das")
