"""Cria tabela guias_fgts.

Revision ID: 20260526_0018
Revises: 20260526_0017
Create Date: 2026-05-26 11:00:00

guias_fgts: cada emissão da Guia Rápida FGTS Digital via Infosimples
(modo Procurador) cria/atualiza um registro. Único por (empresa, periodo).
"""
from alembic import op
import sqlalchemy as sa


revision = "20260526_0018"
down_revision = "20260526_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guias_fgts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("periodo", sa.String(length=6), nullable=False),
        sa.Column("competencia_formatada", sa.String(length=7), nullable=True),
        sa.Column("data_vencimento", sa.Date(), nullable=True),
        sa.Column(
            "valor_total", sa.Numeric(precision=14, scale=2), nullable=False,
            server_default="0.00",
        ),
        sa.Column("valor_mensal", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("valor_rescisorio", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("valor_compensatorio", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("valor_encargos", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("quantidade_trabalhadores", sa.Integer(), nullable=True),
        sa.Column("pdf_url_infosimples", sa.String(length=1024), nullable=True),
        sa.Column("pdf_path", sa.String(length=512), nullable=True),
        sa.Column(
            "situacao", sa.String(length=20), nullable=False, server_default="emitida",
        ),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column(
            "emitida_em", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id", "periodo", name="uq_fgts_empresa_periodo",
        ),
    )
    op.create_index("ix_fgts_id", "guias_fgts", ["id"])
    op.create_index("ix_fgts_empresa_id", "guias_fgts", ["empresa_id"])
    op.create_index("ix_fgts_periodo", "guias_fgts", ["periodo"])
    op.create_index("ix_fgts_vencimento", "guias_fgts", ["data_vencimento"])
    op.create_index("ix_fgts_situacao", "guias_fgts", ["situacao"])


def downgrade() -> None:
    for ix in (
        "ix_fgts_situacao", "ix_fgts_vencimento", "ix_fgts_periodo",
        "ix_fgts_empresa_id", "ix_fgts_id",
    ):
        op.drop_index(ix, table_name="guias_fgts")
    op.drop_table("guias_fgts")
