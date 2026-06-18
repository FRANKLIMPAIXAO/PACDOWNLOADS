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
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.certidao import Certidao, TipoCertidao
from app.models.cobranca_portal import CobrancaPortal
from app.models.documento_escritorio import DocumentoEscritorio
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.models.guia_das import GuiaDAS
from app.models.guia_dctfweb import GuiaDctfweb
from app.models.usuario import Usuario
from app.providers.integra_contador import IntegraContadorError
from app.services.guia_das_service import GuiaDASService
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


def _dt(s: str | None, fim: bool = False) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return d.replace(hour=23, minute=59, second=59) if fim else d
    except ValueError:
        return None


@router.get("/dashboard")
def portal_dashboard(
    meses: int = 6,
    top: int = 8,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Painel do cliente: faturamento por mês (TENDÊNCIA, últimos `meses`) +
    melhores clientes + maiores fornecedores (NO PERÍODO data_inicio/data_fim,
    pra bater com os cards) + nº a manifestar. Tudo SÓ da empresa do cliente."""
    eid = cliente.empresa_id
    meses = max(1, min(meses, 24))
    top = max(1, min(top, 20))
    di, df = _dt(data_inicio), _dt(data_fim, fim=True)

    def _no_periodo(conds: list):
        if di is not None:
            conds.append(DocumentoFiscal.data_emissao >= di)
        if df is not None:
            conds.append(DocumentoFiscal.data_emissao <= df)
        return conds

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
    cli_conds = _no_periodo([
        DocumentoFiscal.empresa_id == eid,
        DocumentoFiscal.origem == "emitida",
        DocumentoFiscal.cancelada == False,  # noqa: E712
        DocumentoFiscal.eh_saida.isnot(False),
        DocumentoFiscal.nome_destinatario.isnot(None),
        DocumentoFiscal.nome_destinatario != "",
    ])
    cli_rows = db.execute(
        select(
            DocumentoFiscal.nome_destinatario.label("nome"),
            func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor"),
        ).where(*cli_conds)
        .group_by(DocumentoFiscal.nome_destinatario).order_by(desc("valor")).limit(top)
    ).all()
    top_clientes = [{"nome": r.nome, "valor": float(r.valor or 0)} for r in cli_rows]

    # Maiores fornecedores (emitentes das recebidas)
    forn_conds = _no_periodo([
        DocumentoFiscal.empresa_id == eid,
        DocumentoFiscal.origem == "recebida",
        DocumentoFiscal.cancelada == False,  # noqa: E712
        DocumentoFiscal.nome_emitente.isnot(None),
        DocumentoFiscal.nome_emitente != "",
    ])
    forn_rows = db.execute(
        select(
            DocumentoFiscal.nome_emitente.label("nome"),
            func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor"),
        ).where(*forn_conds)
        .group_by(DocumentoFiscal.nome_emitente).order_by(desc("valor")).limit(top)
    ).all()
    top_fornecedores = [{"nome": r.nome, "valor": float(r.valor or 0)} for r in forn_rows]

    # SÓ NF-e (modelo 55) manifesta. NFS-e (serviço) e CT-e não têm Ciência da
    # Operação — não entram na contagem nem têm botão Manifestar.
    a_manifestar = db.scalar(
        select(func.count(DocumentoFiscal.id)).where(
            DocumentoFiscal.empresa_id == eid,
            DocumentoFiscal.origem == "recebida",
            DocumentoFiscal.status == "resumo",
            DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
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


# ---------------------------------------------------------------------------
# Documentos do ESCRITÓRIO (entregues pelo PAC TAREFAS) — guias, relatórios,
# comunicados. Separados das notas fiscais.
# ---------------------------------------------------------------------------
@router.get("/documentos-escritorio")
def portal_documentos_escritorio(
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Lista os documentos que o escritório entregou pra esta empresa + nº de
    não lidos (pro badge)."""
    docs = list(db.scalars(
        select(DocumentoEscritorio)
        .where(DocumentoEscritorio.empresa_id == cliente.empresa_id)
        .order_by(DocumentoEscritorio.enviado_em.desc())
        .limit(300)
    ).all())
    nao_lidos = sum(1 for d in docs if d.lido_em is None)
    return {
        "nao_lidos": nao_lidos,
        "documentos": [
            {
                "id": d.id,
                "tipo": d.tipo,
                "titulo": d.titulo,
                "mensagem": d.mensagem,
                "competencia": d.competencia,
                "vencimento": d.vencimento.isoformat() if d.vencimento else None,
                "valor": float(d.valor) if d.valor is not None else None,
                "nome_arquivo": d.nome_arquivo,
                "tem_arquivo": bool(d.arquivo_path),
                "enviado_em": d.enviado_em.isoformat() if d.enviado_em else None,
                "lido": d.lido_em is not None,
            }
            for d in docs
        ],
    }


@router.get("/documentos-escritorio/{doc_id}/download")
def portal_baixar_documento_escritorio(
    doc_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Baixa o arquivo entregue pelo escritório — só se for da empresa do cliente.
    Marca como lido na primeira abertura."""
    from datetime import datetime, timezone
    from pathlib import Path as _Path

    doc = db.get(DocumentoEscritorio, doc_id)
    if not doc or doc.empresa_id != cliente.empresa_id:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if not doc.arquivo_path or not _Path(doc.arquivo_path).exists():
        raise HTTPException(status_code=404, detail="Este documento não tem arquivo anexado.")
    if doc.lido_em is None:
        doc.lido_em = datetime.now(timezone.utc)
        db.commit()
    nome = doc.nome_arquivo or f"documento_{doc.id}.pdf"
    return FileResponse(
        path=doc.arquivo_path,
        filename=nome,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ---------------------------------------------------------------------------
# CNDs / Certidões — o cliente VÊ e BAIXA as certidões da empresa dele.
# Esconde a FEDERAL (SITFIS), que é controle interno do escritório.
# ---------------------------------------------------------------------------
_LABEL_CERT = {
    TipoCertidao.FEDERAL_OFICIAL: "Federal (RFB/PGFN)",
    TipoCertidao.FGTS: "FGTS (CRF)",
    TipoCertidao.TRABALHISTA: "Trabalhista (CNDT)",
    TipoCertidao.ESTADUAL: "Estadual",
    TipoCertidao.MUNICIPAL: "Municipal",
}


@router.get("/certidoes")
def portal_certidoes(
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Certidões da empresa do cliente (a mais recente de cada tipo). Esconde a
    FEDERAL interna (SITFIS, controle do escritório). Read-only, sem custo."""
    certs = list(db.scalars(
        select(Certidao)
        .where(
            Certidao.empresa_id == cliente.empresa_id,
            Certidao.tipo != TipoCertidao.FEDERAL,
        )
        .order_by(Certidao.tipo, Certidao.data_validade.desc(), Certidao.id.desc())
    ).all())
    # a query já ordena por tipo + validade desc → a 1ª de cada tipo é a vigente
    vistos: set = set()
    out = []
    for c in certs:
        if c.tipo in vistos:
            continue
        vistos.add(c.tipo)
        out.append({
            "id": c.id,
            "tipo": c.tipo.value,
            "tipo_label": _LABEL_CERT.get(c.tipo, c.tipo.value),
            "numero": c.numero,
            "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
            "data_validade": c.data_validade.isoformat() if c.data_validade else None,
            "status": c.status(),
            "dias_para_vencer": c.dias_para_vencer,
            "tem_pdf": bool(c.pdf_path),
        })
    return {"certidoes": out}


@router.get("/certidoes/{certidao_id}/pdf")
def portal_baixar_certidao(
    certidao_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Baixa o PDF de uma certidão — só se for da empresa do cliente e não for a
    FEDERAL interna. 404 (não 403) pra não revelar certidões de outras empresas."""
    c = db.get(Certidao, certidao_id)
    if not c or c.empresa_id != cliente.empresa_id or c.tipo == TipoCertidao.FEDERAL:
        raise HTTPException(status_code=404, detail="Certidão não encontrada.")
    if not c.pdf_path:
        raise HTTPException(status_code=404, detail="Esta certidão ainda não tem PDF.")
    p = Path(c.pdf_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Arquivo PDF não encontrado.")
    return FileResponse(path=str(p), filename=p.name, media_type="application/pdf")


# ---------------------------------------------------------------------------
# Guias DAS (Simples) — o cliente VÊ as guias, RECALCULA (Integra) e BAIXA.
# Trava: 1 recálculo GRÁTIS por guia; do 2º em diante R$ 5,00 (avisa antes).
# ---------------------------------------------------------------------------
VALOR_RECALCULO = Decimal("5.00")


def _guia_do_cliente(guia_id: int, cliente: Usuario, db: Session) -> GuiaDAS:
    guia = db.get(GuiaDAS, guia_id)
    if not guia or guia.empresa_id != cliente.empresa_id:
        raise HTTPException(status_code=404, detail="Guia não encontrada.")
    return guia


def _recalculos_feitos(guia_id: int, empresa_id: int, db: Session) -> int:
    return int(db.scalar(
        select(func.count(CobrancaPortal.id)).where(
            CobrancaPortal.empresa_id == empresa_id,
            CobrancaPortal.guia_das_id == guia_id,
            CobrancaPortal.tipo == "recalculo_das",
        )
    ) or 0)


@router.get("/guias-das")
def portal_guias_das(
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Guias DAS da empresa do cliente + nº de recálculos já feitos em cada uma
    (pra a UI saber se o próximo é grátis ou cobrado)."""
    guias = GuiaDASService(db).listar_empresa(cliente.empresa_id)
    counts = dict(db.execute(
        select(CobrancaPortal.guia_das_id, func.count(CobrancaPortal.id))
        .where(
            CobrancaPortal.empresa_id == cliente.empresa_id,
            CobrancaPortal.tipo == "recalculo_das",
            CobrancaPortal.guia_das_id.isnot(None),
        )
        .group_by(CobrancaPortal.guia_das_id)
    ).all())
    out = []
    for g in guias:
        venc = g.data_vencimento_atualizada or g.data_vencimento_original
        out.append({
            "id": g.id,
            "competencia": g.competencia_formatada,
            "periodo_apuracao": g.periodo_apuracao,
            "valor_principal": float(g.valor_principal or 0),
            "valor_atualizado": float(g.valor_atualizado) if g.valor_atualizado is not None else None,
            "data_vencimento": venc.isoformat() if venc else None,
            "situacao": g.situacao,
            "dias_atraso": g.dias_atraso,
            "tem_pdf": bool(g.pdf_path),
            "recalculos": int(counts.get(g.id, 0)),
            "pode_recalcular": g.situacao != "paga",
        })
    return {"guias": out, "valor_recalculo_extra": float(VALOR_RECALCULO)}


@router.post("/guias-das/{guia_id}/atualizar")
def portal_atualizar_guia(
    guia_id: int,
    confirmar: bool = False,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """Recalcula a guia (DARF com Selic+mora via Integra) e libera o PDF.

    TRAVA: o 1º recálculo de cada guia é GRÁTIS; do 2º em diante custa R$ 5,00.
    Quando vai cobrar, devolve `cobranca_necessaria=true` SEM chamar o Integra —
    o front mostra o aviso e re-chama com `confirmar=true`. A cobrança só é
    registrada (livro `cobrancas_portal`) DEPOIS do recálculo dar certo."""
    guia = _guia_do_cliente(guia_id, cliente, db)
    if guia.situacao == "paga":
        raise HTTPException(status_code=400, detail="Esta guia já está paga — não precisa recalcular.")

    feitos = _recalculos_feitos(guia.id, cliente.empresa_id, db)
    cobrar = feitos >= 1
    if cobrar and not confirmar:
        return {
            "ok": False,
            "cobranca_necessaria": True,
            "valor": float(VALOR_RECALCULO),
            "recalculos_feitos": feitos,
            "mensagem": (
                f"Você já gerou esta guia {feitos}x. O 1º recálculo é grátis; "
                f"este novo tem custo de R$ 5,00. Deseja gerar mesmo assim?"
            ),
        }

    try:
        guia = GuiaDASService(db).emitir_guia_atualizada(guia.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IntegraContadorError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    valor = VALOR_RECALCULO if cobrar else Decimal("0.00")
    db.add(CobrancaPortal(
        empresa_id=cliente.empresa_id,
        guia_das_id=guia.id,
        competencia=guia.periodo_apuracao,
        tipo="recalculo_das",
        valor=valor,
        descricao=f"Recálculo DAS {guia.competencia_formatada}" + (" (cobrado)" if cobrar else " (grátis)"),
    ))
    db.commit()

    venc = guia.data_vencimento_atualizada or guia.data_vencimento_original
    return {
        "ok": True,
        "cobrado": bool(cobrar),
        "valor": float(valor),
        "situacao": guia.situacao,
        "valor_atualizado": float(guia.valor_atualizado) if guia.valor_atualizado is not None else None,
        "data_vencimento": venc.isoformat() if venc else None,
        "mensagem": (
            "Guia atualizada gerada! Já pode baixar o PDF."
            + (" Foi cobrado R$ 5,00 (recálculo extra)." if cobrar else " (1º recálculo — grátis).")
        ),
    }


@router.get("/guias-das/{guia_id}/pdf")
def portal_baixar_guia_pdf(
    guia_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Baixa o PDF da guia DAS — só se for da empresa do cliente."""
    guia = _guia_do_cliente(guia_id, cliente, db)
    if not guia.pdf_path:
        raise HTTPException(status_code=404, detail="Guia ainda sem PDF — gere a guia atualizada primeiro.")
    p = Path(guia.pdf_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Arquivo PDF não encontrado.")
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=f"DAS_{guia.periodo_apuracao}.pdf",
    )


# ---------------------------------------------------------------------------
# Guias DCTFWeb (DARF de contribuições da folha) — emitidas pelo ESCRITÓRIO via
# Integra (GERARGUIA31/313). Read-only no portal: o cliente vê e baixa o PDF.
# ---------------------------------------------------------------------------
@router.get("/guias-dctfweb")
def portal_guias_dctfweb(
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> dict:
    """DARFs DCTFWeb que o escritório já emitiu pra esta empresa."""
    rows = list(db.scalars(
        select(GuiaDctfweb)
        .where(GuiaDctfweb.empresa_id == cliente.empresa_id)
        .order_by(GuiaDctfweb.ano_pa.desc(), GuiaDctfweb.mes_pa.desc(), GuiaDctfweb.emitida_em.desc())
        .limit(300)
    ).all())
    return {
        "guias": [
            {
                "id": g.id,
                "periodo": g.periodo_formatado,
                "categoria": g.categoria,
                "origem": g.origem,  # ativa | andamento
                "emitida_em": g.emitida_em.isoformat() if g.emitida_em else None,
                "tem_pdf": bool(g.pdf_path),
            }
            for g in rows
        ],
    }


@router.get("/guias-dctfweb/{guia_id}/pdf")
def portal_baixar_dctfweb(
    guia_id: int,
    cliente: Usuario = Depends(get_current_cliente),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Baixa o DARF DCTFWeb — só se for da empresa do cliente."""
    g = db.get(GuiaDctfweb, guia_id)
    if not g or g.empresa_id != cliente.empresa_id:
        raise HTTPException(status_code=404, detail="Guia não encontrada.")
    if not g.pdf_path:
        raise HTTPException(status_code=404, detail="Guia sem PDF.")
    p = Path(g.pdf_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Arquivo PDF não encontrado.")
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=f"DCTFWeb_{g.ano_pa}{g.mes_pa or ''}.pdf",
    )
