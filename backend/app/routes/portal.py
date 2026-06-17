"""Portal do CLIENTE — área onde o dono da empresa vê SÓ os documentos dele.

Isolamento multi-tenant: TODO endpoint aqui escopa pela `empresa_id` do usuário
logado (derivada do token via get_current_cliente, NUNCA do input). O cliente
não consegue pedir a empresa de outro.

Read-only: o cliente só CONSULTA e BAIXA (XML/PDF/DACTE). Nada de robô, Integra,
certificados, outras empresas — isso é do escritório (get_current_user rejeita
cliente). Reaproveita as funções de download do escritório DEPOIS de conferir a
posse do documento.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.routes.documentos import (
    baixar_pdf_individual,
    baixar_xml_individual,
    baixar_zip_lote,
    listar_documentos,
    resumo_documentos,
)
from app.schemas.auth_schema import TokenResponse
from app.schemas.documento_schema import DocumentoFiscalRead
from app.schemas.auth_schema import LoginRequest
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    get_current_cliente,
)

router = APIRouter(prefix="/portal", tags=["portal-cliente"])


@router.post("/login", response_model=TokenResponse)
def login_cliente(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Login do PORTAL. Só aceita usuário CLIENTE (equipe do escritório usa o
    /auth/login). Mesmo mecanismo de JWT — o que muda é quem cada área aceita."""
    user = authenticate_user(db, payload.email, payload.password)
    if not user or not user.is_cliente or not user.empresa_id:
        # Mensagem genérica de propósito (não revela se o e-mail existe / é cliente)
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    return TokenResponse(access_token=create_access_token(user.email))


@router.get("/me")
def me(cliente: Usuario = Depends(get_current_cliente), db: Session = Depends(get_db)) -> dict:
    """Dados do cliente logado + a empresa dele (básico, sem credenciais)."""
    empresa = db.get(Empresa, cliente.empresa_id)
    return {
        "nome": cliente.nome,
        "email": cliente.email,
        "empresa": {
            "id": empresa.id,
            "razao_social": empresa.razao_social,
            "nome_fantasia": empresa.nome_fantasia,
            "cnpj": empresa.cnpj,
        } if empresa else None,
    }


