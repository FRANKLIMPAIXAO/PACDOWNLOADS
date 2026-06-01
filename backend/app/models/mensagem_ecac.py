from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MensagemEcac(Base):
    """Mensagem da caixa postal eCAC recebida via Integra Contador.

    Idempotencia: (empresa_id, isn_msg) UNIQUE — re-syncs nao duplicam.
    """

    __tablename__ = "mensagens_ecac"
    __table_args__ = (
        UniqueConstraint("empresa_id", "isn_msg", name="uq_mensagens_ecac_empresa_isn"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    isn_msg: Mapped[str] = mapped_column(String(40), index=True)
    assunto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remetente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_envio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indicador_leitura: Mapped[str | None] = mapped_column(String(2), nullable=True)
    indicador_relevancia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conteudo_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sincronizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    empresa = relationship("Empresa")
