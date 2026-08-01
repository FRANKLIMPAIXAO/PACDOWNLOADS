"""Rotas da busca de NFS-e pelo ADN (Ambiente de Dados Nacional)."""
from __future__ import annotations

import hmac
import logging
import os
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.nfse_service import NFSeService

logger = logging.getLogger("pac.nfse_cron")

router = APIRouter(
    prefix="/nfse-adn", tags=["nfse-adn"], dependencies=[Depends(get_current_user)],
)

# Router SEM login — chamado por um cron EXTERNO (token no header). Em produção
# NÃO roda Celery beat (só uvicorn), então a automação é cron externo batendo aqui.
router_cron = APIRouter(prefix="/nfse-adn", tags=["nfse-adn-cron"])


# Estado do cron em memória. O trabalho roda em THREAD e a requisição responde
# na hora — o cron-job.org recebeu 502 porque o Traefik CORTA em ~60s e uma única
# empresa com atraso grande estourava esse tempo sozinha. Respondendo rápido, o
# proxy nunca corta e a sincronização pode demorar o quanto precisar.
_CRON: dict = {"rodando": False, "iniciado_em": None, "ultimo": None}


def _rodar_cron_nfse(chunk: int) -> None:
    """Roda a sincronização FORA da requisição. Sessão de banco PRÓPRIA — a do
    request é fechada assim que a resposta sai."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        resultado = NFSeService(db).cron_sincronizar(chunk=chunk, budget_s=240, max_lotes=12)
        try:
            from app.services.cron_log import registrar_cron
            registrar_cron(db, "nfse", resultado)
        except Exception:  # noqa: BLE001 — log nunca derruba o cron
            db.rollback()
        _CRON["ultimo"] = {"em": datetime.now(timezone.utc).isoformat(), **resultado}
        logger.info("Cron NFS-e concluído: %s", resultado.get("processadas"))
    except Exception as exc:  # noqa: BLE001 — nunca deixa a thread morrer calada
        logger.exception("Cron NFS-e falhou")
        _CRON["ultimo"] = {"em": datetime.now(timezone.utc).isoformat(), "erro": str(exc)[:300]}
    finally:
        db.close()
        _CRON["rodando"] = False


@router_cron.api_route("/cron", methods=["GET", "POST"])
def cron_nfse(
    x_cron_token: str = Header(default=""),
    token: str = "",
    chunk: int = 6,
) -> dict:
    """Dispara um passo do cron de NFS-e e responde NA HORA (202-like).

    Chamado por cron EXTERNO a cada ~10-15 min. Aceita GET ou POST. Token pelo
    header `X-Cron-Token` OU pela URL `?token=...`. Env `NFSE_CRON_TOKEN` (cai
    pra `DFE_CRON_TOKEN`). `chunk` = empresas por rodada (cap 15).

    A sincronização roda em THREAD: a resposta é imediata (não dá 502 do Traefik)
    e o resultado da rodada ANTERIOR volta em `ultimo` — é assim que se acompanha.
    Se ainda estiver rodando, não empilha outra (devolve `ja_rodando`)."""
    esperado = os.getenv("NFSE_CRON_TOKEN", "") or os.getenv("DFE_CRON_TOKEN", "")
    recebido = x_cron_token or token
    if not esperado:
        raise HTTPException(status_code=503, detail="NFSE_CRON_TOKEN (ou DFE_CRON_TOKEN) não configurado no servidor.")
    if not recebido or not hmac.compare_digest(recebido, esperado):
        raise HTTPException(status_code=401, detail="Token do cron inválido.")

    if _CRON["rodando"]:
        return {"ok": True, "ja_rodando": True, "iniciado_em": _CRON["iniciado_em"], "ultimo": _CRON["ultimo"]}

    _CRON["rodando"] = True
    _CRON["iniciado_em"] = datetime.now(timezone.utc).isoformat()
    threading.Thread(
        target=_rodar_cron_nfse, args=(max(1, min(chunk, 15)),), daemon=True,
    ).start()
    return {"ok": True, "disparado": True, "iniciado_em": _CRON["iniciado_em"], "ultimo": _CRON["ultimo"]}


class SincronizarLotePayload(BaseModel):
    empresa_ids: list[int] = Field(..., description="IDs do bloco (máx 5)")
    max_lotes: int = Field(30, ge=1, le=200)


@router.get("/elegiveis")
def elegiveis(db: Session = Depends(get_db)) -> list[dict]:
    """Empresas aptas: ativas, com cert A1 (ADN exige o A1 do próprio CNPJ)."""
    emps = NFSeService(db).listar_elegiveis()
    return [
        {"id": e.id, "razao_social": e.razao_social, "cnpj": e.cnpj,
         "ult_nsu": e.nfse_adn_ult_nsu}
        for e in emps
    ]


@router.post("/empresa/{empresa_id}/sincronizar")
def sincronizar(empresa_id: int, max_lotes: int = 50, db: Session = Depends(get_db)) -> dict:
    """Puxa as NFS-e da empresa pelo ADN (emitidas+recebidas), incremental por NSU.

    Re-chame até `motivo_parada`='fim_fila' (drenou tudo). `max_lotes` limita por
    chamada pra caber no timeout do proxy.
    """
    return NFSeService(db).sincronizar_empresa(empresa_id, max_lotes=max_lotes)


@router.post("/sincronizar-lote")
def sincronizar_lote(payload: SincronizarLotePayload, db: Session = Depends(get_db)) -> dict:
    """Sincroniza um BLOCO de empresas. Erro numa não derruba o bloco."""
    if not payload.empresa_ids:
        return {"resultados": []}
    if len(payload.empresa_ids) > 5:
        raise HTTPException(status_code=400, detail="Máximo 5 empresas por bloco.")
    resultados = NFSeService(db).sincronizar_lote(
        payload.empresa_ids, max_lotes=payload.max_lotes)
    return {"resultados": resultados}
