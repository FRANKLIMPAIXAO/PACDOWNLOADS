from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortalAcessoLog(Base):
    """Registro de acesso do CLIENTE ao portal (login). Dá o controle de quem está
    acessando e com que frequência. Tabela NOVA — `create_all` cria no startup.

    Privacidade (LGPD): guarda só o mínimo (quem/quando/empresa ativa + IP curto
    pra segurança). Sem dado sensível."""
    __tablename__ = "portal_acesso_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    ip: Mapped[str | None] = mapped_column(String(60), nullable=True)
    evento: Mapped[str] = mapped_column(String(20), default="login", nullable=False)  # login | troca_empresa
