"""Cobranças do PORTAL — visão do ESCRITÓRIO (área protegida por get_current_user).

Lista os recálculos de DAS que os clientes dispararam e que geram cobrança
(valor > 0; o 1º de cada guia é grátis e não aparece aqui por padrão). O
escritório vê o total a receber por empresa e marca como paga ao faturar.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cobranca_portal import CobrancaPortal
from app.models.empresa import Empresa
from app.services.auth_service import get_current_user

router = APIRouter(
    prefix="/cobrancas",
    tags=["cobrancas"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def listar_cobrancas(
    paga: bool | None = None,
    empresa_id: int | None = None,
    incluir_gratis: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Lista as cobranças + resumo (a receber / recebido / pendentes).

    Por padrão SÓ as cobráveis (valor > 0). `paga` filtra status;
    `empresa_id` filtra a empresa; `incluir_gratis=true` traz os recálculos
    grátis (valor 0) também (auditoria)."""
    conds = []
    if not incluir_gratis:
        conds.append(CobrancaPortal.valor > 0)
    if paga is not None:
        conds.append(CobrancaPortal.paga == paga)
    if empresa_id is not None:
        conds.append(CobrancaPortal.empresa_id == empresa_id)

    rows = db.execute(
        select(CobrancaPortal, Empresa.razao_social, Empresa.cnpj)
        .join(Empresa, Empresa.id == CobrancaPortal.empresa_id, isouter=True)
        .where(*conds)
        .order_by(CobrancaPortal.paga.asc(), CobrancaPortal.criada_em.desc())
        .limit(2000)
    ).all()
    cobrancas = [
        {
            "id": c.id,
            "empresa_id": c.empresa_id,
            "empresa_razao_social": razao,
            "empresa_cnpj": cnpj,
            "competencia": c.competencia,
            "tipo": c.tipo,
            "valor": float(c.valor or 0),
            "descricao": c.descricao,
            "paga": bool(c.paga),
            "criada_em": c.criada_em.isoformat() if c.criada_em else None,
        }
        for (c, razao, cnpj) in rows
    ]

    # Resumo global (independe dos filtros de status/empresa): cobráveis abertas
    # somam "a receber"; pagas somam "recebido".
    a_receber = db.scalar(
        select(func.coalesce(func.sum(CobrancaPortal.valor), 0)).where(
            CobrancaPortal.valor > 0, CobrancaPortal.paga.is_(False),
        )
    ) or 0
    recebido = db.scalar(
        select(func.coalesce(func.sum(CobrancaPortal.valor), 0)).where(
            CobrancaPortal.valor > 0, CobrancaPortal.paga.is_(True),
        )
    ) or 0
    pendentes = db.scalar(
        select(func.count(CobrancaPortal.id)).where(
            CobrancaPortal.valor > 0, CobrancaPortal.paga.is_(False),
        )
    ) or 0
    return {
        "cobrancas": cobrancas,
        "resumo": {
            "a_receber": float(a_receber),
            "recebido": float(recebido),
            "pendentes": int(pendentes),
        },
    }


@router.post("/{cobranca_id}/marcar-paga")
def marcar_paga(
    cobranca_id: int,
    paga: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    """Marca a cobrança como paga (ou reabre com paga=false)."""
    c = db.get(CobrancaPortal, cobranca_id)
    if not c:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada.")
    c.paga = paga
    db.commit()
    return {"ok": True, "id": c.id, "paga": c.paga}
