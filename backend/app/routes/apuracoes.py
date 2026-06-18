import logging
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db

logger = logging.getLogger(__name__)
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


# ---------------------------------------------------------------------------
# Transmissão em BACKGROUND (thread) — o Serpro às vezes passa de 60s e o
# Traefik corta a conexão sync (502 HTML sem CORS). Aqui o POST dispara numa
# thread e responde NA HORA com um job_id; o front consulta o status até
# concluir. Roda em modo eager (sem worker Celery), igual o robô já faz.
# Job store em memória: some no restart (jobs são curtos) e funciona com
# --workers 1 (1 processo), que é como o backend roda.
# ---------------------------------------------------------------------------
_TRANSM_JOBS: dict[str, dict] = {}
_TRANSM_LOCK = threading.Lock()
_TRANSM_MAX = 300


def _rodar_transmissao(job_id: str, apuracao_id: int, dry_run: bool) -> None:
    db = SessionLocal()
    try:
        resultado = ApuracaoService(db).transmitir(apuracao_id, dry_run=dry_run)
        plano = jsonable_encoder(resultado)  # serializa igual o endpoint sync
        with _TRANSM_LOCK:
            _TRANSM_JOBS[job_id] = {"status": "concluido", "resultado": plano}
    except HTTPException as exc:
        with _TRANSM_LOCK:
            _TRANSM_JOBS[job_id] = {"status": "erro", "erro": str(exc.detail), "code": exc.status_code}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Transmissão async falhou (apuração %s)", apuracao_id)
        with _TRANSM_LOCK:
            _TRANSM_JOBS[job_id] = {"status": "erro", "erro": str(exc)}
    finally:
        db.close()


@router.post("/{apuracao_id}/transmitir-async")
def transmitir_async(
    apuracao_id: int, dry_run: bool = True, db: Session = Depends(get_db),
) -> dict:
    """Inicia o dry-run/transmissão PGDAS-D em background e responde na hora com
    `job_id`. O front consulta GET /apuracoes/transmitir-job/{job_id} até
    `status` virar `concluido` (com `resultado`) ou `erro`."""
    ApuracaoService(db).get_or_404(apuracao_id)  # erro rápido se não existir
    job_id = uuid.uuid4().hex
    with _TRANSM_LOCK:
        if len(_TRANSM_JOBS) > _TRANSM_MAX:
            _TRANSM_JOBS.clear()
        _TRANSM_JOBS[job_id] = {"status": "rodando"}
    threading.Thread(
        target=_rodar_transmissao, args=(job_id, apuracao_id, dry_run), daemon=True,
    ).start()
    return {"job_id": job_id, "status": "rodando"}


@router.get("/transmitir-job/{job_id}")
def transmitir_job(job_id: str) -> dict:
    """Status do job de transmissão: rodando | concluido | erro."""
    with _TRANSM_LOCK:
        job = _TRANSM_JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job não encontrado (pode ter expirado num restart). Tente de novo.",
        )
    return job


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


@router.get("/diagnostico/{empresa_id}/{ano_mes}")
def diagnostico_documentos(empresa_id: int, ano_mes: str, db: Session = Depends(get_db)):
    """Reconcilia o 'Faturamento' da tela de Documentos com o que o motor apura.

    Mostra DE ONDE vem a diferença vs o relatório oficial:
    - total_emitido_bruto = soma de TODAS as emitidas (= card de Documentos)
    - receita_bruta_vendas = só VENDAS (= o que bate com o oficial)
    - emitidas_por_natureza = quebra (venda × remessa × transferência × devolução)
    - duplicatas removidas pelo dedup (motor) vs a tela (que não deduplica)
    """
    from collections import defaultdict

    resumo = ApuracaoCalculator(db).calcular(empresa_id, ano_mes)
    por_natureza: dict[str, dict] = defaultdict(lambda: {"qtd": 0, "valor": 0.0})
    emitidas_qtd = 0
    recebidas_qtd = 0
    total_emitido = 0.0
    for d in resumo.documentos:
        if d.eh_emitida:
            emitidas_qtd += 1
            v = float(d.valor_nota or 0)
            total_emitido += v
            por_natureza[d.natureza_predominante]["qtd"] += 1
            por_natureza[d.natureza_predominante]["valor"] += v
        else:
            recebidas_qtd += 1
    return {
        "empresa": resumo.empresa_nome,
        "cnpj": resumo.empresa_cnpj,
        "ano_mes": ano_mes,
        "docs_apos_dedup": resumo.total_docs,
        "emitidas": emitidas_qtd,
        "recebidas": recebidas_qtd,
        "total_emitido_bruto": round(total_emitido, 2),
        "receita_bruta_vendas": str(resumo.receita_bruta),
        "emitidas_por_natureza": {
            k: {"qtd": v["qtd"], "valor": round(v["valor"], 2)}
            for k, v in sorted(por_natureza.items(), key=lambda x: -x[1]["valor"])
        },
        "avisos": resumo.avisos,
    }


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
