"""distribuicao DF-e: ultimo_nsu_distribuicao em empresas, origem em documentos_fiscais

Revision ID: 20260426_0002
Revises: 20260425_0001
Create Date: 2026-04-26 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260426_0002"
down_revision = "20260425_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "empresas",
        sa.Column("ultimo_nsu_distribuicao", sa.String(length=15), nullable=True),
    )
    op.add_column(
        "documentos_fiscais",
        sa.Column(
            "origem",
            sa.String(length=20),
            nullable=False,
            server_default="emitida",
        ),
    )
    op.create_index(
        "ix_documentos_fiscais_origem",
        "documentos_fiscais",
        ["origem"],
    )


def downgrade() -> None:
    op.drop_index("ix_documentos_fiscais_origem", table_name="documentos_fiscais")
    op.drop_column("documentos_fiscais", "origem")
    op.drop_column("empresas", "ultimo_nsu_distribuicao")
