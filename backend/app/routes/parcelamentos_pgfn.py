"""Rotas REST de Parcelamentos PGFN (Dívida Ativa).

PGFN não tem API automatizada disponível (sem produto Infosimples / Serpro).
Por enquanto: **CADASTRO MANUAL** via UI. CRUD simples:
- GET  /parcelamentos-pgfn/empresa/{id} → lista da empresa
- GET  /parcelamentos-pgfn/ativos → dashboard global
- POST /parcelamentos-pgfn/empresa/{id} → cria
- PUT  /parcelamentos-pgfn/{id} → atualiza
- DELETE /parcelamentos-pgfn/{id} → remove
- POST /parcelamentos-pgfn/{id}/baixar → marca como pago/baixado (mantém histórico)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.parcelamento_pgfn_schema import (
    ParcelamentoPgfnComEmpresa,
    ParcelamentoPgfnRead,
)
from app.services.auth_service import get_current_user
from app.services.parcelamento_pgfn_service import (
    ParcelamentoPgfnPayload,
    ParcelamentoPgfnService,
)

router = APIRouter(
    prefix="/parcelamentos-pgfn",
    tags=["parcelamentos-pgfn"],
    dependencies=[Depends(get_current_user)],
)


class ParcelamentoPgfnPayloadRequest(BaseModel):
    """Payload pra criar/atualizar parcelamento PGFN manualmente."""
    model_config = ConfigDict(extra="forbid")

    numero: str = Field(..., min_length=1, max_length=40)
    modalidade: str = Field(default="Parcelamento Ordinário", max_length=80)
    data_pedido: date | None = None
    situacao: str = Field(default="Ativo", max_length=64)
    valor_total: Decimal | None = None
    valor_total_pago: Decimal | None = None
    quantidade_parcelas: int | None = Field(default=None, ge=1, le=999)
    parcelas_pagas: int | None = Field(default=None, ge=0, le=999)

    def to_service(self) -> ParcelamentoPgfnPayload:
        return ParcelamentoPgfnPayload(
            numero=self.numero,
            modalidade=self.modalidade,
            data_pedido=self.data_pedido,
            situacao=self.situacao,
            valor_total=self.valor_total,
            valor_total_pago=self.valor_total_pago,
            quantidade_parcelas=self.quantidade_parcelas,
            parcelas_pagas=self.parcelas_pagas,
        )


@router.get("/empresa/{empresa_id}", response_model=list[ParcelamentoPgfnRead])
def listar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    return [
        ParcelamentoPgfnRead.model_validate(p)
        for p in ParcelamentoPgfnService(db).listar_empresa(empresa_id)
    ]


@router.get("/ativos", response_model=list[ParcelamentoPgfnComEmpresa])
def listar_todos_ativos(db: Session = Depends(get_db)):
    """Todos os parcelamentos PGFN ativos no PAC (todas empresas) — dashboard."""
    out: list[ParcelamentoPgfnComEmpresa] = []
    for p in ParcelamentoPgfnService(db).listar_todos_ativos():
        item = ParcelamentoPgfnComEmpresa.model_validate(p)
        if p.empresa:
            item.empresa_cnpj = p.empresa.cnpj
            item.empresa_razao_social = p.empresa.razao_social
        out.append(item)
    return out


@router.post(
    "/empresa/{empresa_id}",
    response_model=ParcelamentoPgfnRead,
    status_code=status.HTTP_201_CREATED,
)
def criar(
    empresa_id: int,
    payload: ParcelamentoPgfnPayloadRequest,
    db: Session = Depends(get_db),
):
    svc = ParcelamentoPgfnService(db)
    try:
        p = svc.criar(empresa_id, payload.to_service())
    except ValueError as exc:
        # 404 se empresa não existe, 409 se número duplicado
        if "já tem" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))
    return ParcelamentoPgfnRead.model_validate(p)


@router.put("/{parcelamento_id}", response_model=ParcelamentoPgfnRead)
def atualizar(
    parcelamento_id: int,
    payload: ParcelamentoPgfnPayloadRequest,
    db: Session = Depends(get_db),
):
    svc = ParcelamentoPgfnService(db)
    try:
        p = svc.atualizar(parcelamento_id, payload.to_service())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ParcelamentoPgfnRead.model_validate(p)


@router.delete("/{parcelamento_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar(parcelamento_id: int, db: Session = Depends(get_db)):
    svc = ParcelamentoPgfnService(db)
    try:
        svc.deletar(parcelamento_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{parcelamento_id}/baixar", response_model=ParcelamentoPgfnRead)
def marcar_baixado(parcelamento_id: int, db: Session = Depends(get_db)):
    """Marca parcelamento como 'nao_listado_mais' (pago/baixado)."""
    svc = ParcelamentoPgfnService(db)
    try:
        p = svc.marcar_baixado(parcelamento_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ParcelamentoPgfnRead.model_validate(p)
