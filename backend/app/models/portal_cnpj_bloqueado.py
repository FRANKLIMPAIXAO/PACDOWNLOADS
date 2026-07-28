from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortalCnpjBloqueado(Base):
    """CNPJ de contraparte cujas notas ficam OCULTAS no portal do cliente.

    Escopo: por EMPRESA — vale para TODOS os logins do portal daquela empresa.
    Uso real: a empresa Laticínios não quer que os funcionários (portal) vejam
    as NFS-e emitidas por RCM/ROCA/ZULMA para ela. O CONTADOR (área do
    escritório) continua vendo tudo — o filtro só existe no portal.

    O bloqueio esconde qualquer nota da empresa em que o CNPJ apareça como
    emitente OU destinatário (contraparte), em qualquer caminho do portal.
    """
    __tablename__ = "portal_cnpjs_bloqueados"
    __table_args__ = (
        UniqueConstraint("empresa_id", "cnpj", name="uq_portal_bloqueio_empresa_cnpj"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    rotulo: Mapped[str | None] = mapped_column(String(160), nullable=True)  # nome amigável
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
