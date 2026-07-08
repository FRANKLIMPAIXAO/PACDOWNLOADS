"""Webhook que o PacChat chama quando o ESCRITÓRIO responde um cliente — o
PacGestão então dispara o Web Push pro celular do cliente (tipo WhatsApp).

Autenticação server-to-server pelo header `X-PAC-Token` (o MESMO das admissões /
do PacChat). NÃO é um endpoint de cliente (não usa get_current_cliente).

Fluxo: PacChat → POST /api/v1/pacchat/notificar {cnpj, corpo, autor_nome}
       → acha a empresa pelo CNPJ → clientes (ativos) com acesso a ela
       → inscrições de push deles → envia a notificação.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.cliente_empresa import ClienteEmpresa
from app.models.empresa import Empresa
from app.models.push_subscription import PushSubscription
from app.models.usuario import Usuario
from app.services.push_service import enviar_push

from fastapi import Depends

logger = logging.getLogger("pac.pacchat_webhook")

router = APIRouter(prefix="/pacchat", tags=["pacchat-webhook"])


class NotificarPayload(BaseModel):
    cnpj: str
    corpo: str | None = Field(default=None, max_length=500)
    autor_nome: str | None = Field(default=None, max_length=120)
    titulo: str | None = Field(default=None, max_length=120)


def _token_ok(recebido: str | None) -> bool:
    esperado = get_settings().pac_tarefas_webhook_token or ""
    # compare_digest evita timing attack; sem token configurado → nega.
    return bool(esperado) and bool(recebido) and hmac.compare_digest(recebido, esperado)


@router.post("/notificar")
def notificar(
    payload: NotificarPayload,
    x_pac_token: str | None = Header(default=None, alias="X-PAC-Token"),
    db: Session = Depends(get_db),
) -> dict:
    """Dispara Web Push pros clientes (dispositivos inscritos) da empresa do CNPJ."""
    if not _token_ok(x_pac_token):
        raise HTTPException(status_code=401, detail="Token inválido.")

    cnpj = "".join(ch for ch in (payload.cnpj or "") if ch.isdigit())
    if len(cnpj) != 14:
        raise HTTPException(status_code=400, detail="CNPJ inválido.")
    empresa = db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
    if not empresa:
        # 200 (não 404): pro PacChat não ficar reenviando por empresa que o
        # PacGestão não conhece. Só não há pra quem notificar.
        return {"ok": True, "enviados": 0, "motivo": "empresa não encontrada"}

    # Clientes (ATIVOS) com acesso à empresa: primária ∪ vinculadas (multi-empresa).
    ids: set[int] = set()
    for uid in db.scalars(
        select(Usuario.id).where(Usuario.is_cliente.is_(True), Usuario.empresa_id == empresa.id)
    ).all():
        ids.add(uid)
    for uid in db.scalars(
        select(ClienteEmpresa.usuario_id).where(ClienteEmpresa.empresa_id == empresa.id)
    ).all():
        ids.add(uid)
    if ids:
        ids = set(db.scalars(select(Usuario.id).where(Usuario.id.in_(ids), Usuario.ativo.is_(True))).all())
    if not ids:
        return {"ok": True, "enviados": 0, "motivo": "sem cliente ativo"}

    subs = list(db.scalars(select(PushSubscription).where(PushSubscription.usuario_id.in_(ids))).all())
    if not subs:
        return {"ok": True, "enviados": 0, "motivo": "sem dispositivo inscrito"}

    titulo = (payload.titulo or f"💬 {payload.autor_nome or 'Escritório PAC'}")[:80]
    corpo = (payload.corpo or "Você recebeu uma nova mensagem no portal.")[:140]
    mortos = enviar_push(subs, titulo, corpo, url="/portal")

    # Limpa inscrições que morreram (404/410) pra não tentar de novo.
    if mortos:
        for s in subs:
            if s.endpoint in mortos:
                db.delete(s)
        db.commit()

    return {"ok": True, "enviados": len(subs) - len(mortos), "dispositivos": len(subs), "removidos": len(mortos)}
