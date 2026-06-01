"""Rotas REST de Parcelamentos Simples Nacional (PARCSN ordinário)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

import io

from app.database import get_db
from app.providers.integra_contador import IntegraContadorError
from app.schemas.parcelamento_simples_schema import (
    EmitirDasParcelaPayload,
    ParcelaGeravelRead,
    ParcelamentoSimplesComEmpresa,
    ParcelamentoSimplesRead,
    SyncParcsnResposta,
)
from app.services.auth_service import get_current_user
from app.services.parcelamento_simples_service import ParcelamentoSimplesService

router = APIRouter(
    prefix="/parcelamentos-simples",
    tags=["parcelamentos-simples"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/empresa/{empresa_id}", response_model=list[ParcelamentoSimplesRead])
def listar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    return [
        ParcelamentoSimplesRead.model_validate(p)
        for p in ParcelamentoSimplesService(db).listar_empresa(empresa_id)
    ]


@router.post("/empresa/{empresa_id}/sync", response_model=SyncParcsnResposta)
def sync_empresa(empresa_id: int, db: Session = Depends(get_db)):
    svc = ParcelamentoSimplesService(db)
    try:
        r = svc.sync_empresa(empresa_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return SyncParcsnResposta(
        novos=r.novos, atualizados=r.atualizados,
        erros=r.erros, detalhes=r.detalhes,
    )


@router.get("/ativos", response_model=list[ParcelamentoSimplesComEmpresa])
def dashboard_ativos(db: Session = Depends(get_db)):
    out: list[ParcelamentoSimplesComEmpresa] = []
    for p in ParcelamentoSimplesService(db).dashboard_ativos():
        item = ParcelamentoSimplesComEmpresa.model_validate(p)
        if p.empresa:
            item.empresa_cnpj = p.empresa.cnpj
            item.empresa_razao_social = p.empresa.razao_social
        out.append(item)
    return out


@router.get(
    "/empresa/{empresa_id}/parcelas-disponiveis",
    response_model=list[ParcelaGeravelRead],
)
def listar_parcelas_geraveis(empresa_id: int, db: Session = Depends(get_db)):
    svc = ParcelamentoSimplesService(db)
    try:
        lista = svc.listar_parcelas_geraveis(empresa_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [ParcelaGeravelRead(**p) for p in lista]


@router.post("/empresa/{empresa_id}/emitir-das")
def emitir_das_parcela(
    empresa_id: int,
    payload: EmitirDasParcelaPayload,
    db: Session = Depends(get_db),
):
    """Emite DAS de UMA parcela (GERARDAS161). Retorna o PDF inline."""
    svc = ParcelamentoSimplesService(db)
    try:
        pdf_path = svc.emitir_das_parcela(
            empresa_id, parcela_ano_mes=payload.parcela_ano_mes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    pdf_bytes = pdf_path.read_bytes()
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{pdf_path.name}"',
        },
    )
