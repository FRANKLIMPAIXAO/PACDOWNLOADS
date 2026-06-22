"""Gestão (ESCRITÓRIO) dos documentos entregues ao cliente.

Os documentos vêm do PAC TAREFAS (/integracao/documentos) e aparecem na área do
cliente. Aqui o escritório LISTA e EXCLUI os que foram enviados errado. Listar:
qualquer usuário do escritório; EXCLUIR: só admin (ação destrutiva)."""
from __future__ import annotations

import logging
from pathlib import Path as _Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.documento_escritorio import DocumentoEscritorio
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.services.auth_service import get_current_admin, get_current_user

logger = logging.getLogger("pac.docs_escritorio")

router = APIRouter(
    prefix="/docs-escritorio", tags=["docs-escritorio"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def listar(
    empresa_id: int | None = None,
    limite: int = 300,
    db: Session = Depends(get_db),
) -> dict:
    """Documentos entregues ao cliente (mais recentes primeiro). Filtra por empresa."""
    stmt = select(DocumentoEscritorio).order_by(desc(DocumentoEscritorio.enviado_em))
    if empresa_id:
        stmt = stmt.where(DocumentoEscritorio.empresa_id == empresa_id)
    docs = list(db.scalars(stmt.limit(max(1, min(limite, 1000)))).all())
    emap = {e.id: e for e in db.scalars(
        select(Empresa).where(Empresa.id.in_({d.empresa_id for d in docs}))
    ).all()} if docs else {}
    return {
        "documentos": [
            {
                "id": d.id,
                "empresa_id": d.empresa_id,
                "empresa": emap[d.empresa_id].razao_social if d.empresa_id in emap else None,
                "cnpj": emap[d.empresa_id].cnpj if d.empresa_id in emap else None,
                "tipo": d.tipo,
                "titulo": d.titulo,
                "competencia": d.competencia,
                "vencimento": d.vencimento.isoformat() if d.vencimento else None,
                "valor": float(d.valor) if d.valor is not None else None,
                "tem_arquivo": bool(d.arquivo_path),
                "enviado_em": d.enviado_em.isoformat() if d.enviado_em else None,
                "lido": d.lido_em is not None,
                "origem": d.origem,
            }
            for d in docs
        ],
    }


@router.delete("/{doc_id}")
def excluir(
    doc_id: int,
    admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """EXCLUI um documento da área do cliente (enviado errado). Admin-only. Apaga o
    arquivo do disco também. Auditoria: quem excluiu o quê."""
    doc = db.get(DocumentoEscritorio, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    titulo, empresa_id = doc.titulo, doc.empresa_id
    # apaga o arquivo (best-effort — nunca derruba a exclusão do registro)
    if doc.arquivo_path:
        try:
            p = _Path(doc.arquivo_path)
            if p.exists():
                p.unlink()
        except OSError:
            logger.warning("Não consegui apagar o arquivo %s", doc.arquivo_path)
    db.delete(doc)
    db.commit()
    logger.info("AUDITORIA docs-escritorio EXCLUSAO: admin=%s doc=%s empresa=%s titulo=%r",
                admin.email, doc_id, empresa_id, titulo)
    return {"ok": True, "id": doc_id}
