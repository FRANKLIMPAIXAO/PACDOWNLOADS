"""Modelo de Parcelamento Simples Nacional (PARCSN ordinário).

Cada parcelamento ativo no Integra Contador (PARCSN PEDIDOSPARC163) cria/atualiza
uma linha aqui. Detalhes (valor total, parcelas pagas, restantes) vêm via OBTERPARC164.
Parcelas individuais (próximas a vencer) vêm via PARCELASPARAGERAR162.
DAS de cada parcela emitido via GERARDAS161 com PDF salvo localmente.
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


class ParcelamentoSimples(Base):
    """Parcelamento PARCSN ordinário (Lei 10.522/2002 — 60 parcelas).

    Pra MVP: foco em PARCSN ordinário. Modalidades futuras (PARCSN-ESP, PERTSN,
    RELPSN, PARCMEI etc) podem adicionar campo `modalidade` se necessário.
    """
    __tablename__ = "parcelamentos_simples"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero", name="uq_parcsn_empresa_numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    modalidade: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PARCSN", index=True,
    )

    # Identificador do parcelamento na Serpro (Number, mas guardamos como int)
    numero: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Dados PEDIDOSPARC163 (lista) e OBTERPARC164 (detalhe)
    data_pedido: Mapped[date | None] = mapped_column(Date, nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    data_situacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Vem de OBTERPARC164
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
