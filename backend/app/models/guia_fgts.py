"""Modelo de Guia FGTS Digital emitida via Infosimples (modo Procurador).

Cada emissão via /consultas/fgts/guia-rapida cria/atualiza uma linha aqui.
Único por (empresa_id, periodo) — re-emitir mesma competência ATUALIZA
o registro existente (valores podem mudar se houve admissão/demissão).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.empresa import Empresa


class GuiaFgts(Base):
    """Guia FGTS Digital (DARF) emitida via Infosimples."""

    __tablename__ = "guias_fgts"
    __table_args__ = (
        UniqueConstraint("empresa_id", "periodo", name="uq_fgts_empresa_periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # YYYYMM (formato Infosimples)
    periodo: Mapped[str] = mapped_column(String(6), nullable=False, index=True)

    competencia_formatada: Mapped[str | None] = mapped_column(String(7), nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # Valores
    valor_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"),
    )
    valor_mensal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    valor_rescisorio: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    valor_compensatorio: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    valor_encargos: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    quantidade_trabalhadores: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # PDF — primeiro guarda URL do Infosimples, depois baixamos pra storage local
    pdf_url_infosimples: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Status local
    situacao: Mapped[str] = mapped_column(
        String(20), nullable=False, default="emitida", index=True,
    )  # 'emitida' | 'paga' | 'vencida'
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    emitida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    empresa: Mapped["Empresa"] = relationship(lazy="joined")

    @property
    def dias_para_vencer(self) -> int | None:
        if not self.data_vencimento:
            return None
        return (self.data_vencimento - date.today()).days

    @property
    def status_calculado(self) -> str:
        """Calcula status considerando vencimento. Override do `situacao` salvo."""
        if self.situacao == "paga":
            return "paga"
        if self.data_vencimento and self.data_vencimento < date.today():
            return "vencida"
        return "emitida"
