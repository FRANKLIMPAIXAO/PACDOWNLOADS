from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CronExecucao(Base):
    """Histórico das execuções dos crons de distribuição (DF-e NFe e CT-e).

    Dá visibilidade aos crons que rodam no escuro (só log): quando rodou, quantas
    empresas processou, quantos docs novos entraram e quantas bateram no 656.
    Tabela NOVA — `Base.metadata.create_all` cria no startup (sem migration).
    """
    __tablename__ = "cron_execucoes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # dfe | cte
    total_elegiveis: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    novos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # resumos+completas
    com_656: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detalhe: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: processadas
    erro_msg: Mapped[str | None] = mapped_column(String(500), nullable=True)
