"""sitfis: tabela situacoes_fiscais

Revision ID: 20260502_0006
Revises: 20260502_0005
Create Date: 2026-05-02 17:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0006"
down_revision = "20260502_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "situacoes_fiscais",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "empresa_id",
            sa.Integer(),
            sa.ForeignKey("empresas.id"),
            nullable=False,
        ),
        sa.Column("protocolo", sa.String(length=80), nullable=True),
        sa.Column("pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="GERADO"),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "gerada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_situacoes_fiscais_empresa_id",
        "situacoes_fiscais",
        ["empresa_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_situacoes_fiscais_empresa_id", table_name="situacoes_fiscais")
    op.drop_table("situacoes_fiscais")
