"""Cria tabela receitas_mensais (faturamento mensal pra RBT12).

Revision ID: 20260604_0020
Revises: 20260603_0019
Create Date: 2026-06-04 18:00:00

Empresas recém-migradas não têm histórico de NFes dos 12 meses anteriores,
então o RBT12 (que define a alíquota do Simples) precisa ser informado
manualmente OU puxado da Receita via Integra Contador. Esta tabela guarda
o faturamento por competência (interno + exportação).
"""
from alembic import op
import sqlalchemy as sa


revision = "20260604_0020"
down_revision = "20260603_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receitas_mensais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("ano_mes", sa.String(length=6), nullable=False),
        sa.Column("valor_interno", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("valor_externo", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("origem", sa.String(length=12), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "ano_mes", name="uq_receita_mensal_empresa_ano_mes"),
    )
    op.create_index("ix_receitas_mensais_empresa_id", "receitas_mensais", ["empresa_id"])


def downgrade() -> None:
    op.drop_index("ix_receitas_mensais_empresa_id", table_name="receitas_mensais")
    op.drop_table("receitas_mensais")
