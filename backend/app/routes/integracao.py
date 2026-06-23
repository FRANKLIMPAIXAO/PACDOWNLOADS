"""Integração máquina-a-máquina: o PAC TAREFAS entrega documentos ao cliente.

Autenticado por API key (header `X-API-Key` = env `INTEGRACAO_API_KEY`). O doc
cai na área do cliente (DocumentoEscritorio) e o endpoint devolve o LINK do
portal pra o PAC TAREFAS incluir no e-mail que ele já manda. Sem SMTP no PAC.
"""
from __future__ import annotations

import base64
import hmac
import os
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.documento_escritorio import DocumentoEscritorio
from app.models.empresa import Empresa

router = APIRouter(prefix="/integracao", tags=["integracao"])

_settings = get_settings()


def _checar_api_key(x_api_key: str = Header(default="")) -> None:
    esperado = os.getenv("INTEGRACAO_API_KEY", "")
    if not esperado:
        raise HTTPException(status_code=503, detail="INTEGRACAO_API_KEY não configurada no servidor.")
    if not x_api_key or not hmac.compare_digest(x_api_key, esperado):
        # compare_digest = comparação de tempo constante (anti timing-attack)
        raise HTTPException(status_code=401, detail="API key inválida.")


class EntregarDocumento(BaseModel):
    cnpj: str = Field(..., description="CNPJ do cliente (com ou sem máscara)")
    tipo: str = Field(
        "outro",
        description=(
            "Operacional: guia | relatorio | comunicado | outro. "
            "Cadastral (vai no card 'Documentos da empresa' do portal): contrato | "
            "contrato_social | alteracao_contratual | estatuto | ata | alvara | "
            "licenca | certificado | procuracao | inscricao | cartao_cnpj | documento. "
            "Para 'certificado', mande `vencimento` = validade do certificado."
        ),
    )
    titulo: str = Field(..., max_length=255)
    mensagem: str | None = None
    competencia: str | None = Field(None, description="AAAA-MM (guias)")
    vencimento: date | None = None
    valor: float | None = None
    arquivo_base64: str | None = Field(None, description="PDF/arquivo em base64 (opcional p/ comunicado)")
    nome_arquivo: str | None = None


@router.post("/documentos", dependencies=[Depends(_checar_api_key)])
def entregar_documento(payload: EntregarDocumento, db: Session = Depends(get_db)) -> dict:
    """Entrega UM documento na área do cliente. Idempotência fica a cargo do
    PAC TAREFAS (cada chamada cria um registro novo)."""
    cnpj = re.sub(r"\D", "", payload.cnpj or "")
    if len(cnpj) != 14:
        raise HTTPException(status_code=400, detail="CNPJ inválido (esperado 14 dígitos).")
    empresa = db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
    if not empresa:
        raise HTTPException(status_code=404, detail=f"Empresa com CNPJ {cnpj} não encontrada no PAC.")

    doc = DocumentoEscritorio(
        empresa_id=empresa.id,
        tipo=(payload.tipo or "outro").strip().lower()[:30],
        titulo=payload.titulo.strip(),
        mensagem=payload.mensagem,
        competencia=payload.competencia,
        vencimento=payload.vencimento,
        valor=payload.valor,
        origem="pac_tarefas",
    )
    db.add(doc)
    db.flush()  # pega o id antes de nomear o arquivo

    if payload.arquivo_base64:
        try:
            raw = base64.b64decode(payload.arquivo_base64, validate=True)
        except Exception:  # noqa: BLE001
            db.rollback()
            raise HTTPException(status_code=400, detail="arquivo_base64 inválido.")
        nome = re.sub(r"[^A-Za-z0-9._-]", "_", (payload.nome_arquivo or f"doc_{doc.id}.pdf"))[:255]
        pasta = Path(_settings.storage_path) / "escritorio" / cnpj
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{doc.id}_{nome}"
        caminho.write_bytes(raw)
        doc.arquivo_path = str(caminho)
        doc.nome_arquivo = nome

    db.commit()
    db.refresh(doc)

    portal_base = os.getenv("PORTAL_URL", "https://pacdownloads-frontend.ibm21x.easypanel.host").rstrip("/")
    return {
        "id": doc.id,
        "empresa_id": empresa.id,
        "empresa": empresa.razao_social,
        "portal_url": f"{portal_base}/portal",
        "mensagem": "Documento entregue na área do cliente.",
    }


# ---------------------------------------------------------------------------
# Solicitações de ADMISSÃO — o PAC TAREFAS baixa os anexos e atualiza o status.
# (A solicitação em si chega via WEBHOOK; aqui é o suporte: anexos + status.)
# ---------------------------------------------------------------------------
@router.get("/admissoes/{solicitacao_id}/anexo/{indice}", dependencies=[Depends(_checar_api_key)])
def baixar_anexo_admissao(solicitacao_id: int, indice: int, db: Session = Depends(get_db)):
    """Baixa um anexo de uma solicitação de admissão (link enviado no webhook)."""
    import json as _json

    from fastapi.responses import FileResponse
    from app.models.solicitacao_admissao import SolicitacaoAdmissao

    sol = db.get(SolicitacaoAdmissao, solicitacao_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    try:
        anexos = _json.loads(sol.anexos) if sol.anexos else []
    except Exception:  # noqa: BLE001
        anexos = []
    if indice < 0 or indice >= len(anexos):
        raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    meta = anexos[indice]
    caminho = Path(meta.get("path") or "")
    if not caminho or not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo do anexo não está mais disponível.")
    nome = meta.get("nome") or caminho.name
    return FileResponse(path=str(caminho), filename=nome, media_type="application/octet-stream")


class AtualizarStatusAdmissao(BaseModel):
    status: str = Field(..., description="nova | em_analise | concluida | cancelada")


@router.patch("/admissoes/{solicitacao_id}/status", dependencies=[Depends(_checar_api_key)])
def atualizar_status_admissao(
    solicitacao_id: int, payload: AtualizarStatusAdmissao, db: Session = Depends(get_db),
) -> dict:
    """O PAC TAREFAS atualiza o status da solicitação (fecha o ciclo p/ o cliente
    acompanhar no portal)."""
    from app.models.solicitacao_admissao import SolicitacaoAdmissao

    validos = {"nova", "em_analise", "concluida", "cancelada"}
    if payload.status not in validos:
        raise HTTPException(status_code=400, detail=f"Status inválido. Use: {sorted(validos)}")
    sol = db.get(SolicitacaoAdmissao, solicitacao_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    sol.status = payload.status
    db.commit()
    return {"id": sol.id, "status": sol.status}
