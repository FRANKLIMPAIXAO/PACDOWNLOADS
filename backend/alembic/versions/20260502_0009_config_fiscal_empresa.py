"""empresa: campos de config fiscal (anexo, atividade, iss)

Revision ID: 20260502_0009
Revises: 20260502_0008
Create Date: 2026-05-02 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0009"
down_revision = "20260502_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        batch.add_column(sa.Column("anexo_simples", sa.String(length=4), nullable=True))
        batch.add_column(sa.Column("atividade", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("iss_aliquota", sa.Numeric(5, 2), nullable=True))
        batch.add_column(sa.Column("folha_12m", sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        batch.drop_column("folha_12m")
        batch.drop_column("iss_aliquota")
        batch.drop_column("atividade")
        batch.drop_column("anexo_simples")
