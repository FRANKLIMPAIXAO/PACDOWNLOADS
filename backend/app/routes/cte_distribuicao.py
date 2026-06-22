"""Rotas da Distribuição DF-e do CT-e (direto com cert A1, sem Focus)."""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.cte_distribuicao_service import CteDistribuicaoService

router = APIRouter(
    prefix="/dfe-cte", tags=["dfe-cte"], dependencies=[Depends(get_current_user)],
)

# Router do cron: SEM JWT (um cron externo chama), protegido por token em header.
router_cron = APIRouter(prefix="/dfe-cte", tags=["dfe-cte-cron"])


@router_cron.post("/cron")
def cron(x_cron_token: str = Header(default=""), chunk: int = 2, db: Session = Depends(get_db)) -> dict:
    """Passo do cron do CT-e (distribui um pedaço da carteira). Chamado por um cron
    EXTERNO a cada ~15 min. Protegido por `X-Cron-Token` (env `CTE_CRON_TOKEN`)."""
    esperado = os.getenv("CTE_CRON_TOKEN", "")
    if not esperado:
        raise HTTPException(status_code=503, detail="CTE_CRON_TOKEN não configurado no servidor.")
    if not x_cron_token or not hmac.compare_digest(x_cron_token, esperado):
        # compare_digest = comparação de tempo constante (anti timing-attack)
        raise HTTPException(status_code=401, detail="Token do cron inválido.")
    resultado = CteDistribuicaoService(db).cron_diario(chunk=max(1, min(chunk, 5)))
    from app.services.cron_log import registrar_cron
    registrar_cron(db, "cte", resultado)
    return resultado


@router.get("/cron-execucoes")
def cron_execucoes(limit: int = 30, db: Session = Depends(get_db)) -> dict:
    """Histórico do cron de CT-e (frete) — relatório."""
    from app.services.cron_log import listar_execucoes
    return {"execucoes": listar_execucoes(db, "cte", limit)}


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
