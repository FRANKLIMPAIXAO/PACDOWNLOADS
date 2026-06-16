"""empresa.cte_dist_ult_nsu — cursor NSU da Distribuição DF-e do CT-e

Guarda o último NSU sacado do Ambiente Nacional do CT-e (CTeDistribuicaoDFe) pra
puxar os conhecimentos de transporte (recebidas, tomadora do frete)
incrementalmente, com o mesmo cert A1 que a Distribuição da NFe usa. Fila do
CT-e é SEPARADA da NFe.

Revision ID: 20260616_0024
Revises: 20260614_0023
"""
from alembic import op
import sqlalchemy as sa


revision = "20260616_0024"
down_revision = "20260614_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "empresas",
        sa.Column("cte_dist_ult_nsu", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("empresas", "cte_dist_ult_nsu")
