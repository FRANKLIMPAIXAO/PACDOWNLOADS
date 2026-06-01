from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConsultaLog(Base):
    __tablename__ = "consultas_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), nullable=True, index=True)
    tipo_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    periodo_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    periodo_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    detalhes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    empresa: Mapped[Empresa | None] = relationship(back_populates="logs")
