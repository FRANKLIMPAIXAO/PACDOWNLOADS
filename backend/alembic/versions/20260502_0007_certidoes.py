"""cnd: tabela certidoes (controle de CND/CRF/CNDT)

Revision ID: 20260502_0007
Revises: 20260502_0006
Create Date: 2026-05-02 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0007"
down_revision = "20260502_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certidoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "FEDERAL", "FGTS", "TRABALHISTA", "ESTADUAL", "MUNICIPAL",
                name="tipocertidao",
            ),
            nullable=False,
        ),
        sa.Column("numero", sa.String(length=120), nullable=True),
        sa.Column("data_emissao", sa.Date(), nullable=True),
        sa.Column("data_validade", sa.Date(), nullable=False),
        sa.Column("pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_certidoes_empresa_id", "certidoes", ["empresa_id"])
    op.create_index("ix_certidoes_data_validade", "certidoes", ["data_validade"])


def downgrade() -> None:
    op.drop_index("ix_certidoes_data_validade", table_name="certidoes")
    op.drop_index("ix_certidoes_empresa_id", table_name="certidoes")
    op.drop_table("certidoes")
