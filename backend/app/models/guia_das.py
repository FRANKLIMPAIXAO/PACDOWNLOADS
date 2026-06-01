"""Modelo de Guia DAS Simples Nacional.

Uma linha por (empresa, periodo_apuracao). Sincronizada via Integra Contador:
- declaração entregue → cria/atualiza linha com `valor_principal` + `data_vencimento_original`
- pagamento detectado em PAGAMENTOS71 → marca `situacao='paga'` + `data_pagamento`
- vencimento expirado sem pagamento → marca `situacao='atrasada'`
- emissão de guia atualizada via GERARDAS12 → preenche `valor_atualizado`, `pdf_path`,
  `numero_das`, `codigo_barras`, `data_vencimento_atualizada`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.empresa import Empresa


class GuiaDAS(Base):
    __tablename__ = "guias_das"
    __table_args__ = (
        UniqueConstraint("empresa_id", "periodo_apuracao", name="uq_guia_das_empresa_pa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # YYYYMM (formato Serpro PGDAS-D)
    periodo_apuracao: Mapped[str] = mapped_column(String(6), nullable=False, index=True)

    # Da declaração PGDAS-D (CONSDECREC13)
    numero_declaracao: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recibo_declaracao: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_transmissao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Valor original da declaração (sem mora)
    valor_principal: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"),
    )
    data_vencimento_original: Mapped[date] = mapped_column(Date, nullable=False)

    # Valor + dados da guia ATUALIZADA (gerada via GERARDAS12 quando atrasa)
    valor_atualizado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    data_vencimento_atualizada: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_das: Mapped[str | None] = mapped_column(String(32), nullable=True)
    codigo_barras: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    emitida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Situação calculada — `em_aberto`, `paga`, `atrasada`, `parcialmente_paga`
    situacao: Mapped[str] = mapped_column(
        String(20), nullable=False, default="em_aberto", index=True,
    )
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Última vez que sincronizou via Integra Contador
    sincronizada_em: Mapped[datetime] = mapped_column(
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
    def dias_atraso(self) -> int:
        """Dias decorridos desde o vencimento (0 se ainda no prazo)."""
        if self.situacao == "paga":
            return 0
        hoje = date.today()
        if hoje <= self.data_vencimento_original:
            return 0
        return (hoje - self.data_vencimento_original).days

    @property
    def competencia_formatada(self) -> str:
        """YYYYMM → MM/YYYY"""
        if len(self.periodo_apuracao) != 6:
            return self.periodo_apuracao
        return f"{self.periodo_apuracao[4:]}/{self.periodo_apuracao[:4]}"
