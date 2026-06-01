"""Modelo de Guia DCTFWeb emitida via Integra Contador.

Cada chamada a GERARGUIA31 (declaração ATIVA) ou GERARGUIAANDAMENTO313 (em ANDAMENTO)
gera um DARF PDF que é salvo localmente em `storage/guias_dctfweb/{cnpj}/`.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.empresa import Empresa


class GuiaDctfweb(Base):
    """Guia DARF DCTFWeb emitida via Serpro.

    Não é unique por (empresa, periodo, categoria) porque o cliente pode
    re-emitir várias vezes (cada emissão gera um novo PDF datado).
    """
    __tablename__ = "guias_dctfweb"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # Categoria DCTFWeb (40, 50, 41, 51, 44, 45, 46) — guarda como string pra log
    categoria: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Período de apuração
    ano_pa: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    mes_pa: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    dia_pa: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cno_afericao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_proc_reclamatoria: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Origem: 'ativa' (GERARGUIA31) ou 'andamento' (GERARGUIAANDAMENTO313)
    origem: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    pdf_path: Mapped[str] = mapped_column(String(512), nullable=False)
    emitida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    empresa: Mapped["Empresa"] = relationship(lazy="joined")

    @property
    def periodo_formatado(self) -> str:
        """Devolve string legível pro UI: 'MM/YYYY' ou só 'YYYY' (anual)."""
        if self.mes_pa:
            return f"{self.mes_pa}/{self.ano_pa}"
        return self.ano_pa
