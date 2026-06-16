"""usuario.is_cliente + empresa_id — portal do cliente (multi-tenant)

Adiciona o conceito de CLIENTE no Usuario: um login que enxerga SÓ a própria
empresa (empresa_id), pelo /portal. Equipe do escritório segue is_cliente=False
/ empresa_id NULL (vê todas). O get_current_user rejeita cliente nos endpoints
do escritório; o get_current_cliente exige cliente no portal.

Revision ID: 20260616_0025
Revises: 20260616_0024
"""
from alembic import op
import sqlalchemy as sa


revision = "20260616_0025"
down_revision = "20260616_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column(
            "is_cliente", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column("empresa_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_usuarios_is_cliente", "usuarios", ["is_cliente"])
    op.create_index("ix_usuarios_empresa_id", "usuarios", ["empresa_id"])
    op.create_foreign_key(
        "fk_usuarios_empresa_id", "usuarios", "empresas", ["empresa_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_usuarios_empresa_id", "usuarios", type_="foreignkey")
    op.drop_index("ix_usuarios_empresa_id", table_name="usuarios")
    op.drop_index("ix_usuarios_is_cliente", table_name="usuarios")
    op.drop_column("usuarios", "empresa_id")
    op.drop_column("usuarios", "is_cliente")
