"""Rotas da busca de NFS-e pelo ADN (Ambiente de Dados Nacional)."""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.nfse_service import NFSeService

router = APIRouter(
    prefix="/nfse-adn", tags=["nfse-adn"], dependencies=[Depends(get_current_user)],
)

# Router SEM login — chamado por um cron EXTERNO (token no header). Em produção
# NÃO roda Celery beat (só uvicorn), então a automação é cron externo batendo aqui.
router_cron = APIRouter(prefix="/nfse-adn", tags=["nfse-adn-cron"])


@router_cron.post("/cron")
def cron_nfse(
    x_cron_token: str = Header(default=""),
    chunk: int = 3,
    db: Session = Depends(get_db),
) -> dict:
    """Passo do cron de NFS-e — sincroniza um PEDAÇO da carteira pelo ADN.

    Chamado por cron EXTERNO a cada ~10-15 min. Protegido por `X-Cron-Token`
    (env `NFSE_CRON_TOKEN`; cai pra `DFE_CRON_TOKEN` se aquele não estiver setado,
    pra reaproveitar o mesmo cron). `chunk` = empresas por chamada (cap 8)."""
    esperado = os.getenv("NFSE_CRON_TOKEN", "") or os.getenv("DFE_CRON_TOKEN", "")
    if not esperado:
        raise HTTPException(status_code=503, detail="NFSE_CRON_TOKEN (ou DFE_CRON_TOKEN) não configurado no servidor.")
    if not x_cron_token or not hmac.compare_digest(x_cron_token, esperado):
        raise HTTPException(status_code=401, detail="Token do cron inválido.")
    resultado = NFSeService(db).cron_sincronizar(chunk=max(1, min(chunk, 8)))
    try:
        from app.services.cron_log import registrar_cron
        registrar_cron(db, "nfse", resultado)
    except Exception:  # noqa: BLE001 — log nunca derruba o cron
        db.rollback()
    return resultado


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
