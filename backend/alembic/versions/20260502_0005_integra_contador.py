"""integra contador: tabelas procuracoes e mensagens_ecac

Revision ID: 20260502_0005
Revises: 20260502_0004
Create Date: 2026-05-02 16:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260502_0005"
down_revision = "20260502_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procuracoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("cnpj_outorgante", sa.String(length=14), nullable=False),
        sa.Column("cnpj_outorgado", sa.String(length=14), nullable=False),
        sa.Column("data_inicio", sa.String(length=10), nullable=True),
        sa.Column("data_fim", sa.String(length=10), nullable=True),
        sa.Column("situacao", sa.String(length=30), nullable=False, server_default="DESCONHECIDA"),
        sa.Column("servicos_autorizados", sa.JSON(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "sincronizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_procuracoes_empresa_id", "procuracoes", ["empresa_id"])

    op.create_table(
        "mensagens_ecac",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresas.id"), nullable=False),
        sa.Column("isn_msg", sa.String(length=40), nullable=False),
        sa.Column("assunto", sa.String(length=500), nullable=True),
        sa.Column("remetente", sa.String(length=255), nullable=True),
        sa.Column("data_envio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indicador_leitura", sa.String(length=2), nullable=True),
        sa.Column("indicador_relevancia", sa.String(length=20), nullable=True),
        sa.Column("conteudo_html", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "sincronizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("empresa_id", "isn_msg", name="uq_mensagens_ecac_empresa_isn"),
    )
    op.create_index("ix_mensagens_ecac_empresa_id", "mensagens_ecac", ["empresa_id"])
    op.create_index("ix_mensagens_ecac_isn_msg", "mensagens_ecac", ["isn_msg"])


def downgrade() -> None:
    op.drop_index("ix_mensagens_ecac_isn_msg", table_name="mensagens_ecac")
    op.drop_index("ix_mensagens_ecac_empresa_id", table_name="mensagens_ecac")
    op.drop_table("mensagens_ecac")
    op.drop_index("ix_procuracoes_empresa_id", table_name="procuracoes")
    op.drop_table("procuracoes")
