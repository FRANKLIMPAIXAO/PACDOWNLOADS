"""focus_token: aumenta tamanho para 512 (suportar Fernet)

Revision ID: 20260502_0004
Revises: 20260427_0003
Create Date: 2026-05-02 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0004"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        batch.alter_column(
            "focus_token",
            existing_type=sa.String(length=128),
            type_=sa.String(length=512),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        batch.alter_column(
            "focus_token",
            existing_type=sa.String(length=512),
            type_=sa.String(length=128),
            existing_nullable=True,
        )
