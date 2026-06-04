"""Rotas de faturamento mensal (RBT12)."""
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.receita_mensal_service import ReceitaMensalService


router = APIRouter(
    prefix="/empresas/{empresa_id}/receitas-mensais",
    tags=["receitas-mensais"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def listar(empresa_id: int, competencia: str, db: Session = Depends(get_db)) -> dict:
    """Lista os 12 meses anteriores a `competencia` (AAAAMM) com valores.

    Retorna {meses: [{ano_mes, valor_interno, valor_externo, origem}], rbt12,
    meses_preenchidos}. Meses sem dado vêm com valor 0.
    """
    return ReceitaMensalService(db).listar_para_competencia(empresa_id, competencia)


@router.put("")
def salvar(
    empresa_id: int,
    meses: list[dict] = Body(..., embed=True),
    db: Session = Depends(get_db),
) -> dict:
    """Salva (upsert) os meses informados na grade manual.

    Body: {"meses": [{ano_mes, valor_interno, valor_externo}, ...]}
    """
    return ReceitaMensalService(db).salvar_em_lote(empresa_id, meses, origem="manual")


@router.post("/puxar-receita")
def puxar_da_receita(
    empresa_id: int,
    competencia: str,
    db: Session = Depends(get_db),
) -> dict:
    """Puxa o faturamento dos 12 meses anteriores via Integra Contador
    (CONSDECLARACAO13 + CONSDECREC15). Best-effort — revise a grade depois.
    """
    return ReceitaMensalService(db).puxar_da_receita(empresa_id, competencia)
