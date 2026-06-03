from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SituacaoFiscal(Base):
    """Relatorio SITFIS gerado via Integra Contador (Serpro).

    Cada execucao do fluxo SOLICITARPROTOCOLO91 + RELATORIOSITFIS92 cria uma
    linha. O PDF eh salvo no storage local; o caminho fica em `pdf_path`.
    """

    __tablename__ = "situacoes_fiscais"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    # Protocolo Serpro real eh base64 com ~250 chars. Mock antigo era curto.
    # Mantemos 500 pra margem confortavel.
    protocolo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="GERADO")
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gerada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    empresa = relationship("Empresa")