@router.get("/documentos", response_model=list[DocumentoFiscalRead])
def portal_documentos(
    tipo_documento: TipoDocumento | None = None,
    cancelada: bool | None = None,
    origem: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    limite: int = 500,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> list[DocumentoFiscal]:
    """Lista as notas DA EMPRESA DO CLIENTE. empresa_id é FORÇADO pela identidade
    (o cliente não escolhe empresa). `origem`: emitida (saída) / recebida
    (entrada) — usado pelas abas. Reaproveita a listagem do escritório."""
    return listar_documentos(
        empresa_id=cliente.empresa_id,
        tipo_documento=tipo_documento,
        cancelada=cancelada,
        origem=origem,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=limite,
        db=db,
    )


@router.get("/documentos/zip")
def portal_baixar_zip(
    tipo_documento: TipoDocumento | None = None,
    origem: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    arquivo: Literal["xml", "pdf", "ambos"] = "xml",
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Baixa em LOTE (ZIP) as notas da empresa do cliente, respeitando os filtros
    da tela (tipo/origem/período). empresa_id FORÇADO pela identidade. Só ativas."""
    return baixar_zip_lote(
        empresa_id=cliente.empresa_id,
        tipo_documento=tipo_documento,
        cancelada=False,
        origem=origem,
        data_inicio=data_inicio,
        data_fim=data_fim,
        arquivo=arquivo,
        db=db,
    )


@router.get("/documentos/resumo")
def portal_resumo(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Totalizadores (emitidas/recebidas/faturamento) SÓ da empresa do cliente."""
    return resumo_documentos(
        empresa_id=cliente.empresa_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        db=db,
    )


def _doc_do_cliente(documento_id: int, cliente: Usuario, db: Session) -> DocumentoFiscal:
    """Carrega o doc e CONFERE que é da empresa do cliente. 404 (não 403) se não
    for — não revela a existência de documentos de outras empresas."""
    doc = db.get(DocumentoFiscal, documento_id)
    if not doc or doc.empresa_id != cliente.empresa_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return doc


@router.get("/documentos/{documento_id}/download")
def portal_baixar_xml(
    documento_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Baixa o XML — só se o documento for da empresa do cliente."""
    _doc_do_cliente(documento_id, cliente, db)
    return baixar_xml_individual(documento_id, db)


@router.get("/documentos/{documento_id}/pdf")
def portal_baixar_pdf(
    documento_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Baixa o PDF (DANFE/DACTE) — só se o documento for da empresa do cliente."""
    _doc_do_cliente(documento_id, cliente, db)
    return baixar_pdf_individual(documento_id, db)


# ---------------------------------------------------------------------------
# Dashboard gerencial do cliente (agregações escopadas pela empresa do token)
# ---------------------------------------------------------------------------
def _corte_meses(meses: int) -> datetime:
    """1º dia do mês `meses` meses atrás (inclui o mês atual)."""
    now = datetime.now(timezone.utc)
    total = (now.year * 12 + (now.month - 1)) - (meses - 1)
    cy, cm = divmod(total, 12)
    return datetime(cy, cm + 1, 1, tzinfo=timezone.utc)


@router.get("/dashboard")
def portal_dashboard(
    meses: int = 6,
    top: int = 8,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Painel do cliente: faturamento por mês + melhores clientes + maiores
    fornecedores + nº a manifestar. Tudo SÓ da empresa do cliente."""
    eid = cliente.empresa_id
    meses = max(1, min(meses, 24))
    top = max(1, min(top, 20))

    # Faturamento por mês (emitidas, saída real, ativas)
    mes_expr = func.to_char(DocumentoFiscal.data_emissao, "YYYY-MM")
    fat_rows = db.execute(
        select(
            mes_expr.label("mes"),
            func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor"),
        ).where(
            DocumentoFiscal.empresa_id == eid,
            DocumentoFiscal.origem == "emitida",
            DocumentoFiscal.cancelada == False,  # noqa: E712
            DocumentoFiscal.eh_saida.isnot(False),
            DocumentoFiscal.data_emissao >= _corte_meses(meses),
        ).group_by(mes_expr).order_by(mes_expr)
    ).all()
    faturamento_mensal = [{"mes": r.mes, "valor": float(r.valor or 0)} for r in fat_rows]

    # Melhores clientes (destinatários nomeados das emitidas — exclui NFC-e balcão)
    cli_rows = db.execute(
        select(
            DocumentoFiscal.nome_destinatario.label("nome"),
            func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor"),
        ).where(
            DocumentoFiscal.empresa_id == eid,
            DocumentoFiscal.origem == "emitida",
            DocumentoFiscal.cancelada == False,  # noqa: E712
            DocumentoFiscal.eh_saida.isnot(False),
            DocumentoFiscal.nome_destinatario.isnot(None),
            DocumentoFiscal.nome_destinatario != "",
        ).group_by(DocumentoFiscal.nome_destinatario).order_by(desc("valor")).limit(top)
    ).all()
    top_clientes = [{"nome": r.nome, "valor": float(r.valor or 0)} for r in cli_rows]

    # Maiores fornecedores (emitentes das recebidas)
    forn_rows = db.execute(
        select(
            DocumentoFiscal.nome_emitente.label("nome"),
            func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor"),
        ).where(
            DocumentoFiscal.empresa_id == eid,
            DocumentoFiscal.origem == "recebida",
            DocumentoFiscal.cancelada == False,  # noqa: E712
            DocumentoFiscal.nome_emitente.isnot(None),
            DocumentoFiscal.nome_emitente != "",
        ).group_by(DocumentoFiscal.nome_emitente).order_by(desc("valor")).limit(top)
    ).all()
    top_fornecedores = [{"nome": r.nome, "valor": float(r.valor or 0)} for r in forn_rows]

    a_manifestar = db.scalar(
        select(func.count(DocumentoFiscal.id)).where(
            DocumentoFiscal.empresa_id == eid,
            DocumentoFiscal.origem == "recebida",
            DocumentoFiscal.status == "resumo",
        )
    )
    return {
        "faturamento_mensal": faturamento_mensal,
        "top_clientes": top_clientes,
        "top_fornecedores": top_fornecedores,
        "a_manifestar": int(a_manifestar or 0),
    }


@router.post("/documentos/{documento_id}/manifestar")
def portal_manifestar_documento(
    documento_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Cliente dá Ciência da Operação numa nota de COMPRA dele — libera o XML
    completo. Confere posse antes de delegar pro serviço do escritório."""
    _doc_do_cliente(documento_id, cliente, db)
    from app.services.dfe_distribuicao_service import DfeDistribuicaoService
    return DfeDistribuicaoService(db).manifestar_documento(documento_id)


@router.post("/manifestar")
def portal_manifestar_lote(
    limite: int = 20,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Manifesta em lote as recebidas em resumo da empresa do cliente."""
    from app.services.dfe_distribuicao_service import DfeDistribuicaoService
    return DfeDistribuicaoService(db).manifestar_recebidas(cliente.empresa_id, limite=limite)
