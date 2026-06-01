"""Cria tabelas parcelamentos_simples (PARCSN) e guias_dctfweb.

Revision ID: 20260522_0016
Revises: 20260522_0015
Create Date: 2026-05-22 19:00:00

PARCSN: parcelamentos ativos do Simples Nacional (ordinário Lei 10.522).
Sincronizado via PEDIDOSPARC163 + OBTERPARC164. DAS emitido via GERARDAS161.

DCTFWeb: cada emissão de DARF via GERARGUIA31 (declaração ATIVA) ou
GERARGUIAANDAMENTO313 (em ANDAMENTO) salva o PDF e registra origem.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260522_0016"
down_revision = "20260522_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # parcelamentos_simples
    op.create_table(
        "parcelamentos_simples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column(
            "modalidade", sa.String(length=20), nullable=False, server_default="PARCSN",
        ),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("data_pedido", sa.Date(), nullable=True),
        sa.Column("situacao", sa.String(length=64), nullable=True),
        sa.Column("data_situacao", sa.Date(), nullable=True),
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
            "empresa_id", "numero", name="uq_parcsn_empresa_numero",
        ),
    )
    op.create_index("ix_parcsn_id", "parcelamentos_simples", ["id"])
    op.create_index("ix_parcsn_empresa_id", "parcelamentos_simples", ["empresa_id"])
    op.create_index("ix_parcsn_modalidade", "parcelamentos_simples", ["modalidade"])
    op.create_index("ix_parcsn_numero", "parcelamentos_simples", ["numero"])
    op.create_index("ix_parcsn_situacao", "parcelamentos_simples", ["situacao"])

    # guias_dctfweb
    op.create_table(
        "guias_dctfweb",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("ano_pa", sa.String(length=4), nullable=False),
        sa.Column("mes_pa", sa.String(length=2), nullable=True),
        sa.Column("dia_pa", sa.String(length=2), nullable=True),
        sa.Column("cno_afericao", sa.Integer(), nullable=True),
        sa.Column("num_proc_reclamatoria", sa.String(length=64), nullable=True),
        sa.Column("origem", sa.String(length=20), nullable=False),
        sa.Column("pdf_path", sa.String(length=512), nullable=False),
        sa.Column(
            "emitida_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dctfweb_id", "guias_dctfweb", ["id"])
    op.create_index("ix_dctfweb_empresa_id", "guias_dctfweb", ["empresa_id"])
    op.create_index("ix_dctfweb_categoria", "guias_dctfweb", ["categoria"])
    op.create_index("ix_dctfweb_ano_pa", "guias_dctfweb", ["ano_pa"])
    op.create_index("ix_dctfweb_mes_pa", "guias_dctfweb", ["mes_pa"])
    op.create_index("ix_dctfweb_origem", "guias_dctfweb", ["origem"])


def downgrade() -> None:
    for ix in (
        "ix_dctfweb_origem", "ix_dctfweb_mes_pa", "ix_dctfweb_ano_pa",
        "ix_dctfweb_categoria", "ix_dctfweb_empresa_id", "ix_dctfweb_id",
    ):
        op.drop_index(ix, table_name="guias_dctfweb")
    op.drop_table("guias_dctfweb")
    for ix in (
        "ix_parcsn_situacao", "ix_parcsn_numero", "ix_parcsn_modalidade",
        "ix_parcsn_empresa_id", "ix_parcsn_id",
    ):
        op.drop_index(ix, table_name="parcelamentos_simples")
    op.drop_table("parcelamentos_simples")
