"""Modelo de Parcelamento PGFN (Procuradoria-Geral da Fazenda Nacional).

Cada parcelamento ativo da Dívida Ativa retornado pelo Infosimples cria/atualiza
uma linha aqui. Diferente do PARCSN (que vem da Serpro Integra Contador), PGFN
não tem API Serpro direta — Infosimples é o caminho prático.

Modalidades comuns:
- Parcelamento Ordinário (Lei 10.522/2002) — até 60 parcelas
- RegPag — programa de regularização específico
- Transação Tributária (Lei 13.988/2020) — descontos até 65%, até 145 meses
- PRR (Programa de Regularização Rural)
- Outros programas pontuais
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


class ParcelamentoPgfn(Base):
    """Parcelamento PGFN ativo na Dívida Ativa.

    Atualizado via Infosimples (`pgfn_parcelamentos`). Cache 7 dias por empresa
    pra economizar pré-pago.
    """

    __tablename__ = "parcelamentos_pgfn"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero", name="uq_pgfn_empresa_numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # Número da inscrição/parcelamento (string porque PGFN às vezes usa formato
    # alfanumérico, diferente do PARCSN que é só Number)
    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Modalidade (Parcelamento Ordinário, Transação, RegPag, etc.)
    modalidade: Mapped[str] = mapped_column(
        String(80), nullable=False, default="PGFN", index=True,
    )

    data_pedido: Mapped[date | None] = mapped_column(Date, nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Valores consolidados
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    valor_total_pago: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    quantidade_parcelas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcelas_pagas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sincronizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    empresa: Mapped["Empresa"] = relationship(lazy="joined")

    @property
    def parcelas_restantes(self) -> int | None:
        if self.quantidade_parcelas is None or self.parcelas_pagas is None:
            return None
        return max(0, self.quantidade_parcelas - self.parcelas_pagas)

    @property
    def percentual_concluido(self) -> float | None:
        if not self.quantidade_parcelas or self.parcelas_pagas is None:
            return None
        return round(100 * self.parcelas_pagas / self.quantidade_parcelas, 1)
