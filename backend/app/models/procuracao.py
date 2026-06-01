from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Procuracao(Base):
    """Procuracao eletronica eCAC outorgada pelo cliente ao escritorio.

    Sincronizada via OBTERPROCURACAO41 do Integra Contador. Existem 0 ou 1 por
    empresa (a mais recente sobrescreve via empresa_id unique constraint? hoje
    nao — multiplas linhas para historico, sempre lendo a mais recente).
    """

    __tablename__ = "procuracoes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    cnpj_outorgante: Mapped[str] = mapped_column(String(14))
    cnpj_outorgado: Mapped[str] = mapped_column(String(14))
    data_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    data_fim: Mapped[str | None] = mapped_column(String(10), nullable=True)
    situacao: Mapped[str] = mapped_column(String(30), default="DESCONHECIDA")
    servicos_autorizados: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sincronizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    empresa = relationship("Empresa")

    @property
    def ativa(self) -> bool:
        return self.situacao.upper() == "ATIVA"
