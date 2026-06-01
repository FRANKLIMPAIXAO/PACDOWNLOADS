"""Cria tabela execucoes_robo_sefaz pra histórico do agente SEFAZ-GO.

Revision ID: 20260522_0014
Revises: 20260518_0013
Create Date: 2026-05-22 17:00:00

Cada disparo do agente (cron mensal dia 5 às 03h, ou manual via botão
"Rodar agora" na página /robo-sefaz) cria uma linha aqui. Quando termina,
status vira `concluido` ou `erro` e as métricas agregadas são preenchidas
a partir do resumo JSON do agente.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260522_0014"
down_revision = "20260518_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execucoes_robo_sefaz",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("disparo", sa.String(length=20), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False, server_default="GO"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pendente"),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=True),
        sa.Column(
            "iniciado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_empresas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("com_zip", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sem_notas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("persistidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detalhes", sa.JSON(), nullable=True),
        sa.Column("motivo_erro", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execucoes_robo_sefaz_id", "execucoes_robo_sefaz", ["id"])
    op.create_index("ix_execucoes_robo_sefaz_disparo", "execucoes_robo_sefaz", ["disparo"])
    op.create_index("ix_execucoes_robo_sefaz_uf", "execucoes_robo_sefaz", ["uf"])
    op.create_index("ix_execucoes_robo_sefaz_status", "execucoes_robo_sefaz", ["status"])
    op.create_index("ix_execucoes_robo_sefaz_empresa_id", "execucoes_robo_sefaz", ["empresa_id"])
    op.create_index(
        "ix_execucoes_robo_sefaz_iniciado_em",
        "execucoes_robo_sefaz",
        ["iniciado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_execucoes_robo_sefaz_iniciado_em", table_name="execucoes_robo_sefaz")
    op.drop_index("ix_execucoes_robo_sefaz_empresa_id", table_name="execucoes_robo_sefaz")
    op.drop_index("ix_execucoes_robo_sefaz_status", table_name="execucoes_robo_sefaz")
    op.drop_index("ix_execucoes_robo_sefaz_uf", table_name="execucoes_robo_sefaz")
    op.drop_index("ix_execucoes_robo_sefaz_disparo", table_name="execucoes_robo_sefaz")
    op.drop_index("ix_execucoes_robo_sefaz_id", table_name="execucoes_robo_sefaz")
    op.drop_table("execucoes_robo_sefaz")
