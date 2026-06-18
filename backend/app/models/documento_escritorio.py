from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentoEscritorio(Base):
    """Documento que o ESCRITÓRIO entrega ao cliente (guia, relatório, comunicado,
    arquivo livre) — vindo do PAC TAREFAS via /integracao/documentos. Aparece na
    área do cliente, SEPARADO das notas fiscais (DocumentoFiscal).

    Tabela NOVA — não mexe em nenhum model existente. `Base.metadata.create_all`
    cria sozinho; a migration é belt-and-suspenders.
    """
    __tablename__ = "documentos_escritorio"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=False)
    # guia | relatorio | comunicado | outro
    tipo: Mapped[str] = mapped_column(String(30), default="outro", nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    mensagem: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # competência "AAAA-MM" e vencimento/valor — usados pelas GUIAS (DAS/FGTS/DARF)
    competencia: Mapped[str | None] = mapped_column(String(7), nullable=True)
    vencimento: Mapped[date | None] = mapped_column(Date(), nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    # arquivo no disco (None = comunicado sem anexo)
    arquivo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    nome_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origem: Mapped[str] = mapped_column(String(40), default="pac_tarefas", nullable=False)
    enviado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    lido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
