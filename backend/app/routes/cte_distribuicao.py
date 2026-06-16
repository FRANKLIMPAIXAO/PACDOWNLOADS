"""Rotas da Distribuição DF-e do CT-e (direto com cert A1, sem Focus)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.cte_distribuicao_service import CteDistribuicaoService

router = APIRouter(
    prefix="/dfe-cte", tags=["dfe-cte"], dependencies=[Depends(get_current_user)],
)


class DistribuirLotePayload(BaseModel):
    empresa_ids: list[int] = Field(..., description="IDs do bloco (máx 5)")
    max_paginas: int = Field(8, ge=1, le=20)


@router.get("/elegiveis")
def elegiveis(db: Session = Depends(get_db)) -> list[dict]:
    """Empresas aptas pra Distribuição CT-e: ativas + cert A1 (NÃO exclui Focus)."""
    emps = CteDistribuicaoService(db).listar_elegiveis()
    return [
        {"id": e.id, "razao_social": e.razao_social, "cnpj": e.cnpj,
         "ult_nsu": e.cte_dist_ult_nsu}
        for e in emps
    ]


@router.post("/empresa/{empresa_id}/distribuir")
def distribuir(
    empresa_id: int,
    max_paginas: int = 15,
    reset: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Puxa do Ambiente Nacional os CT-e da empresa (tomadora do frete).

    Usa o certificado A1 (mTLS), modelo NSU — incremental, de graça. Re-chame
    até `cstat`=137 (sem mais docs). `reset=true` re-puxa do começo.
    """
    return CteDistribuicaoService(db).distribuir_empresa(
        empresa_id, max_paginas=max_paginas, reset_nsu=reset)


@router.post("/distribuir-lote")
def distribuir_lote(payload: DistribuirLotePayload, db: Session = Depends(get_db)) -> dict:
    """Distribui um BLOCO de empresas (frontend fatia a carteira). Resiliente."""
    if not payload.empresa_ids:
        return {"resultados": []}
    if len(payload.empresa_ids) > 5:
        raise HTTPException(status_code=400, detail="Máximo 5 empresas por bloco.")
    resultados = CteDistribuicaoService(db).distribuir_lote(
        payload.empresa_ids, max_paginas=payload.max_paginas,
    )
    return {"resultados": resultados}
