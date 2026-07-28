"""Gestão (escritório) dos CNPJs bloqueados no portal do cliente, por empresa.

Autenticado como EQUIPE (get_current_user). O cliente/portal NÃO acessa isto —
ele só sofre o efeito (notas dos CNPJs somem no portal dele).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.empresa import Empresa
from app.models.portal_cnpj_bloqueado import PortalCnpjBloqueado
from app.services.auth_service import get_current_user

router = APIRouter(
    prefix="/portal-bloqueios", tags=["portal-bloqueios"],
    dependencies=[Depends(get_current_user)],
)


def _norm_cnpj(s: str | None) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


class BloqueioCreate(BaseModel):
    empresa_id: int
    cnpj: str = Field(min_length=11, max_length=20)  # aceita com/sem máscara
    rotulo: str | None = Field(default=None, max_length=160)


class BloqueioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    cnpj: str
    rotulo: str | None
    created_at: datetime


@router.get("", response_model=list[BloqueioRead])
def listar(empresa_id: int, db: Session = Depends(get_db)) -> list[PortalCnpjBloqueado]:
    return list(
        db.scalars(
            select(PortalCnpjBloqueado)
            .where(PortalCnpjBloqueado.empresa_id == empresa_id)
            .order_by(PortalCnpjBloqueado.created_at.desc())
        ).all()
    )


@router.post("", response_model=BloqueioRead, status_code=201)
def adicionar(payload: BloqueioCreate, db: Session = Depends(get_db)) -> PortalCnpjBloqueado:
    cnpj = _norm_cnpj(payload.cnpj)
    if len(cnpj) != 14:
        raise HTTPException(status_code=400, detail="CNPJ inválido — precisa de 14 dígitos.")
    if not db.get(Empresa, payload.empresa_id):
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    ja = db.scalar(
        select(PortalCnpjBloqueado).where(
            PortalCnpjBloqueado.empresa_id == payload.empresa_id,
            PortalCnpjBloqueado.cnpj == cnpj,
        )
    )
    if ja:  # idempotente — já bloqueado
        return ja
    b = PortalCnpjBloqueado(
        empresa_id=payload.empresa_id, cnpj=cnpj,
        rotulo=(payload.rotulo or "").strip() or None,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/{bloqueio_id}")
def remover(bloqueio_id: int, db: Session = Depends(get_db)) -> dict:
    b = db.get(PortalCnpjBloqueado, bloqueio_id)
    if b:
        db.delete(b)
        db.commit()
    return {"ok": True}
