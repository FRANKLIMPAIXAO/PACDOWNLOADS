from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConectorEmailExecucao(Base):
    """Histórico de cada leitura da caixa de e-mail (conector de saídas Nível 2).

    Dá visibilidade ao cron (que roda no escuro): quando rodou, de quais empresas
    entraram notas e se teve erro. Tabela NOVA — `Base.metadata.create_all` cria
    sozinho no startup (sem migration; só ALTER de coluna exige alembic).
    """
    __tablename__ = "conector_email_execucoes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    origem: Mapped[str] = mapped_column(String(20), default="cron", nullable=False)  # cron | manual
    emails_lidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    anexos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    persistidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nao_cadastrada: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    erros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # JSON em texto (Postgres + SQLite): amostra de remetentes e quebra por empresa.
    remetentes: Mapped[str | None] = mapped_column(Text, nullable=True)
    detalhe_empresas: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Preenchido só se a RODADA INTEIRA falhou (ex.: IMAP login/conexão).
    erro_msg: Mapped[str | None] = mapped_column(String(500), nullable=True)
