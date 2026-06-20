"""Rotas da Distribuição DF-e da NFe (direto com cert A1, sem Focus)."""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.dfe_distribuicao_service import DfeDistribuicaoService

router = APIRouter(
    prefix="/dfe-nfe", tags=["dfe-nfe"], dependencies=[Depends(get_current_user)],
)

# Router do cron: SEM JWT (um cron externo chama), protegido por token em header.
router_cron = APIRouter(prefix="/dfe-nfe", tags=["dfe-nfe-cron"])


@router_cron.post("/cron")
def cron_diario(
    x_cron_token: str = Header(default=""),
    chunk: int = 2,
    db: Session = Depends(get_db),
) -> dict:
    """Passo do cron diário (distribuir + manifestar um pedaço da carteira).

    Chamado por um cron EXTERNO a cada ~10-15 min. Protegido por `X-Cron-Token`
    (env `DFE_CRON_TOKEN`). `chunk` = empresas por chamada (cap interno por
    tempo pra caber no proxy).
    """
    esperado = os.getenv("DFE_CRON_TOKEN", "")
    if not esperado:
        raise HTTPException(status_code=503, detail="DFE_CRON_TOKEN não configurado no servidor.")
    if not x_cron_token or not hmac.compare_digest(x_cron_token, esperado):
        # compare_digest = comparação de tempo constante (anti timing-attack)
        raise HTTPException(status_code=401, detail="Token do cron inválido.")
    return DfeDistribuicaoService(db).cron_diario(chunk=max(1, min(chunk, 5)))


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
    reset: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Puxa do Ambiente Nacional as NFes da empresa (recebidas resumo + completas).

    Usa o certificado A1 da empresa (mTLS), modelo NSU — incremental, de graça.
    `max_paginas`: limite de páginas (cada ~50 docs) por chamada, pra caber no
    timeout. Re-chame até `cstat`=137 (sem mais docs).
    `reset=true`: re-puxa do começo (90 dias) — recupera o XML completo de notas
    cujo resumo já existe mas o procNFe foi descartado antes do fix do dedup.
    """
    return DfeDistribuicaoService(db).distribuir_empresa(
        empresa_id, max_paginas=max_paginas, reset_nsu=reset)


@router.post("/empresa/{empresa_id}/manifestar")
def manifestar(
    empresa_id: int,
    limite: int = 20,
    db: Session = Depends(get_db),
) -> dict:
    """Manifesta (Ciência da Operação) as recebidas em resumo da empresa.

    Envia o evento assinado (XML-DSig) pra cada nota; depois rode a Distribuição
    de novo pra baixar o XML completo. Processa em lote (`limite`).
    """
    return DfeDistribuicaoService(db).manifestar_recebidas(empresa_id, limite=limite)


@router.post("/documento/{documento_id}/manifestar")
def manifestar_documento(documento_id: int, db: Session = Depends(get_db)) -> dict:
    """Manifesta (Ciência da Operação) UMA nota — botão da linha em /documentos."""
    return DfeDistribuicaoService(db).manifestar_documento(documento_id)


@router.post("/empresa/{empresa_id}/diagnostico-evento")
def diagnostico_evento(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Dispara o evento assinado em 5 variantes de envelope/transporte SOAP e
    devolve o que cada uma respondeu. Acha sem chute qual o NFeRecepcaoEvento4
    do AN aceita (resolve o 'action não reconhecida')."""
    return DfeDistribuicaoService(db).diagnosticar_evento(empresa_id)


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
