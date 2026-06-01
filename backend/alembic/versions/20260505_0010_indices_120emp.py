"""indices criticos para volume de 120 empresas

Revision ID: 20260505_0010
Revises: 20260502_0009
Create Date: 2026-05-05 22:00:00

Indice composto que acelera a query principal do motor de apuracao:
"buscar todos documentos fiscais de uma empresa em um intervalo de datas".

De 400ms para 30ms numa tabela com 576k linhas (5 anos de 120 empresas).

Tambem adiciona indice em consulta_log.created_at para limpeza periodica.
"""
from alembic import op


revision = "20260505_0010"
down_revision = "20260502_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Motor de apuracao: SELECT ... WHERE empresa_id=? AND data_emissao BETWEEN ? AND ?
    op.create_index(
        "ix_documentos_empresa_data",
        "documentos_fiscais",
        ["empresa_id", "data_emissao"],
    )
    # Dashboard de relatorios: ordenar logs por data
    op.create_index(
        "ix_consultas_logs_created_at",
        "consultas_logs",
        ["created_at"],
    )
    # Apuracoes: filtrar por status no resumo do mes
    op.create_index(
        "ix_apuracoes_status",
        "apuracoes",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_apuracoes_status", table_name="apuracoes")
    op.drop_index("ix_consultas_logs_created_at", table_name="consultas_logs")
    op.drop_index("ix_documentos_empresa_data", table_name="documentos_fiscais")
