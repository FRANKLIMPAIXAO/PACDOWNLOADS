"""Conector de SAÍDAS por e-mail — rotas.

- POST /conector-email/processar  (escritório, JWT): dispara a leitura da caixa em
  BACKGROUND e devolve job_id; GET /conector-email/status/{job_id} faz o polling.
  IMAP + parse de muitos XMLs pode passar do timeout do Traefik (~60s), por isso
  roda em thread (igual upload do portal / SITFIS).
- POST /conector-email/cron  (SEM JWT, header X-Cron-Token): um cron EXTERNO dispara
  periodicamente; também roda em thread e volta na hora.
- GET  /conector-email/config: diz se o conector está ligado (sem expor segredo).
"""
from __future__ import annotations

import hmac
import logging
import threading
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.services.auth_service import get_current_user
from app.services.email_inbox_service import EmailInboxService

logger = logging.getLogger("pac.conector_email")

router = APIRouter(
    prefix="/conector-email", tags=["conector-email"],
    dependencies=[Depends(get_current_user)],
)
router_cron = APIRouter(prefix="/conector-email", tags=["conector-email-cron"])

# Jobs em memória (eager, --workers 1), igual ao upload do portal.
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
# Trava global: NÃO deixa duas leituras simultâneas (a mesma caixa) — evita
# processar o mesmo e-mail duas vezes numa corrida.
_RODANDO = threading.Event()


def _rodar(job_id: str | None) -> None:
    """Lê a caixa numa thread própria, com sessão de banco própria."""
    if not _RODANDO.is_set():
        _RODANDO.set()
    db = SessionLocal()
    try:
        res = EmailInboxService(db).processar()
        payload = res.to_dict()
        logger.info(
            "conector-email OK: emails=%s persistidos=%s nao_cadastrada=%s erros=%s",
            payload["emails_lidos"], payload["persistidos"],
            payload["nao_cadastrada"], payload["erros"],
        )
        if job_id:
            with _LOCK:
                _JOBS[job_id] = {"status": "concluido", "resultado": payload}
    except Exception as exc:  # noqa: BLE001
        logger.exception("conector-email falhou")
        if job_id:
            with _LOCK:
                _JOBS[job_id] = {"status": "erro", "erro": str(exc)[:300]}
    finally:
        db.close()
        _RODANDO.clear()


@router.get("/config")
def config() -> dict:
    s = get_settings()
    return {"ativo": s.conector_email_ativo, "caixa": s.imap_user or None}


@router.post("/processar")
def processar() -> dict:
    s = get_settings()
    if not s.conector_email_ativo:
        raise HTTPException(
            status_code=503,
            detail="Conector de e-mail desligado: configure IMAP_HOST/IMAP_USER/IMAP_PASSWORD.",
        )
    if _RODANDO.is_set():
        raise HTTPException(status_code=409, detail="Já há uma leitura em andamento.")
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {"status": "rodando"}
    threading.Thread(target=_rodar, args=(job_id,), daemon=True).start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def status(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Leitura não encontrada (pode ter reiniciado).")
        return job


@router_cron.post("/cron")
def cron(x_cron_token: str = Header(default="")) -> dict:
    """Disparo do cron EXTERNO. Protegido por X-Cron-Token (env CONECTOR_EMAIL_TOKEN)."""
    s = get_settings()
    esperado = s.conector_email_token
    if not esperado:
        raise HTTPException(status_code=503, detail="CONECTOR_EMAIL_TOKEN não configurado no servidor.")
    if not x_cron_token or not hmac.compare_digest(x_cron_token, esperado):
        raise HTTPException(status_code=401, detail="Token do cron inválido.")
    if not s.conector_email_ativo:
        raise HTTPException(status_code=503, detail="Conector de e-mail desligado (IMAP não configurado).")
    if _RODANDO.is_set():
        return {"ok": True, "ja_rodando": True}
    threading.Thread(target=_rodar, args=(None,), daemon=True).start()
    return {"ok": True, "iniciado": True}
