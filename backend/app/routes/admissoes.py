"""Solicitações de admissão — visão do ESCRITÓRIO.

Lista as admissões que os clientes enviaram pelo portal e dá o controle de
REENVIO ao PAC TAREFAS (rede de segurança quando o webhook falhou). Listar:
qualquer usuário do escritório; reenviar: admin (ação que dispara integração)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.empresa import Empresa
from app.models.solicitacao_admissao import SolicitacaoAdmissao
from app.models.usuario import Usuario
from app.services.admissao_service import AdmissaoService
from app.services.auth_service import get_current_admin, get_current_user

router = APIRouter(
    prefix="/admissoes", tags=["admissoes"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def listar(empresa_id: int | None = None, limite: int = 200, db: Session = Depends(get_db)) -> dict:
    """Admissões enviadas pelos clientes (mais recentes primeiro)."""
    stmt = select(SolicitacaoAdmissao).order_by(desc(SolicitacaoAdmissao.criado_em))
    if empresa_id:
        stmt = stmt.where(SolicitacaoAdmissao.empresa_id == empresa_id)
    sols = list(db.scalars(stmt.limit(max(1, min(limite, 500)))).all())
    emap = {e.id: e for e in db.scalars(
        select(Empresa).where(Empresa.id.in_({s.empresa_id for s in sols}))
    ).all()} if sols else {}
    pendentes = sum(1 for s in sols if not s.enviado_pactarefas and s.status != "cancelada")
    return {
        "pendentes_envio": pendentes,
        "admissoes": [
            {
                "id": s.id,
                "empresa": emap[s.empresa_id].razao_social if s.empresa_id in emap else None,
                "cnpj": emap[s.empresa_id].cnpj if s.empresa_id in emap else None,
                "funcionario": s.funcionario_nome,
                "cpf": s.funcionario_cpf,
                "cargo": s.cargo,
                "data_admissao": s.data_admissao.isoformat() if s.data_admissao else None,
                "status": s.status,
                "enviado": s.enviado_pactarefas,
                "envio_erro": s.envio_erro,
                "anexos": len(json.loads(s.anexos)) if s.anexos else 0,
                "criado_em": s.criado_em.isoformat() if s.criado_em else None,
            }
            for s in sols
        ],
    }


@router.post("/{solicitacao_id}/reenviar")
def reenviar(
    solicitacao_id: int,
    admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Reenvia UMA admissão ao PAC TAREFAS (webhook). Admin-only."""
    sol = db.get(SolicitacaoAdmissao, solicitacao_id)
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    empresa = db.get(Empresa, sol.empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    ok = AdmissaoService(db).enviar_webhook(sol, empresa)
    return {"id": sol.id, "enviado": ok, "erro": sol.envio_erro if not ok else None}


@router.post("/reenviar-pendentes")
def reenviar_pendentes(
    admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Reenvia TODAS as admissões pendentes de envio. Admin-only."""
    return AdmissaoService(db).reenviar_pendentes(limite=100)
