"""usuario.is_cliente + empresa_id — portal do cliente (multi-tenant)

VERSÃO MÍNIMA E IDEMPOTENTE. A 1ª versão tinha create_index + create_foreign_key
junto; como o DDL do Postgres é transacional, se o index/FK falhasse ele
REVERTIA os add_column junto → o app subia sem a coluna `is_cliente` e TODO
login quebrava (o entrypoint engole o erro do alembic e sobe mesmo assim).

Aqui só os 2 add_column, com checagem "se a coluna já existe" — não tem como
falhar nem re-rodar quebrado. Index/FK eram só otimização; o ForeignKey no
model é metadata (não exige a constraint no banco), e queries por empresa_id
funcionam sem índice.

Revision ID: 20260616_0025
Revises: 20260616_0024
"""
from alembic import op
import sqlalchemy as sa


revision = "20260616_0025"
down_revision = "20260616_0024"
branch_labels = None
depends_on = None


def _tem_coluna(tabela: str, coluna: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(tabela)]
    return coluna in cols


def upgrade() -> None:
    if not _tem_coluna("usuarios", "is_cliente"):
        op.add_column(
            "usuarios",
            sa.Column(
                "is_cliente", sa.Boolean(), nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if not _tem_coluna("usuarios", "empresa_id"):
        op.add_column(
            "usuarios",
            sa.Column("empresa_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    if _tem_coluna("usuarios", "empresa_id"):
        op.drop_column("usuarios", "empresa_id")
    if _tem_coluna("usuarios", "is_cliente"):
        op.drop_column("usuarios", "is_cliente")
