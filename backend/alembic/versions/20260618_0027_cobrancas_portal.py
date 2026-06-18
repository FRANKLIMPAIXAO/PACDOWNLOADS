"""cobrancas_portal — livro de cobranças do portal (recálculo de guia DAS)

Tabela NOVA (não mexe em nenhuma existente — risco baixo). Registra os
recálculos de DAS disparados pelo cliente: 1º grátis (valor=0), 2º+ cobrado
(valor=5). O `Base.metadata.create_all` do lifespan também cria; esta migration
é redundância idempotente.

Revision ID: 20260618_0027
Revises: 20260618_0026
"""
from alembic import op
import sqlalchemy as sa


revision = "20260618_0027"
down_revision = "20260618_0026"
branch_labels = None
depends_on = None


def _tem_tabela(nome: str) -> bool:
    return nome in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _tem_tabela("cobrancas_portal"):
        return
    op.create_table(
        "cobrancas_portal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False, index=True),
        sa.Column("guia_das_id", sa.Integer(), nullable=True, index=True),
        sa.Column("competencia", sa.String(length=6), nullable=True),
        sa.Column("tipo", sa.String(length=40), nullable=False, server_default="recalculo_das", index=True),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("descricao", sa.String(length=255), nullable=True),
        sa.Column("paga", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )


def downgrade() -> None:
    if _tem_tabela("cobrancas_portal"):
        op.drop_table("cobrancas_portal")
