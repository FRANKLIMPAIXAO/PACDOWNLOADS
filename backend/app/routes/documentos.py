import io
import zipfile
from pathlib import Path
from typing import Literal

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.providers.focus_nfe import FocusNFeProvider
from app.schemas.documento_schema import DocumentoFiscalRead
from app.services.auth_service import get_current_user
from app.services.upload_xml_service import UploadXmlService


router = APIRouter(prefix="/documentos", tags=["documentos"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[DocumentoFiscalRead])
def listar_documentos(
    empresa_id: int | None = None,
    tipo_documento: TipoDocumento | None = None,
    cancelada: bool | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
) -> list[DocumentoFiscal]:
    """Lista documentos com filtros opcionais.

    Filtros:
    - `empresa_id`: somente da empresa
    - `tipo_documento`: NFE/CTE/NFSE
    - `cancelada`: None (todas) / True (canceladas) / False (ativas)
    - `data_inicio` / `data_fim`: ISO YYYY-MM-DD (inclusive) — filtra `data_emissao`
    """
    from datetime import datetime, timezone

    stmt = (
        select(DocumentoFiscal)
        .options(joinedload(DocumentoFiscal.empresa))
        .order_by(DocumentoFiscal.data_emissao.desc().nullslast(), DocumentoFiscal.id.desc())
    )
    if empresa_id:
        stmt = stmt.where(DocumentoFiscal.empresa_id == empresa_id)
    if tipo_documento:
        stmt = stmt.where(DocumentoFiscal.tipo_documento == tipo_documento)
    if cancelada is not None:
        stmt = stmt.where(DocumentoFiscal.cancelada == cancelada)
    if data_inicio:
        try:
            dt = datetime.strptime(data_inicio, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            stmt = stmt.where(DocumentoFiscal.data_emissao >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"data_inicio invalida: {data_inicio} (esperado YYYY-MM-DD)")
    if data_fim:
        try:
            dt = datetime.strptime(data_fim, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # +1 dia pra incluir o dia todo (data_emissao tem hora)
            dt = dt.replace(hour=23, minute=59, second=59)
            stmt = stmt.where(DocumentoFiscal.data_emissao <= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"data_fim invalida: {data_fim} (esperado YYYY-MM-DD)")
    return db.scalars(stmt).unique().all()


@router.get("/empresa/{empresa_id}", response_model=list[DocumentoFiscalRead])
def documentos_por_empresa(empresa_id: int, db: Session = Depends(get_db)) -> list[DocumentoFiscal]:
    return db.scalars(select(DocumentoFiscal).where(DocumentoFiscal.empresa_id == empresa_id)).all()


@router.get("/tipo/{tipo_documento}", response_model=list[DocumentoFiscalRead])
def documentos_por_tipo(tipo_documento: TipoDocumento, db: Session = Depends(get_db)) -> list[DocumentoFiscal]:
    return db.scalars(select(DocumentoFiscal).where(DocumentoFiscal.tipo_documento == tipo_documento)).all()


def _filename_amigavel(doc: DocumentoFiscal, ext: str) -> str:
    """Nome de arquivo intuitivo: <tipo>_<chave>_<emitente>.<ext>"""
    chave = doc.chave_acesso or "sem-chave"
    emitente = (doc.nome_emitente or "").replace("/", "-").replace("\\", "-")
    base = f"{doc.tipo_documento.value}_{chave}"
    if emitente:
        # Limpa caracteres problemáticos em filenames
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in emitente)[:40]
        base += f"_{safe}"
    return f"{base}.{ext}"


@router.get("/{documento_id}/download")
def baixar_xml_individual(documento_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Baixa o XML do documento como anexo (forca download no browser)."""
    documento = db.get(DocumentoFiscal, documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    path = Path(documento.xml_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="XML nao encontrado no storage")
    filename = _filename_amigavel(documento, "xml")
    return FileResponse(
        path=path,
        filename=filename,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{documento_id}/pdf")
def baixar_pdf_individual(documento_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Baixa o DANFE PDF associado ao documento.

    Se o PDF nao existe localmente mas a NF ja foi manifestada, tenta baixar
    da Focus na hora (Focus pode ter sincronizado com SEFAZ apos a ultima vez
    que o robo rodou). Se conseguir, salva no disco e retorna.
    """
    documento = db.get(DocumentoFiscal, documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    xml_path = Path(documento.xml_path)
    pdf_path = xml_path.with_suffix(".pdf")

    # Se ja temos local, serve direto
    if pdf_path.exists():
        filename = _filename_amigavel(documento, "pdf")
        return FileResponse(
            path=pdf_path,
            filename=filename,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Se eh NFe de SAIDA (a empresa eh a emitente) — Focus nao tem DANFE PDF
    # (so devolve pra notas RECEBIDAS apos manifestacao). Gera DANFE localmente
    # a partir do XML via brazilfiscalreport e cacheia no disco.
    eh_saida = documento.origem == "emitida"
    if not eh_saida and documento.chave_acesso and len(documento.chave_acesso) >= 20:
        # Fallback: detecta saida comparando CNPJ na chave com CNPJ da empresa
        emp_check = db.get(Empresa, documento.empresa_id)
        if emp_check:
            cnpj_emitente = documento.chave_acesso[6:20]
            cnpj_empresa = "".join(c for c in (emp_check.cnpj or "") if c.isdigit())
            eh_saida = cnpj_emitente == cnpj_empresa

    if eh_saida and xml_path.exists() and documento.tipo_documento.value == "NFE":
        try:
            from brazilfiscalreport.danfe import Danfe, DanfeConfig
            xml_str = xml_path.read_text(encoding="utf-8")
            danfe = Danfe(xml=xml_str, config=DanfeConfig())
            danfe.output(str(pdf_path))
            filename = _filename_amigavel(documento, "pdf")
            return FileResponse(
                path=pdf_path,
                filename=filename,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"Falha ao gerar DANFE PDF a partir do XML: {exc!r}",
            )

    # Nao temos local: ja foi manifestada? Tenta puxar da Focus agora
    raw = documento.json_original or {}
    if not raw.get("manifestado_em"):
        raise HTTPException(
            status_code=404,
            detail=(
                "DANFE PDF nao disponivel. "
                "Clique em 'Manifestar' para registrar Ciencia na SEFAZ."
            ),
        )

    empresa = db.get(Empresa, documento.empresa_id)
    token = empresa.get_focus_token() if empresa else None
    if not empresa or not token:
        raise HTTPException(
            status_code=404,
            detail="DANFE PDF nao disponivel localmente e empresa sem token Focus.",
        )

    # Tenta baixar agora
    provider = FocusNFeProvider()
    try:
        pdf_bytes = provider.baixar_pdf_nfe_recebida(token, documento.chave_acesso)
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "?")
        if status == 404:
            raise HTTPException(
                status_code=404,
                detail=(
                    "DANFE PDF ainda nao disponivel na Focus. "
                    "A sincronizacao com SEFAZ apos manifestacao pode levar "
                    "ate algumas horas. Tente novamente mais tarde."
                ),
            )
        raise HTTPException(
            status_code=502, detail=f"Falha ao buscar PDF na Focus: {status}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Erro Focus: {exc}"
        ) from exc

    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=502, detail="Focus retornou dados invalidos (nao e PDF)."
        )

    # Tambem tenta atualizar XML pra procNFe completo, se ainda for resumo
    try:
        if xml_path.exists():
            head = xml_path.read_text(encoding="utf-8", errors="replace")[:2000]
            if "<nfeProc" not in head and "<infNFe" not in head:
                xml_novo = provider.baixar_xml_nfe_recebida(
                    token, documento.chave_acesso
                )
                if "<nfeProc" in xml_novo or "<infNFe" in xml_novo:
                    xml_path.write_text(xml_novo, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass  # XML completo eh bonus; nao bloqueia o download do PDF

    # Salva PDF no disco pra proximas chamadas serem instantaneas
    pdf_path.write_bytes(pdf_bytes)

    filename = _filename_amigavel(documento, "pdf")
    return FileResponse(
        path=pdf_path,
        filename=filename,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Source": "focus-live-fetch",
        },
    )


@router.get("/zip")
def baixar_zip_lote(
    empresa_id: int | None = None,
    tipo_documento: TipoDocumento | None = None,
    cancelada: bool | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    arquivo: Literal["xml", "pdf", "ambos"] = "xml",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Empacota XMLs e/ou PDFs num ZIP e retorna pra download.

    Aceita os mesmos filtros que GET /documentos (empresa_id, tipo, cancelada,
    data_inicio, data_fim). `arquivo`: xml | pdf | ambos.
    """
    from datetime import datetime, timezone

    stmt = select(DocumentoFiscal).order_by(
        DocumentoFiscal.data_emissao.desc().nullslast()
    )
    if empresa_id:
        stmt = stmt.where(DocumentoFiscal.empresa_id == empresa_id)
    if tipo_documento:
        stmt = stmt.where(DocumentoFiscal.tipo_documento == tipo_documento)
    if cancelada is not None:
        stmt = stmt.where(DocumentoFiscal.cancelada == cancelada)
    if data_inicio:
        try:
            dt = datetime.strptime(data_inicio, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            stmt = stmt.where(DocumentoFiscal.data_emissao >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"data_inicio invalida: {data_inicio}")
    if data_fim:
        try:
            dt = datetime.strptime(data_fim, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc,
            )
            stmt = stmt.where(DocumentoFiscal.data_emissao <= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"data_fim invalida: {data_fim}")
    documentos = db.scalars(stmt).all()

    if not documentos:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado")

    buffer = io.BytesIO()
    incluidos = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in documentos:
            xml_path = Path(doc.xml_path) if doc.xml_path else None

            if arquivo in ("xml", "ambos") and xml_path and xml_path.exists():
                zf.write(xml_path, arcname=_filename_amigavel(doc, "xml"))
                incluidos += 1

            if arquivo in ("pdf", "ambos") and xml_path:
                pdf_path = xml_path.with_suffix(".pdf")
                if pdf_path.exists():
                    zf.write(pdf_path, arcname=_filename_amigavel(doc, "pdf"))
                    incluidos += 1

    if incluidos == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Nenhum arquivo '{arquivo}' encontrado para os documentos filtrados. "
                "Pra PDFs: certifique-se que foram manifestados e Focus sincronizou."
            ),
        )

    buffer.seek(0)
    sufixo_empresa = f"_empresa{empresa_id}" if empresa_id else ""
    sufixo_tipo = f"_{tipo_documento.value}" if tipo_documento else ""
    filename = f"documentos{sufixo_empresa}{sufixo_tipo}_{arquivo}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Arquivos-Incluidos": str(incluidos),
        },
    )


@router.post("/upload-em-massa")
async def upload_em_massa(
    arquivo: UploadFile = File(..., description="ZIP com XMLs ou um único XML"),
    empresa_id_fallback: int | None = Form(
        None,
        description="ID da empresa para roteamento se XML não tiver CNPJ cadastrado (opcional)",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Importa XMLs em massa via ZIP ou arquivo individual.

    Fluxo:
    1. Aceita ZIP com múltiplos XMLs OU 1 XML individual
    2. Detecta NFe/NFCe/CTe/NFSe pelo root XML
    3. Identifica empresa via CNPJ emitente OU destinatário
    4. Roteia: emitida (cnpj_emitente == empresa) ou recebida (cnpj_destinatario == empresa)
    5. Persiste com idempotência (constraint unique empresa+tipo+chave)

    Resposta inclui:
    - total_arquivos, persistidos, duplicados, empresa_nao_cadastrada, erros
    - detalhes[] com 1 entrada por arquivo (chave, tipo, empresa, status, mensagem)

    Casos de uso:
    - Upload manual de XMLs exportados do ERP (SAP/Bling/Tiny/etc)
    - Importação retroativa de XMLs históricos
    - Upload do ZIP baixado da SEFAZ-GO (formato <CNPJ>_<inicio>_<fim>_<id>.zip)
    - Agente PAC-Watcher fazendo POST automatizado da pasta watch
    """
    if not arquivo.filename:
        raise HTTPException(status_code=400, detail="Arquivo sem nome")

    content = await arquivo.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    service = UploadXmlService(db)
    nome = arquivo.filename.lower()

    if nome.endswith(".zip"):
        resultado = service.processar_zip(content, empresa_id_fallback=empresa_id_fallback)
    elif nome.endswith(".xml"):
        resultado = service.processar_xmls(
            [(arquivo.filename, content)], empresa_id_fallback=empresa_id_fallback,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Formato nao suportado: {arquivo.filename}. Envie .zip ou .xml",
        )

    return resultado.to_dict()
