"""Cache TTL pra respostas Infosimples (economiza saldo pré-pago).

Cada (cnpj, endpoint, payload_hash) cacheia a resposta JSON crua por X dias.
Caller decide TTL:
- CND VALIDA (vence > 30d) → 30 dias
- CND A_VENCER (vence <= 30d) → 7 dias
- CND VENCIDA → 1 dia
- PGFN parcelamentos → 7 dias

Quando expira, próxima chamada bate na API real, atualiza cache.
`force=True` bypassa cache (botão "atualizar agora" na UI).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CacheInfosimples(Base):
    """Uma linha por (cnpj, endpoint, payload_hash) — resposta crua + TTL."""

    __tablename__ = "cache_infosimples"
    __table_args__ = (
        UniqueConstraint(
            "cnpj", "endpoint", "payload_hash",
            name="uq_cache_info_cnpj_endpoint",
        ),
        Index("ix_cache_info_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    # Path do endpoint Infosimples (ex: "/consultas/caixa/fgts")
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # MD5 do payload extra (filtros, mês ref, etc.) — só importa se enviarmos
    # parâmetros além de CNPJ. Hoje é '' fixo, mas reservado pra futuro.
    payload_hash: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # JSON cru da resposta (campo `data` do Infosimples)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Quando o cache expira (datetime UTC). Após isso, próxima chamada bate na API.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Quanto custou — pra contabilidade interna (somar gasto Infosimples no mês)
    custo_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
