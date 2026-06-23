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
import json
import logging
import threading
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models.conector_email_execucao import ConectorEmailExecucao
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


def _registrar_execucao(db: Session, origem: str, payload: dict | None, erro_msg: str | None) -> None:
    """Grava a execução no histórico (pro relatório). Nunca derruba a rodada."""
    try:
        db.add(ConectorEmailExecucao(
            origem=origem,
            emails_lidos=(payload or {}).get("emails_lidos", 0),
            anexos=(payload or {}).get("anexos", 0),
            persistidos=(payload or {}).get("persistidos", 0),
            duplicados=(payload or {}).get("duplicados", 0),
            nao_cadastrada=(payload or {}).get("nao_cadastrada", 0),
            erros=(payload or {}).get("erros", 0),
            remetentes=json.dumps((payload or {}).get("remetentes", []), ensure_ascii=False),
            detalhe_empresas=json.dumps((payload or {}).get("empresas", []), ensure_ascii=False),
            erro_msg=erro_msg,
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Falha ao registrar execução do conector de e-mail")


def _rodar(job_id: str | None, origem: str) -> None:
    """Lê a caixa numa thread própria, com sessão de banco própria. Persiste a
    execução no histórico (relatório), seja sucesso ou falha."""
    if not _RODANDO.is_set():
        _RODANDO.set()
    db = SessionLocal()
    try:
        res = EmailInboxService(db).processar()
        payload = res.to_dict()
        logger.info(
            "conector-email OK (%s): emails=%s persistidos=%s nao_cadastrada=%s erros=%s",
            origem, payload["emails_lidos"], payload["persistidos"],
            payload["nao_cadastrada"], payload["erros"],
        )
        _registrar_execucao(db, origem, payload, None)
        if job_id:
            with _LOCK:
                _JOBS[job_id] = {"status": "concluido", "resultado": payload}
    except Exception as exc:  # noqa: BLE001
        logger.exception("conector-email falhou")
        _registrar_execucao(db, origem, None, str(exc)[:480])
        if job_id:
            with _LOCK:
                _JOBS[job_id] = {"status": "erro", "erro": str(exc)[:300]}
    finally:
        # Rede de segurança: a cada tick do cron, reenvia admissões que não
        # chegaram no PAC TAREFAS (ex.: Supabase fora no momento do envio). Roda
        # SEMPRE (mesmo se o e-mail falhou) e nunca derruba o cron.
        try:
            from app.services.admissao_service import AdmissaoService
            r = AdmissaoService(db).reenviar_pendentes(limite=30)
            if r.get("tentadas"):
                logger.info("conector-email: reenvio admissoes pendentes %s", r)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao reenviar admissoes pendentes")
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
    threading.Thread(target=_rodar, args=(job_id, "manual"), daemon=True).start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def status(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Leitura não encontrada (pode ter reiniciado).")
        return job


@router.get("/execucoes")
def execucoes(limit: int = 30, db: Session = Depends(get_db)) -> dict:
    """Histórico das leituras da caixa (relatório): quando rodou, de quais empresas
    entraram notas e se teve erro. Mais recente primeiro."""
    limit = max(1, min(limit, 200))
    linhas = list(db.scalars(
        select(ConectorEmailExecucao)
        .order_by(desc(ConectorEmailExecucao.criado_em))
        .limit(limit)
    ).all())

    def _json(txt: str | None) -> list:
        if not txt:
            return []
        try:
            return json.loads(txt)
        except Exception:  # noqa: BLE001
            return []

    return {
        "rodando": _RODANDO.is_set(),
        "execucoes": [
            {
                "id": e.id,
                "criado_em": e.criado_em.isoformat() if e.criado_em else None,
                "origem": e.origem,
                "emails_lidos": e.emails_lidos,
                "anexos": e.anexos,
                "persistidos": e.persistidos,
                "duplicados": e.duplicados,
                "nao_cadastrada": e.nao_cadastrada,
                "erros": e.erros,
                "empresas": _json(e.detalhe_empresas),
                "remetentes": _json(e.remetentes),
                "erro_msg": e.erro_msg,
            }
            for e in linhas
        ],
    }


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
    threading.Thread(target=_rodar, args=(None, "cron"), daemon=True).start()
    return {"ok": True, "iniciado": True}
