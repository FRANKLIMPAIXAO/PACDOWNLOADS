"""Livro de cobranças geradas no PORTAL do cliente.

Hoje só registra os RECÁLCULOS de guia DAS que o cliente dispara: o 1º
recálculo de cada guia é GRÁTIS (valor=0), do 2º em diante é COBRADO (valor=5).
O escritório usa esse livro pra faturar o cliente (`paga` vira True quando
cobrado). Contar quantos recálculos uma guia já teve = contar linhas com
`guia_das_id` daquela guia — assim não precisei mexer na tabela `guias_das`
(ALTER COLUMN é o que costuma derrubar o app).

Tabela NOVA → `Base.metadata.create_all` do lifespan cria; a migration é redundância.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CobrancaPortal(Base):
    __tablename__ = "cobrancas_portal"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id"), nullable=False, index=True,
    )
    # Referência à guia recalculada (nullable: a guia pode ser apagada depois).
    guia_das_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    competencia: Mapped[str | None] = mapped_column(String(6), nullable=True)
    tipo: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="recalculo_das", index=True,
    )
    # 0.00 = grátis (1º recálculo), 5.00 = cobrado (2º+).
    valor: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"),
    )
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Escritório marca True quando efetivamente faturar/receber.
    paga: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )
