"""empresa.nfse_adn_ult_nsu — cursor NSU do ADN da NFS-e

Guarda o último NSU sacado do Ambiente de Dados Nacional (ADN) da NFS-e pra
puxar as notas de serviço (emitidas+recebidas) incrementalmente, com o mesmo
cert A1 que a Distribuição DF-e usa.

Revision ID: 20260614_0023
Revises: 20260613_0022
"""
from alembic import op
import sqlalchemy as sa


revision = "20260614_0023"
down_revision = "20260613_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "empresas",
        sa.Column("nfse_adn_ult_nsu", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("empresas", "nfse_adn_ult_nsu")
