"""Rotas da busca de NFS-e pelo ADN (Ambiente de Dados Nacional)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.nfse_service import NFSeService

router = APIRouter(
    prefix="/nfse-adn", tags=["nfse-adn"], dependencies=[Depends(get_current_user)],
)


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
