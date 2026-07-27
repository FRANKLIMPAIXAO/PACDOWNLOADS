"""PAC Indica — programa de indicação.

- `POST /portal/indicacao`  PÚBLICO (sem auth): o formulário na tela de login do
  portal envia a indicação. Protegido por honeypot + throttle por IP + validação.
- `GET  /pac-indica`        ADMIN/equipe: lista as indicações recebidas.
- `PATCH /pac-indica/{id}`  ADMIN/equipe: muda o status (nova → em_contato → …).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.indicacao_pac import IndicacaoPac
from app.services.auth_service import get_current_user

# Router PÚBLICO (sem dependência de auth) — formulário da tela de login.
router_public = APIRouter(prefix="/portal", tags=["pac-indica"])
# Router da EQUIPE (autenticado) — gestão das indicações.
router = APIRouter(
    prefix="/pac-indica", tags=["pac-indica"], dependencies=[Depends(get_current_user)],
)

STATUS_VALIDOS = {"nova", "em_contato", "convertida", "descartada"}

# Throttle simples em memória p/ o endpoint PÚBLICO (zera no restart). Máx N
# envios por IP por janela — barra flood de bot sem precisar de Redis.
_ENVIOS_POR_IP: dict[str, deque] = defaultdict(deque)
_LIMITE_IP = 5
_JANELA_S = 3600


class IndicacaoCreate(BaseModel):
    nome_indicador: str = Field(min_length=2, max_length=120)
    contato_indicador: str = Field(min_length=5, max_length=120)
    empresa_indicador: str | None = Field(default=None, max_length=160)
    nome_indicado: str = Field(min_length=2, max_length=120)
    contato_indicado: str = Field(min_length=5, max_length=120)
    observacao: str | None = Field(default=None, max_length=1000)
    # HONEYPOT: campo escondido no formulário. Humano deixa vazio; bot preenche
    # tudo → descartamos silenciosamente (responde ok, não grava).
    website: str | None = Field(default=None, max_length=200)


class IndicacaoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome_indicador: str
    contato_indicador: str
    empresa_indicador: str | None
    nome_indicado: str
    contato_indicado: str
    observacao: str | None
    status: str
    origem: str
    created_at: datetime


@router_public.post("/indicacao", status_code=201)
def criar_indicacao(
    payload: IndicacaoCreate, request: Request, db: Session = Depends(get_db),
) -> dict:
    """PÚBLICO. Recebe uma indicação do programa PAC Indica."""
    # Honeypot: preenchido = bot. Responde ok (não denuncia a armadilha) e ignora.
    if payload.website:
        return {"ok": True}

    ip = request.client.host if request.client else "?"
    agora = time.time()
    dq = _ENVIOS_POR_IP[ip]
    while dq and agora - dq[0] > _JANELA_S:
        dq.popleft()
    if len(dq) >= _LIMITE_IP:
        raise HTTPException(
            status_code=429,
            detail="Recebemos muitas indicações deste dispositivo agora há pouco. Tente novamente mais tarde.",
        )
    dq.append(agora)

    ind = IndicacaoPac(
        nome_indicador=payload.nome_indicador.strip(),
        contato_indicador=payload.contato_indicador.strip(),
        empresa_indicador=(payload.empresa_indicador or "").strip() or None,
        nome_indicado=payload.nome_indicado.strip(),
        contato_indicado=payload.contato_indicado.strip(),
        observacao=(payload.observacao or "").strip() or None,
        origem="portal_login",
        ip=ip,
    )
    db.add(ind)
    db.commit()
    return {"ok": True}


@router.get("/contagem")
def contar_indicacoes(db: Session = Depends(get_db)) -> dict:
    """Contador leve p/ o badge no menu — quantas indicações estão 'nova'."""
    novas = db.scalar(
        select(func.count()).select_from(IndicacaoPac).where(IndicacaoPac.status == "nova")
    )
    return {"novas": int(novas or 0)}


@router.get("", response_model=list[IndicacaoRead])
def listar_indicacoes(
    status: str | None = None, db: Session = Depends(get_db),
) -> list[IndicacaoPac]:
    stmt = select(IndicacaoPac).order_by(IndicacaoPac.created_at.desc())
    if status in STATUS_VALIDOS:
        stmt = stmt.where(IndicacaoPac.status == status)
    return list(db.scalars(stmt.limit(500)).all())


class StatusUpdate(BaseModel):
    status: str


@router.patch("/{indicacao_id}", response_model=IndicacaoRead)
def atualizar_status(
    indicacao_id: int, payload: StatusUpdate, db: Session = Depends(get_db),
) -> IndicacaoPac:
    if payload.status not in STATUS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Status inválido: {payload.status!r}")
    ind = db.get(IndicacaoPac, indicacao_id)
    if not ind:
        raise HTTPException(status_code=404, detail="Indicação não encontrada.")
    ind.status = payload.status
    db.commit()
    db.refresh(ind)
    return ind
