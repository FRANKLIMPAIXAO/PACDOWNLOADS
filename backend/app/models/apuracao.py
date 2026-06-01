from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    DateTime, Enum as SqlEnum, ForeignKey, JSON, Numeric, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StatusApuracao(str, Enum):
    DRAFT = "DRAFT"            # criada, sem transmissao
    TRANSMITIDA = "TRANSMITIDA"  # PGDAS-D entregue
    DAS_GERADO = "DAS_GERADO"  # DAS gerado e disponivel
    PAGO = "PAGO"              # marcado como pago manualmente
    ERRO = "ERRO"


class RegimeApuracao(str, Enum):
    SIMPLES_NACIONAL = "SIMPLES_NACIONAL"
    LUCRO_PRESUMIDO = "LUCRO_PRESUMIDO"
    LUCRO_REAL = "LUCRO_REAL"
    MEI = "MEI"


class Apuracao(Base):
    """Apuracao mensal de tributos.

    Por enquanto cobre PGDAS-D (Simples Nacional). Futuras competencias podem
    abrigar Lucro Presumido (apuracao trimestral DARF), DCTFWeb e MIT.
    """

    __tablename__ = "apuracoes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "ano_mes", name="uq_apuracoes_empresa_ano_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    ano_mes: Mapped[str] = mapped_column(String(6))  # "YYYYMM"
    regime: Mapped[RegimeApuracao] = mapped_column(
        SqlEnum(RegimeApuracao), default=RegimeApuracao.SIMPLES_NACIONAL,
    )
    status: Mapped[StatusApuracao] = mapped_column(
        SqlEnum(StatusApuracao), default=StatusApuracao.DRAFT,
    )
    receita_bruta: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_devido: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    numero_declaracao: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recibo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transmitida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    das_numero_documento: Mapped[str | None] = mapped_column(String(80), nullable=True)
    das_codigo_barras: Mapped[str | None] = mapped_column(String(120), nullable=True)
    das_data_vencimento: Mapped[str | None] = mapped_column(String(10), nullable=True)
    das_pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_declaracao: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_das: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    receitas_segregadas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    empresa = relationship("Empresa")
