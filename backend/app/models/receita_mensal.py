from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReceitaMensal(Base):
    """Faturamento mensal de uma empresa, por competência (AAAAMM).

    Usado pra compor o RBT12 (Receita Bruta dos 12 meses anteriores) que
    determina a alíquota efetiva do Simples Nacional. Empresas recém-migradas
    não têm histórico de NFes no sistema, então o faturamento dos meses
    anteriores precisa ser informado MANUALMENTE pra o cálculo do DAS bater
    com o da Receita.

    `origem`:
    - 'manual'    → digitado pelo contador (histórico pré-migração)
    - 'calculado' → derivado das NFes do mês pelo motor de cálculo
    """

    __tablename__ = "receitas_mensais"
    __table_args__ = (
        UniqueConstraint("empresa_id", "ano_mes", name="uq_receita_mensal_empresa_ano_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False, index=True)
    ano_mes: Mapped[str] = mapped_column(String(6), nullable=False)  # "AAAAMM"
    # Receita bruta do mês — mercado interno e exportação separados (PGDAS-D pede)
    valor_interno: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0",
    )
    valor_externo: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0",
    )
    origem: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="manual",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    empresa = relationship("Empresa")
