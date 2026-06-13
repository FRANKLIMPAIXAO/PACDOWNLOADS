"""empresa.nfe_dist_ult_nsu — estado da Distribuição DF-e da NFe (NSU)

Guarda o último NSU sacado do Ambiente Nacional pra puxar as notas
(recebidas+emitidas) incrementalmente, direto com o cert A1 (sem Focus).

Revision ID: 20260613_0022
Revises: 20260613_0021
"""
from alembic import op
import sqlalchemy as sa


revision = "20260613_0022"
down_revision = "20260613_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "empresas",
        sa.Column("nfe_dist_ult_nsu", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("empresas", "nfe_dist_ult_nsu")
