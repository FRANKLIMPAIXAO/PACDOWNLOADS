"""Rotas REST de guias DAS Simples Nacional.

- GET   /guias-das/empresa/{empresa_id}      lista guias da empresa
- GET   /guias-das/empresa/{empresa_id}?somente_atrasadas=true
- POST  /guias-das/empresa/{empresa_id}/sync sincroniza ano via Integra
- GET   /guias-das/atrasadas                 dashboard global de atrasadas
- POST  /guias-das/{guia_id}/atualizar       emite DARF com Selic+mora (caminho #18)
- GET   /guias-das/{guia_id}/pdf             download do PDF
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.providers.integra_contador import IntegraContadorError
from app.schemas.guia_das_schema import (
    GuiaDASComEmpresa,
    GuiaDASRead,
    SyncDASRequest,
    SyncDASResposta,
)
from app.services.auth_service import get_current_user
from app.services.guia_das_service import GuiaDASService

router = APIRouter(
    prefix="/guias-das",
    tags=["guias-das"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/empresa/{empresa_id}", response_model=list[GuiaDASRead])
def listar_empresa(
    empresa_id: int,
    somente_atrasadas: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[GuiaDASRead]:
    servico = GuiaDASService(db)
    guias = servico.listar_empresa(empresa_id, somente_atrasadas=somente_atrasadas)
    return [GuiaDASRead.model_validate(g) for g in guias]


@router.post(
    "/empresa/{empresa_id}/sync",
    response_model=SyncDASResposta,
)
def sync_empresa(
    empresa_id: int,
    payload: SyncDASRequest | None = None,
    db: Session = Depends(get_db),
) -> SyncDASResposta:
    payload = payload or SyncDASRequest()
    servico = GuiaDASService(db)
    try:
        resultado = servico.sync_empresa(empresa_id, ano=payload.ano)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return SyncDASResposta(
        novas=resultado.novas,
        atualizadas=resultado.atualizadas,
        pagas_detectadas=resultado.pagas_detectadas,
        erros=resultado.erros,
        detalhes=resultado.detalhes,
    )


@router.get("/atrasadas", response_model=list[GuiaDASComEmpresa])
def dashboard_atrasadas(db: Session = Depends(get_db)) -> list[GuiaDASComEmpresa]:
    """Dashboard global: todas guias `situacao='atrasada'`, todas empresas."""
    servico = GuiaDASService(db)
    guias = servico.dashboard_atrasadas()
    out: list[GuiaDASComEmpresa] = []
    for g in guias:
        item = GuiaDASComEmpresa.model_validate(g)
        if g.empresa:
            item.empresa_cnpj = g.empresa.cnpj
            item.empresa_razao_social = g.empresa.razao_social
        out.append(item)
    return out


@router.post("/{guia_id}/atualizar", response_model=GuiaDASRead)
def emitir_guia_atualizada(
    guia_id: int, db: Session = Depends(get_db),
) -> GuiaDASRead:
    """Caminho #18: emite DARF nova via GERARDAS12 com Selic+mora calculados."""
    servico = GuiaDASService(db)
    try:
        guia = servico.emitir_guia_atualizada(guia_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GuiaDASRead.model_validate(guia)


@router.get("/{guia_id}/pdf")
def baixar_pdf(guia_id: int, db: Session = Depends(get_db)) -> FileResponse:
    servico = GuiaDASService(db)
    guia = servico.obter(guia_id)
    if not guia or not guia.pdf_path:
        raise HTTPException(
            status_code=404,
            detail="Guia não encontrada ou PDF não emitido — chame /atualizar primeiro",
        )
    pdf_path = Path(guia.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo PDF não existe: {pdf_path}")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"DAS_{guia.periodo_apuracao}_{guia.empresa_id}.pdf",
    )
