from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.integra_schema import (
    DteResposta,
    MensagemEcacDetalhe,
    MensagemEcacRead,
    PagamentoRead,
    ProcuracaoRead,
    SituacaoFiscalRead,
    SyncCaixaPostalResposta,
)
from app.services.auth_service import get_current_user
from app.services.integra_contador_service import IntegraContadorService


router = APIRouter(
    prefix="/empresas/{empresa_id}/integra",
    tags=["integra-contador"],
    dependencies=[Depends(get_current_user)],
)


# --- Caixa Postal eCAC ---


@router.post(
    "/caixa-postal/sync",
    response_model=SyncCaixaPostalResposta,
)
def sync_caixa_postal(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Busca mensagens via MSGCONTRIBUINTE61 e persiste em mensagens_ecac."""
    service = IntegraContadorService(db)
    resultado = service.sync_caixa_postal(empresa_id)
    return asdict(resultado)


@router.get(
    "/caixa-postal",
    response_model=list[MensagemEcacRead],
)
def listar_caixa_postal(empresa_id: int, db: Session = Depends(get_db)) -> list:
    return IntegraContadorService(db).listar_mensagens(empresa_id)


@router.get(
    "/caixa-postal/{isn_msg}",
    response_model=MensagemEcacDetalhe,
)
def detalhar_caixa_postal(empresa_id: int, isn_msg: str, db: Session = Depends(get_db)):
    """MSGDETALHAMENTO62 — busca conteudo HTML completo da mensagem."""
    return IntegraContadorService(db).detalhar_mensagem(empresa_id, isn_msg)


class MarcarLidasPayload(BaseModel):
    isns: list[str] | None = None  # None ou vazia = marca TODAS


@router.post("/caixa-postal/marcar-lidas")
def marcar_mensagens_lidas(
    empresa_id: int,
    payload: MarcarLidasPayload | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Marca mensagens como lidas LOCALMENTE (`indicador_leitura='1'`).

    Body opcional `{"isns": ["123", "456"]}`. Se omitido ou vazio,
    marca TODAS as mensagens da empresa.
    NOTA: nao chama Serpro — apenas atualiza o flag local.
    """
    from app.models.mensagem_ecac import MensagemEcac

    stmt = sa_update(MensagemEcac).where(MensagemEcac.empresa_id == empresa_id)
    isns = payload.isns if payload else None
    if isns:
        stmt = stmt.where(MensagemEcac.isn_msg.in_(isns))
    stmt = stmt.values(indicador_leitura="1")
    result = db.execute(stmt)
    db.commit()
    return {"empresa_id": empresa_id, "marcadas": result.rowcount}


@router.get("/caixa-postal-resumo")
def resumo_caixa_postal(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Resumo agregado da caixa postal: contadores por leitura e relevancia."""
    from app.models.mensagem_ecac import MensagemEcac
    from sqlalchemy import select as sa_select

    msgs = db.scalars(
        sa_select(MensagemEcac).where(MensagemEcac.empresa_id == empresa_id)
    ).all()
    nao_lidas = sum(1 for m in msgs if m.indicador_leitura != "1")
    lidas = sum(1 for m in msgs if m.indicador_leitura == "1")
    alta = sum(1 for m in msgs if m.indicador_relevancia == "1")
    alta_nao_lidas = sum(
        1 for m in msgs
        if m.indicador_relevancia == "1" and m.indicador_leitura != "1"
    )
    return {
        "empresa_id": empresa_id,
        "total": len(msgs),
        "nao_lidas": nao_lidas,
        "lidas": lidas,
        "alta_relevancia": alta,
        "alta_relevancia_nao_lidas": alta_nao_lidas,
    }


# --- Procuracao ---


@router.post(
    "/procuracao/sync",
    response_model=ProcuracaoRead,
)
def sync_procuracao(empresa_id: int, db: Session = Depends(get_db)):
    """OBTERPROCURACAO41 — consulta procuracao ativa e persiste."""
    return IntegraContadorService(db).sync_procuracao(empresa_id)


@router.get(
    "/procuracao",
    response_model=ProcuracaoRead,
)
def obter_procuracao(empresa_id: int, db: Session = Depends(get_db)):
    proc = IntegraContadorService(db).ultima_procuracao(empresa_id)
    if not proc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma procuracao sincronizada ainda. Use POST /procuracao/sync.",
        )
    return proc


# --- DTE ---


@router.get(
    "/dte",
    response_model=DteResposta,
)
def consultar_dte(empresa_id: int, db: Session = Depends(get_db)) -> DteResposta:
    """CONSULTASITUACAODTE111 — situacao do DTE para o CNPJ."""
    dados = IntegraContadorService(db).consultar_dte(empresa_id)
    return DteResposta(
        cnpj=dados.get("cnpj"),
        indicador_optante=dados.get("indicadorOptante"),
        data_adesao=dados.get("dataAdesao"),
        raw=dados,
    )


# --- SITFIS ---


@router.post(
    "/sitfis/gerar",
    response_model=SituacaoFiscalRead,
)
def gerar_situacao_fiscal(empresa_id: int, db: Session = Depends(get_db)):
    """SOLICITARPROTOCOLO91 + RELATORIOSITFIS92 — gera relatorio SITFIS em PDF."""
    return IntegraContadorService(db).gerar_situacao_fiscal(empresa_id)


@router.get(
    "/sitfis",
    response_model=SituacaoFiscalRead,
)
def obter_ultima_situacao(empresa_id: int, db: Session = Depends(get_db)):
    situacao = IntegraContadorService(db).ultima_situacao_fiscal(empresa_id)
    if not situacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma situacao fiscal gerada. Use POST /sitfis/gerar.",
        )
    return situacao


@router.get("/sitfis/{situacao_id}/pdf")
def baixar_pdf_situacao(empresa_id: int, situacao_id: int, db: Session = Depends(get_db)):
    """Download do PDF da situacao fiscal gerada."""
    situacao = IntegraContadorService(db).obter_situacao_fiscal(situacao_id)
    if situacao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Situacao fiscal nao encontrada para esta empresa.")
    if not situacao.pdf_path:
        raise HTTPException(status_code=404, detail="PDF indisponivel.")
    path = Path(situacao.pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF removido do storage.")
    return FileResponse(
        path=str(path),
        filename=f"sitfis-{situacao_id}.pdf",
        media_type="application/pdf",
    )


# --- Pagamentos ---


@router.get(
    "/pagamentos",
    response_model=list[PagamentoRead],
)
def listar_pagamentos(
    empresa_id: int,
    data_inicio: str,
    data_fim: str,
    db: Session = Depends(get_db),
):
    """PAGAMENTOS71 — lista DARF/DAS pagos no periodo (YYYY-MM-DD)."""
    raws = IntegraContadorService(db).listar_pagamentos(empresa_id, data_inicio, data_fim)
    return [
        PagamentoRead(
            numero_documento=str(p.get("numeroDocumento") or ""),
            codigo_receita=p.get("codigoReceita"),
            descricao_receita=p.get("descricaoReceita"),
            data_arrecadacao=p.get("dataArrecadacao"),
            valor_total=p.get("valorTotal"),
        )
        for p in raws
    ]


@router.get("/pagamentos/{numero_documento}/comprovante")
def baixar_comprovante(
    empresa_id: int,
    numero_documento: str,
    db: Session = Depends(get_db),
):
    """COMPARRECADACAO72 — emite e devolve PDF do comprovante."""
    pdf = IntegraContadorService(db).emitir_comprovante_pagamento(empresa_id, numero_documento)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="comprovante-{numero_documento}.pdf"',
        },
    )
