"""documentos_escritorio — docs que o escritório entrega ao cliente (PAC TAREFAS)

Tabela NOVA (guia/relatório/comunicado/arquivo entregue ao cliente, vindo do
PAC TAREFAS). Não mexe em nenhuma tabela existente — risco baixo. O
`Base.metadata.create_all` do lifespan também cria; esta migration é redundância.

Revision ID: 20260618_0026
Revises: 20260616_0025
"""
from alembic import op
import sqlalchemy as sa


revision = "20260618_0026"
down_revision = "20260616_0025"
branch_labels = None
depends_on = None


def _tem_tabela(nome: str) -> bool:
    return nome in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _tem_tabela("documentos_escritorio"):
        return
    op.create_table(
        "documentos_escritorio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False, index=True),
        sa.Column("tipo", sa.String(length=30), nullable=False, server_default="outro", index=True),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("mensagem", sa.String(length=2000), nullable=True),
        sa.Column("competencia", sa.String(length=7), nullable=True),
        sa.Column("vencimento", sa.Date(), nullable=True),
        sa.Column("valor", sa.Numeric(15, 2), nullable=True),
        sa.Column("arquivo_path", sa.String(length=1024), nullable=True),
        sa.Column("nome_arquivo", sa.String(length=255), nullable=True),
        sa.Column("origem", sa.String(length=40), nullable=False, server_default="pac_tarefas"),
        sa.Column("enviado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("lido_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    if _tem_tabela("documentos_escritorio"):
        op.drop_table("documentos_escritorio")
