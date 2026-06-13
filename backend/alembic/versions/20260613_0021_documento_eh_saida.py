"""documento_fiscal: coluna eh_saida (tpNF — saída vs nota de entrada própria)

Distingue faturamento real (saída/venda) de nota que a empresa EMITE mas é
ENTRADA (compra de produtor rural, retorno de industrialização). Sem isso o
card de Faturamento somava as duas e inflava (ex.: CLAVEAUX 2,18M vs 1,45M).

Revision ID: 20260613_0021
Revises: 20260604_0020
"""
from alembic import op
import sqlalchemy as sa


revision = "20260613_0021"
down_revision = "20260604_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documentos_fiscais",
        sa.Column("eh_saida", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_documentos_fiscais_eh_saida", "documentos_fiscais", ["eh_saida"],
    )


def downgrade() -> None:
    op.drop_index("ix_documentos_fiscais_eh_saida", table_name="documentos_fiscais")
    op.drop_column("documentos_fiscais", "eh_saida")
