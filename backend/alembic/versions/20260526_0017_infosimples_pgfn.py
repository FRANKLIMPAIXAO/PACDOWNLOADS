"""Cria tabelas cache_infosimples e parcelamentos_pgfn.

Revision ID: 20260526_0017
Revises: 20260522_0016
Create Date: 2026-05-26 09:00:00

cache_infosimples: TTL pra respostas do Infosimples (CND 30d, PGFN 7d) —
economiza saldo pré-pago em re-consultas.

parcelamentos_pgfn: parcelamentos ativos da Dívida Ativa (PGFN), sincronizados
via Infosimples já que Serpro não tem API direta pra isso.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260526_0017"
down_revision = "20260522_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # cache_infosimples
    op.create_table(
        "cache_infosimples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("custo_centavos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cnpj", "endpoint", "payload_hash",
            name="uq_cache_info_cnpj_endpoint",
        ),
    )
    op.create_index("ix_cache_info_id", "cache_infosimples", ["id"])
    op.create_index("ix_cache_info_cnpj", "cache_infosimples", ["cnpj"])
    op.create_index("ix_cache_info_endpoint", "cache_infosimples", ["endpoint"])
    op.create_index("ix_cache_info_expires", "cache_infosimples", ["expires_at"])

    # parcelamentos_pgfn
    op.create_table(
        "parcelamentos_pgfn",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=40), nullable=False),
        sa.Column(
            "modalidade", sa.String(length=80), nullable=False, server_default="PGFN",
        ),
        sa.Column("data_pedido", sa.Date(), nullable=True),
        sa.Column("situacao", sa.String(length=64), nullable=True),
        sa.Column("valor_total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("valor_total_pago", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("quantidade_parcelas", sa.Integer(), nullable=True),
        sa.Column("parcelas_pagas", sa.Integer(), nullable=True),
        sa.Column(
            "sincronizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id", "numero", name="uq_pgfn_empresa_numero",
        ),
    )
    op.create_index("ix_pgfn_id", "parcelamentos_pgfn", ["id"])
    op.create_index("ix_pgfn_empresa_id", "parcelamentos_pgfn", ["empresa_id"])
    op.create_index("ix_pgfn_modalidade", "parcelamentos_pgfn", ["modalidade"])
    op.create_index("ix_pgfn_numero", "parcelamentos_pgfn", ["numero"])
    op.create_index("ix_pgfn_situacao", "parcelamentos_pgfn", ["situacao"])


def downgrade() -> None:
    for ix in (
        "ix_pgfn_situacao", "ix_pgfn_numero", "ix_pgfn_modalidade",
        "ix_pgfn_empresa_id", "ix_pgfn_id",
    ):
        op.drop_index(ix, table_name="parcelamentos_pgfn")
    op.drop_table("parcelamentos_pgfn")

    for ix in (
        "ix_cache_info_expires", "ix_cache_info_endpoint",
        "ix_cache_info_cnpj", "ix_cache_info_id",
    ):
        op.drop_index(ix, table_name="cache_infosimples")
    op.drop_table("cache_infosimples")
