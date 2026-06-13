"""Rotas da Distribuição DF-e da NFe (direto com cert A1, sem Focus)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.dfe_distribuicao_service import DfeDistribuicaoService

router = APIRouter(
    prefix="/dfe-nfe", tags=["dfe-nfe"], dependencies=[Depends(get_current_user)],
)


@router.post("/empresa/{empresa_id}/distribuir")
def distribuir(
    empresa_id: int,
    max_paginas: int = 15,
    db: Session = Depends(get_db),
) -> dict:
    """Puxa do Ambiente Nacional as NFes da empresa (recebidas resumo + completas).

    Usa o certificado A1 da empresa (mTLS), modelo NSU — incremental, de graça.
    `max_paginas`: limite de páginas (cada ~50 docs) por chamada, pra caber no
    timeout. Re-chame até `cstat`=137 (sem mais docs).
    """
    return DfeDistribuicaoService(db).distribuir_empresa(empresa_id, max_paginas=max_paginas)
