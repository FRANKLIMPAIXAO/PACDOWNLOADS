"""tipocertidao: adiciona FEDERAL_OFICIAL (CND oficial RFB+PGFN)

Revision ID: 20260506_0011
Revises: 20260505_0010
Create Date: 2026-05-06 09:00:00

Separa o tipo FEDERAL em dois:
- FEDERAL: SITFIS (Integra Contador) — uso interno, validade 60d
- FEDERAL_OFICIAL: CND oficial RFB+PGFN (Playwright) — sob demanda,
  validade 180d
"""
from alembic import op
import sqlalchemy as sa


revision = "20260506_0011"
down_revision = "20260505_0010"
branch_labels = None
depends_on = None


_VALORES_NOVOS = ("FEDERAL", "FEDERAL_OFICIAL", "FGTS", "TRABALHISTA", "ESTADUAL", "MUNICIPAL")
_VALORES_ANTIGOS = ("FEDERAL", "FGTS", "TRABALHISTA", "ESTADUAL", "MUNICIPAL")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Em Postgres, ALTER TYPE permite ADD VALUE diretamente
        op.execute("ALTER TYPE tipocertidao ADD VALUE IF NOT EXISTS 'FEDERAL_OFICIAL'")
    else:
        # SQLite: enum eh CHECK constraint, precisa recriar a tabela via batch_alter
        with op.batch_alter_table("certidoes") as batch:
            batch.alter_column(
                "tipo",
                existing_type=sa.Enum(*_VALORES_ANTIGOS, name="tipocertidao"),
                type_=sa.Enum(*_VALORES_NOVOS, name="tipocertidao"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Postgres: reverter enum requer recriar — pulamos no MVP
        # (em producao, evite downgrade desta migracao apos uso real)
        pass
    else:
        # Antes de remover FEDERAL_OFICIAL, transforma linhas existentes em FEDERAL
        op.execute(
            "UPDATE certidoes SET tipo = 'FEDERAL' WHERE tipo = 'FEDERAL_OFICIAL'"
        )
        with op.batch_alter_table("certidoes") as batch:
            batch.alter_column(
                "tipo",
                existing_type=sa.Enum(*_VALORES_NOVOS, name="tipocertidao"),
                type_=sa.Enum(*_VALORES_ANTIGOS, name="tipocertidao"),
            )
