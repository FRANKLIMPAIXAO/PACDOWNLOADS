"""Rotas REST de Guias DCTFWeb."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.providers.integra_contador import IntegraContadorError
from app.schemas.guia_dctfweb_schema import (
    EmitirGuiaDctfwebPayload,
    GuiaDctfwebComEmpresa,
    GuiaDctfwebRead,
)
from app.services.auth_service import get_current_user
from app.services.guia_dctfweb_service import GuiaDctfwebService

router = APIRouter(
    prefix="/guias-dctfweb",
    tags=["guias-dctfweb"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/empresa/{empresa_id}", response_model=list[GuiaDctfwebRead])
def listar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    return [
        GuiaDctfwebRead.model_validate(g)
        for g in GuiaDctfwebService(db).listar_empresa(empresa_id)
    ]


@router.get("/recentes", response_model=list[GuiaDctfwebComEmpresa])
def listar_recentes(db: Session = Depends(get_db)):
    out: list[GuiaDctfwebComEmpresa] = []
    for g in GuiaDctfwebService(db).listar_todas():
        item = GuiaDctfwebComEmpresa.model_validate(g)
        if g.empresa:
            item.empresa_cnpj = g.empresa.cnpj
            item.empresa_razao_social = g.empresa.razao_social
        out.append(item)
    return out


@router.post(
    "/empresa/{empresa_id}/emitir-ativa", response_model=GuiaDctfwebRead,
)
def emitir_ativa(
    empresa_id: int,
    payload: EmitirGuiaDctfwebPayload,
    db: Session = Depends(get_db),
):
    """GERARGUIA31: declaração já transmitida (situação ATIVA)."""
    svc = GuiaDctfwebService(db)
    try:
        g = svc.emitir_guia_ativa(
            empresa_id,
            categoria=payload.categoria,
            ano_pa=payload.ano_pa,
            mes_pa=payload.mes_pa,
            dia_pa=payload.dia_pa,
            cno_afericao=payload.cno_afericao,
            num_proc_reclamatoria=payload.num_proc_reclamatoria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GuiaDctfwebRead.model_validate(g)


@router.post(
    "/empresa/{empresa_id}/emitir-andamento", response_model=GuiaDctfwebRead,
)
def emitir_andamento(
    empresa_id: int,
    payload: EmitirGuiaDctfwebPayload,
    db: Session = Depends(get_db),
):
    """GERARGUIAANDAMENTO313: declaração em apuração (ANDAMENTO)."""
    svc = GuiaDctfwebService(db)
    try:
        g = svc.emitir_guia_andamento(
            empresa_id,
            categoria=payload.categoria,
            ano_pa=payload.ano_pa,
            mes_pa=payload.mes_pa,
            dia_pa=payload.dia_pa,
            cno_afericao=payload.cno_afericao,
            num_proc_reclamatoria=payload.num_proc_reclamatoria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GuiaDctfwebRead.model_validate(g)


@router.get("/{guia_id}/pdf")
def baixar_pdf(guia_id: int, db: Session = Depends(get_db)):
    g = GuiaDctfwebService(db).obter(guia_id)
    if not g or not g.pdf_path:
        raise HTTPException(status_code=404, detail="Guia DCTFWeb não encontrada")
    pdf_path = Path(g.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF não existe no storage")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"DCTFWeb_{g.origem}_{g.categoria}_{g.periodo_formatado.replace('/', '_')}.pdf",
    )
