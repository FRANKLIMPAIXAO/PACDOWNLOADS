"""focus nfe: adiciona empresas.focus_token

Revision ID: 20260427_0003
Revises: 20260426_0002
Create Date: 2026-04-27 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260427_0003"
down_revision = "20260426_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "empresas",
        sa.Column("focus_token", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("empresas", "focus_token")
