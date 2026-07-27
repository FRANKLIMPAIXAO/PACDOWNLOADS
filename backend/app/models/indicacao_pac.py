from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IndicacaoPac(Base):
    """Indicação do programa PAC Indica.

    Enviada pelo formulário PÚBLICO da tela de login do portal (e, futuramente,
    de dentro do portal do cliente). Guarda quem indicou + quem foi indicado pro
    escritório entrar em contato e recompensar. Sem dado sensível (só nome +
    contato) — minimização LGPD.
    """
    __tablename__ = "indicacoes_pac"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Quem indica
    nome_indicador: Mapped[str] = mapped_column(String(120), nullable=False)
    contato_indicador: Mapped[str] = mapped_column(String(120), nullable=False)  # tel/e-mail
    empresa_indicador: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Quem foi indicado
    nome_indicado: Mapped[str] = mapped_column(String(120), nullable=False)
    contato_indicado: Mapped[str] = mapped_column(String(120), nullable=False)  # tel/e-mail
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Gestão pelo escritório
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="nova", server_default="nova", index=True,
    )  # nova | em_contato | convertida | descartada
    origem: Mapped[str] = mapped_column(
        String(30), nullable=False, default="portal_login", server_default="portal_login",
    )
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )
