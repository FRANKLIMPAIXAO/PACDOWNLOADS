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
    # Recíproco: se o CNPJ bloqueado for uma EMPRESA nossa (tem portal), esconde
    # também no portal DELA as notas desta empresa — some nos dois lados de uma vez.
    reciproco: bool = False


class BloqueioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empresa_id: int
    cnpj: str
    rotulo: str | None
    created_at: datetime


class BloqueioCreateResp(BaseModel):
    bloqueio: BloqueioRead
    # razão social da outra empresa quando o recíproco foi criado (senão None)
    reciproco_criado_para: str | None = None


def _upsert_bloqueio(db: Session, empresa_id: int, cnpj: str, rotulo: str | None) -> PortalCnpjBloqueado:
    """Cria o bloqueio se ainda não existir (idempotente)."""
    ja = db.scalar(
        select(PortalCnpjBloqueado).where(
            PortalCnpjBloqueado.empresa_id == empresa_id,
            PortalCnpjBloqueado.cnpj == cnpj,
        )
    )
    if ja:
        return ja
    b = PortalCnpjBloqueado(empresa_id=empresa_id, cnpj=cnpj, rotulo=(rotulo or "").strip() or None)
    db.add(b)
    db.flush()
    return b


@router.get("", response_model=list[BloqueioRead])
def listar(empresa_id: int, db: Session = Depends(get_db)) -> list[PortalCnpjBloqueado]:
    return list(
        db.scalars(
            select(PortalCnpjBloqueado)
            .where(PortalCnpjBloqueado.empresa_id == empresa_id)
            .order_by(PortalCnpjBloqueado.created_at.desc())
        ).all()
    )


@router.post("", response_model=BloqueioCreateResp, status_code=201)
def adicionar(payload: BloqueioCreate, db: Session = Depends(get_db)) -> BloqueioCreateResp:
    cnpj = _norm_cnpj(payload.cnpj)
    if len(cnpj) != 14:
        raise HTTPException(status_code=400, detail="CNPJ inválido — precisa de 14 dígitos.")
    empresa = db.get(Empresa, payload.empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    b = _upsert_bloqueio(db, payload.empresa_id, cnpj, payload.rotulo)

    # Recíproco: se o CNPJ bloqueado for uma EMPRESA nossa, esconde também no
    # portal DELA as notas desta empresa (o mesmo login trocava de empresa e via).
    reciproco_para: str | None = None
    if payload.reciproco:
        outra = db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
        if outra and outra.id != empresa.id:
            _upsert_bloqueio(
                db, outra.id, _norm_cnpj(empresa.cnpj),
                empresa.razao_social or "Empresa",
            )
            reciproco_para = outra.razao_social

    db.commit()
    db.refresh(b)
    return BloqueioCreateResp(bloqueio=BloqueioRead.model_validate(b), reciproco_criado_para=reciproco_para)


@router.delete("/{bloqueio_id}")
def remover(bloqueio_id: int, db: Session = Depends(get_db)) -> dict:
    b = db.get(PortalCnpjBloqueado, bloqueio_id)
    if b:
        db.delete(b)
        db.commit()
    return {"ok": True}
