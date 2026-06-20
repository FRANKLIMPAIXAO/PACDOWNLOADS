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
    tipo: str = Field("outro", description="guia | relatorio | comunicado | outro")
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
