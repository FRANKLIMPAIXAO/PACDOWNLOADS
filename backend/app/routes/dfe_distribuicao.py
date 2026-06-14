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
