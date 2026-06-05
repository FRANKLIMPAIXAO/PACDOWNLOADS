from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.apuracao_schema import (
    ApuracaoCreate, ApuracaoRead, ResumoMesResposta,
)
from app.services.apuracao_calculator import ApuracaoCalculator
from app.services.apuracao_service import ApuracaoService
from app.services.auth_service import get_current_user


class CalcularLotePayload(BaseModel):
    ano_mes: str = Field(..., description="Competência YYYYMM")
    empresa_ids: list[int] = Field(..., description="IDs das empresas do bloco")


router = APIRouter(
    prefix="/apuracoes", tags=["apuracoes"], dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[ApuracaoRead])
def listar(
    empresa_id: int | None = Query(None),
    ano_mes: str | None = Query(None, description="YYYYMM"),
    db: Session = Depends(get_db),
):
    return ApuracaoService(db).listar(empresa_id=empresa_id, ano_mes=ano_mes)


@router.get("/resumo/{ano_mes}", response_model=ResumoMesResposta)
def resumo(ano_mes: str, db: Session = Depends(get_db)):
    return ApuracaoService(db).resumo_mes(ano_mes)


@router.post("", response_model=ApuracaoRead, status_code=status.HTTP_201_CREATED)
def criar(payload: ApuracaoCreate, db: Session = Depends(get_db)):
    """Cria/atualiza DRAFT da apuracao do mes (idempotente por empresa+ano_mes)."""
    return ApuracaoService(db).criar_draft(
        payload.empresa_id, payload.ano_mes,
        payload.receita_bruta, payload.receitas_segregadas,
    )


@router.get("/{apuracao_id}", response_model=ApuracaoRead)
def obter(apuracao_id: int, db: Session = Depends(get_db)):
    return ApuracaoService(db).get_or_404(apuracao_id)


@router.post("/{apuracao_id}/transmitir")
def transmitir(
    apuracao_id: int,
    dry_run: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    """TRANSDECLARACAO11 — valida (dry-run) ou transmite declaração PGDAS-D.

    `?dry_run=true` (DEFAULT) → indicadorTransmissao=False: a RFB calcula e
    devolve os valores SEM gerar declaração definitiva. SEGURO pra conferir.
    `?dry_run=false` → transmite de verdade (gera declaração + recibo).

    Devolve {dry_run, valor_devido_rfb, valores_rfb, valor_devido_pac,
    divergencia, status}. Em dry-run o status da apuração NÃO muda.

    Fluxo recomendado: dry-run primeiro, comparar divergencia (RFB × PAC),
    só transmitir real (dry_run=false) se os valores baterem.
    """
    return ApuracaoService(db).transmitir(apuracao_id, dry_run=dry_run)


@router.post("/{apuracao_id}/das/gerar", response_model=ApuracaoRead)
def gerar_das(apuracao_id: int, db: Session = Depends(get_db)):
    """GERARDAS12 — gera DAS Simples em PDF (storage local)."""
    return ApuracaoService(db).gerar_das(apuracao_id)


@router.post("/{apuracao_id}/pagar", response_model=ApuracaoRead)
def marcar_pago(apuracao_id: int, db: Session = Depends(get_db)):
    return ApuracaoService(db).marcar_pago(apuracao_id)


@router.get("/{apuracao_id}/das/pdf")
def baixar_das(apuracao_id: int, db: Session = Depends(get_db)):
    apur = ApuracaoService(db).get_or_404(apuracao_id)
    if not apur.das_pdf_path:
        raise HTTPException(status_code=404, detail="DAS nao gerado.")
    p = Path(apur.das_pdf_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="PDF removido do storage.")
    return FileResponse(
        path=str(p), filename=f"das_{apur.ano_mes}.pdf",
        media_type="application/pdf",
    )


@router.get("/{apuracao_id}/extrato")
def extrato(apuracao_id: int, db: Session = Depends(get_db)):
    """CONSEXTRATO16 — extrato detalhado dos tributos do DAS."""
    return ApuracaoService(db).consultar_extrato(apuracao_id)


# --- Motor de calculo automatico (le XMLs e gera resumo) ---


@router.get("/calcular/{empresa_id}/{ano_mes}")
def calcular_preview(empresa_id: int, ano_mes: str, db: Session = Depends(get_db)):
    """Executa o motor de apuracao Simples Nacional e retorna preview SEM salvar.

    - Le NFe/CTe/NFSe da competencia (`empresa_id` + mes)
    - Classifica CFOPs (vendas, devolucoes, remessas, transferencias)
    - Identifica produtos com Substituicao Tributaria
    - Calcula RBT12 a partir das apuracoes anteriores
    - Aplica tabela do anexo (I/II/III/IV/V) -> aliquota efetiva
    - Devolve receita bruta liquida + decomposicao por tributo
    """
    resumo = ApuracaoCalculator(db).calcular(empresa_id, ano_mes)
    return resumo.to_payload()


@router.post("/calcular-lote")
def calcular_lote(payload: CalcularLotePayload, db: Session = Depends(get_db)):
    """Fechamento em LOTE: calcula + salva a apuração de várias empresas.

    Recebe um BLOCO de empresa_ids (o frontend fatia a carteira em blocos pra
    caber no timeout do Traefik ~60s) e devolve um item por empresa com
    receita/DAS/anexo/avisos — ou ok=False + erro se alguma falhar (não derruba
    o bloco). Idempotente: re-rodar atualiza a apuração existente.
    """
    if len(payload.ano_mes) != 6 or not payload.ano_mes.isdigit():
        raise HTTPException(status_code=400, detail="ano_mes deve ser YYYYMM")
    if not payload.empresa_ids:
        return {"ano_mes": payload.ano_mes, "resultados": []}
    if len(payload.empresa_ids) > 25:
        raise HTTPException(
            status_code=400,
            detail="Máximo 25 empresas por bloco (pra caber no timeout). Fatie no frontend.",
        )
    resultados = ApuracaoCalculator(db).calcular_lote(payload.empresa_ids, payload.ano_mes)
    return {"ano_mes": payload.ano_mes, "resultados": resultados}


@router.post("/calcular/{empresa_id}/{ano_mes}")
def calcular_e_salvar(empresa_id: int, ano_mes: str, db: Session = Depends(get_db)):
    """Calcula via motor e cria/atualiza a apuracao DRAFT da competencia."""
    apur = ApuracaoCalculator(db).calcular_e_salvar(empresa_id, ano_mes)
    return {
        "id": apur.id,
        "empresa_id": apur.empresa_id,
        "ano_mes": apur.ano_mes,
        "regime": apur.regime.value if hasattr(apur.regime, "value") else str(apur.regime),
        "status": apur.status.value if hasattr(apur.status, "value") else str(apur.status),
        "receita_bruta": str(apur.receita_bruta) if apur.receita_bruta else None,
        "valor_devido": str(apur.valor_devido) if apur.valor_devido else None,
        "receitas_segregadas": apur.receitas_segregadas,
    }
