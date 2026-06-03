"""Aumenta situacoes_fiscais.protocolo de VARCHAR(80) para VARCHAR(500).

Revision ID: 20260603_0019
Revises: 20260526_0018
Create Date: 2026-06-03 22:30:00

Protocolo Serpro real (SOLICITARPROTOCOLO91) vem em base64 com ~250 chars.
Mock antigo era curto (cabia em 80). Em prod o INSERT estoura com
psycopg.errors.StringDataRightTruncation. Subimos pra 500 para folga.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260603_0019"
down_revision = "20260526_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "situacoes_fiscais",
        "protocolo",
        existing_type=sa.String(length=80),
        type_=sa.String(length=500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "situacoes_fiscais",
        "protocolo",
        existing_type=sa.String(length=500),
        type_=sa.String(length=80),
        existing_nullable=True,
    )
