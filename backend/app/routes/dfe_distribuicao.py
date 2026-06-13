"""Rotas da Distribuição DF-e da NFe (direto com cert A1, sem Focus)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.dfe_distribuicao_service import DfeDistribuicaoService

router = APIRouter(
    prefix="/dfe-nfe", tags=["dfe-nfe"], dependencies=[Depends(get_current_user)],
)


class DistribuirLotePayload(BaseModel):
    empresa_ids: list[int] = Field(..., description="IDs do bloco (máx 5)")
    max_paginas: int = Field(8, ge=1, le=20)


@router.get("/elegiveis")
def elegiveis(db: Session = Depends(get_db)) -> list[dict]:
    """Empresas aptas pra Distribuição Direta: ativas, com cert A1, SEM Focus."""
    emps = DfeDistribuicaoService(db).listar_elegiveis()
    return [
        {"id": e.id, "razao_social": e.razao_social, "cnpj": e.cnpj,
         "ult_nsu": e.nfe_dist_ult_nsu}
        for e in emps
    ]


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


@router.post("/distribuir-lote")
def distribuir_lote(payload: DistribuirLotePayload, db: Session = Depends(get_db)) -> dict:
    """Distribui um BLOCO de empresas (o frontend fatia a carteira em blocos
    pequenos pra caber no timeout). Resiliente: erro numa não derruba o bloco."""
    if not payload.empresa_ids:
        return {"resultados": []}
    if len(payload.empresa_ids) > 5:
        raise HTTPException(status_code=400, detail="Máximo 5 empresas por bloco.")
    resultados = DfeDistribuicaoService(db).distribuir_lote(
        payload.empresa_ids, max_paginas=payload.max_paginas,
    )
    return {"resultados": resultados}
