"""Rotas REST de Guias FGTS Digital via Infosimples (modo Procurador)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.guia_fgts_schema import (
    EmitirFgtsPayload,
    EmitirFgtsResposta,
    GuiaFgtsComEmpresa,
    GuiaFgtsRead,
    HistoricoFgtsResposta,
)
from app.services.auth_service import get_current_user
from app.services.guia_fgts_service import GuiaFgtsService

router = APIRouter(
    prefix="/guias-fgts",
    tags=["guias-fgts"],
    dependencies=[Depends(get_current_user)],
)


def _to_read(g) -> GuiaFgtsRead:
    return GuiaFgtsRead(
        id=g.id,
        empresa_id=g.empresa_id,
        periodo=g.periodo,
        competencia_formatada=g.competencia_formatada,
        data_vencimento=g.data_vencimento,
        valor_total=g.valor_total,
        valor_mensal=g.valor_mensal,
        valor_rescisorio=g.valor_rescisorio,
        valor_compensatorio=g.valor_compensatorio,
        valor_encargos=g.valor_encargos,
        quantidade_trabalhadores=g.quantidade_trabalhadores,
        pdf_url_infosimples=g.pdf_url_infosimples,
        pdf_path=g.pdf_path,
        situacao=g.situacao,
        status_calculado=g.status_calculado,
        dias_para_vencer=g.dias_para_vencer,
        data_pagamento=g.data_pagamento,
        emitida_em=g.emitida_em,
    )


@router.get("/empresa/{empresa_id}", response_model=list[GuiaFgtsRead])
def listar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    return [_to_read(g) for g in GuiaFgtsService(db).listar_empresa(empresa_id)]


@router.get("/pendentes", response_model=list[GuiaFgtsComEmpresa])
def listar_pendentes(db: Session = Depends(get_db)):
    """Todas as guias FGTS emitidas e ainda não pagas — dashboard global."""
    out: list[GuiaFgtsComEmpresa] = []
    for g in GuiaFgtsService(db).listar_todas_pendentes():
        base = _to_read(g).model_dump()
        item = GuiaFgtsComEmpresa(**base)
        if g.empresa:
            item.empresa_cnpj = g.empresa.cnpj
            item.empresa_razao_social = g.empresa.razao_social
        out.append(item)
    return out


@router.post(
    "/empresa/{empresa_id}/emitir", response_model=EmitirFgtsResposta,
)
def emitir(
    empresa_id: int,
    payload: EmitirFgtsPayload,
    db: Session = Depends(get_db),
):
    """Emite Guia Rápida FGTS Digital pra (empresa, periodo).

    Modo Procurador — cert do escritório no painel Infosimples + CNPJ da empresa.
    Custa 1 consulta Infosimples (~R$ 0,20 na faixa 1-500/mês).
    """
    svc = GuiaFgtsService(db)
    r = svc.emitir_mensal(empresa_id, periodo=payload.periodo)
    return EmitirFgtsResposta(
        sucesso=r.sucesso,
        guia=_to_read(r.guia) if r.guia else None,
        erro=r.erro,
    )


@router.get(
    "/empresa/{empresa_id}/historico-infosimples",
    response_model=HistoricoFgtsResposta,
)
def historico_infosimples(
    empresa_id: int,
    periodo: str | None = Query(default=None, pattern=r"^\d{6}$"),
    pagina: int = Query(default=1, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Consulta histórico de guias FGTS direto no Infosimples (custa 1 consulta).

    Use pra reconciliar o que tá no PAC com o que tá no portal FGTS Digital.
    """
    svc = GuiaFgtsService(db)
    try:
        return svc.consultar_historico(
            empresa_id, periodo=periodo, pagina=pagina,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{guia_id}/marcar-paga", response_model=GuiaFgtsRead)
def marcar_paga(
    guia_id: int,
    data_pagamento: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    svc = GuiaFgtsService(db)
    try:
        g = svc.marcar_paga(guia_id, data_pagamento=data_pagamento)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _to_read(g)


@router.get("/{guia_id}/pdf")
def baixar_pdf(guia_id: int, db: Session = Depends(get_db)):
    from app.models.guia_fgts import GuiaFgts
    g = db.get(GuiaFgts, guia_id)
    if not g or not g.pdf_path:
        raise HTTPException(status_code=404, detail="PDF não disponível")
    p = Path(g.pdf_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="PDF removido do storage")
    return FileResponse(path=str(p), filename=p.name, media_type="application/pdf")
