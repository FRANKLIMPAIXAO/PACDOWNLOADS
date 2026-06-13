from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Enum as SqlEnum, ForeignKey, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TipoDocumento(str, Enum):
    NFE = "NFE"
    CTE = "CTE"
    NFSE = "NFSE"


class DocumentoFiscal(Base):
    __tablename__ = "documentos_fiscais"
    __table_args__ = (
        UniqueConstraint("empresa_id", "tipo_documento", "chave_acesso", name="uq_documento_empresa_tipo_chave"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    tipo_documento: Mapped[TipoDocumento] = mapped_column(SqlEnum(TipoDocumento), index=True)
    chave_acesso: Mapped[str] = mapped_column(String(64), index=True)
    numero: Mapped[str | None] = mapped_column(String(30), nullable=True)
    serie: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_emissao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cnpj_emitente: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    nome_emitente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnpj_destinatario: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    nome_destinatario: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="baixado", nullable=False)
    xml_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    origem: Mapped[str] = mapped_column(
        String(20), default="emitida", server_default="emitida", nullable=False, index=True
    )
    json_original: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # tpNF da NFe: True=saída (venda/remessa), False=ENTRADA (nota de entrada
    # própria — compra de produtor rural, retorno de industrialização: a empresa
    # EMITE mas é compra, NÃO é faturamento). NULL = doc antigo antes do backfill.
    eh_saida: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    # Cancelamento (migration 0013) — detectado quando XML pos-manifestacao
    # vira procEventoNFe com descEvento=Cancelamento.
    cancelada: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False, index=True
    )
    cancelada_em: Mapped[date | None] = mapped_column(Date(), nullable=True)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    protocolo_cancelamento: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    empresa: Mapped[Empresa] = relationship(back_populates="documentos")
