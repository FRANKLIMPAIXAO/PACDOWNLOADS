"""documentos_fiscais: adiciona cancelada / cancelada_em / motivo_cancelamento

Revision ID: 20260518_0013
Revises: 20260518_0012
Create Date: 2026-05-18 16:00:00

Quando o emitente cancela uma NF-e, a SEFAZ registra um evento de
Cancelamento (`procEventoNFe descEvento=Cancelamento`). A Focus expoe esse
evento via o mesmo endpoint `/v2/nfes_recebidas/{chave}.xml` — ao re-baixar
apos a manifestacao, em vez do `procNFe` o sistema recebe o
`procEventoNFe`. Precisamos detectar isso e marcar a NF como cancelada
para nao entrar em apuracao.

Campos adicionados:
- cancelada (boolean, default False, indexed)
- cancelada_em (date)
- motivo_cancelamento (string 255 — copia do xJust do evento)
- protocolo_cancelamento (string 30 — copia do nProt do evento)
"""
from alembic import op
import sqlalchemy as sa


revision = "20260518_0013"
down_revision = "20260518_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documentos_fiscais") as batch:
        batch.add_column(
            sa.Column("cancelada", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("cancelada_em", sa.Date(), nullable=True))
        batch.add_column(sa.Column("motivo_cancelamento", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("protocolo_cancelamento", sa.String(length=30), nullable=True))
        batch.create_index(
            "ix_documentos_fiscais_cancelada",
            ["cancelada"],
        )


def downgrade() -> None:
    with op.batch_alter_table("documentos_fiscais") as batch:
        batch.drop_index("ix_documentos_fiscais_cancelada")
        batch.drop_column("protocolo_cancelamento")
        batch.drop_column("motivo_cancelamento")
        batch.drop_column("cancelada_em")
        batch.drop_column("cancelada")
