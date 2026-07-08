"""Webhook que o PacChat chama quando o ESCRITÓRIO responde um cliente — o
PacGestão então dispara o Web Push pro celular do cliente (tipo WhatsApp).

Autenticação server-to-server pelo header `X-PAC-Token` (o MESMO das admissões /
do PacChat). NÃO é um endpoint de cliente (não usa get_current_cliente).

Fluxo: PacChat → POST /api/v1/pacchat/notificar {cnpj, corpo, autor_nome}
       → acha a empresa pelo CNPJ → clientes (ativos) com acesso a ela
       → inscrições de push deles → envia a notificação.

Diagnóstico: cada chamada recebida fica num buffer em memória (últimas 30),
visível em GET /pacchat/notificar-log?t=<token> — pra ver, do navegador, SE o
PacChat está chamando e o que aconteceu (token ok? achou empresa? quantos push?).
"""
from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Header, HTTPException
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

logger = logging.getLogger("pac.pacchat_webhook")

router = APIRouter(prefix="/pacchat", tags=["pacchat-webhook"])

# Últimas chamadas recebidas (memória; zera no restart). Diagnóstico ao vivo.
_ULTIMAS: deque[dict] = deque(maxlen=30)


class NotificarPayload(BaseModel):
    cnpj: str
    corpo: str | None = Field(default=None, max_length=500)
    autor_nome: str | None = Field(default=None, max_length=120)
    titulo: str | None = Field(default=None, max_length=120)
    # Pra push de LIGAÇÃO: tag própria ("chamada") e requer_interacao=True (a
    # notificação fica na tela até o cliente tocar e abrir o portal p/ atender).
    tag: str | None = Field(default=None, max_length=40)
    requer_interacao: bool = False


def _token_ok(recebido: str | None) -> bool:
    esperado = get_settings().pac_tarefas_webhook_token or ""
    # compare_digest evita timing attack; sem token configurado → nega.
    return bool(esperado) and bool(recebido) and hmac.compare_digest(recebido, esperado)


def _repetir_push_chamada(cnpj: str, subs_data: list[dict], titulo: str, corpo: str,
                          vezes: int = 5, intervalo: float = 4.0) -> None:
    """"Toca" a notificação de ligação VÁRIAS vezes (buzz repetido, tag=chamada +
    renotify → re-alerta o mesmo aviso), simulando um telefone tocando. PARA
    sozinho quando a chamada não está mais pendente (atendida/encerrada). Roda em
    thread daemon — não segura a resposta do webhook."""
    from app.services.pacchat_service import PacChatError, PacChatService
    subs = [SimpleNamespace(**d) for d in subs_data]
    for _ in range(vezes):
        time.sleep(intervalo)
        try:
            r = PacChatService().chamada_pendente(cnpj)
            if not r.get("chamada"):
                return  # atendeu / encerrou → para de "tocar"
        except PacChatError:
            return
        except Exception:  # noqa: BLE001 — nunca deixa a thread derrubar nada
            return
        enviar_push(subs, titulo, corpo, url="/portal", tag="chamada", require_interaction=True)


@router.post("/notificar")
def notificar(
    payload: NotificarPayload,
    x_pac_token: str | None = Header(default=None, alias="X-PAC-Token"),
    db: Session = Depends(get_db),
) -> dict:
    """Dispara Web Push pros clientes (dispositivos inscritos) da empresa do CNPJ."""
    reg: dict = {
        "em": datetime.now(timezone.utc).isoformat(),
        "cnpj_recebido": payload.cnpj,
        "token_ok": _token_ok(x_pac_token),
        "autor_nome": payload.autor_nome,
        "tem_corpo": bool(payload.corpo),
        "empresa": None, "clientes": 0, "dispositivos": 0, "enviados": 0, "resultado": "",
    }

    def _registrar(resultado: str) -> None:
        reg["resultado"] = resultado
        _ULTIMAS.appendleft(reg)

    if not reg["token_ok"]:
        _registrar("401 token inválido")
        raise HTTPException(status_code=401, detail="Token inválido.")

    cnpj = "".join(ch for ch in (payload.cnpj or "") if ch.isdigit())
    reg["cnpj_norm"] = cnpj
    if len(cnpj) != 14:
        _registrar("400 CNPJ inválido")
        raise HTTPException(status_code=400, detail="CNPJ inválido.")

    empresa = db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
    if not empresa:
        # 200 (não 404): pro PacChat não ficar reenviando por empresa que o
        # PacGestão não conhece. Só não há pra quem notificar.
        _registrar("empresa não encontrada")
        return {"ok": True, "enviados": 0, "motivo": "empresa não encontrada"}
    reg["empresa"] = empresa.razao_social

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
    reg["clientes"] = len(ids)
    if not ids:
        _registrar("sem cliente ativo")
        return {"ok": True, "enviados": 0, "motivo": "sem cliente ativo"}

    subs = list(db.scalars(select(PushSubscription).where(PushSubscription.usuario_id.in_(ids))).all())
    reg["dispositivos"] = len(subs)
    if not subs:
        _registrar("sem dispositivo inscrito")
        return {"ok": True, "enviados": 0, "motivo": "sem dispositivo inscrito"}

    titulo = (payload.titulo or f"💬 {payload.autor_nome or 'Escritório PAC'}")[:80]
    corpo = (payload.corpo or "Você recebeu uma nova mensagem no portal.")[:140]
    mortos = enviar_push(
        subs, titulo, corpo, url="/portal",
        tag=(payload.tag or "pacchat"),
        require_interaction=payload.requer_interacao,
    )

    # Limpa inscrições que morreram (404/410) pra não tentar de novo.
    if mortos:
        for s in subs:
            if s.endpoint in mortos:
                db.delete(s)
        db.commit()

    enviados = len(subs) - len(mortos)
    reg["enviados"] = enviados
    _registrar("ok")

    # Ligação (tag=chamada): "toca" repetido — repete o push a cada ~4s enquanto a
    # chamada estiver tocando (para sozinho ao atender). PacChat chama o webhook 1x.
    if (payload.tag or "") == "chamada" and enviados > 0:
        vivas = [{"endpoint": s.endpoint, "p256dh": s.p256dh, "auth": s.auth}
                 for s in subs if s.endpoint not in mortos]
        threading.Thread(
            target=_repetir_push_chamada, args=(cnpj, vivas, titulo, corpo), daemon=True,
        ).start()

    return {"ok": True, "enviados": enviados, "dispositivos": len(subs), "removidos": len(mortos)}


@router.get("/notificar-log")
def notificar_log(
    x_pac_token: str | None = Header(default=None, alias="X-PAC-Token"),
    t: str | None = None,
) -> dict:
    """Diagnóstico: últimas chamadas que o PacChat fez neste webhook. Abra no
    navegador: /api/v1/pacchat/notificar-log?t=<o mesmo token>. Se `chamadas`
    vier vazio, o PacChat NÃO está chamando (ou a URL/token está errada)."""
    if not (_token_ok(x_pac_token) or _token_ok(t)):
        raise HTTPException(status_code=401, detail="Token inválido.")
    return {"total": len(_ULTIMAS), "chamadas": list(_ULTIMAS)}
