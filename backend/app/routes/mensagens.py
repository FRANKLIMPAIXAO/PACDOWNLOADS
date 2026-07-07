"""Chat ESCRITÓRIO ↔ CLIENTE (estilo WhatsApp) — lado do ESCRITÓRIO.

A conversa é POR EMPRESA. Aqui a equipe do escritório (get_current_user, rejeita
cliente) lista as conversas, abre a thread de uma empresa e responde. O lado do
CLIENTE fica em `portal.py` (get_current_cliente, escopado pela empresa do token).

`autor` é FIXADO como 'escritorio' nestas rotas — nunca vem do input. Assim não
há como um lado se passar pelo outro.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.empresa import Empresa
from app.models.mensagem_chat import MensagemChat
from app.models.usuario import Usuario
from app.services.auth_service import get_current_user


router = APIRouter(
    prefix="/mensagens",
    tags=["mensagens"],
    dependencies=[Depends(get_current_user)],  # equipe do escritório (rejeita cliente)
)

# Teto do corpo da mensagem — evita abuso/payload gigante. Vale p/ os dois lados.
MAX_CORPO = 5000


class MensagemCreate(BaseModel):
    corpo: str = Field(..., min_length=1, max_length=MAX_CORPO)


def serializar_mensagem(m: MensagemChat) -> dict:
    """Formato único de mensagem, usado pelo escritório E pelo portal."""
    return {
        "id": m.id,
        "autor": m.autor,  # 'escritorio' | 'cliente'
        "autor_nome": m.autor_nome,
        "corpo": m.corpo,
        "lida_escritorio": m.lida_escritorio,
        "lida_cliente": m.lida_cliente,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/conversas")
def listar_conversas(db: Session = Depends(get_db)) -> dict:
    """Caixa de entrada: uma linha por empresa que TEM conversa, com a última
    mensagem e o nº de não lidas (mensagens do CLIENTE que o escritório ainda não
    viu). Ordena pela mais recente — igual WhatsApp."""
    # Última mensagem de cada empresa (maior id por empresa_id).
    sub_last = (
        select(MensagemChat.empresa_id, func.max(MensagemChat.id).label("max_id"))
        .group_by(MensagemChat.empresa_id)
        .subquery()
    )
    ultimas = db.scalars(
        select(MensagemChat).join(sub_last, MensagemChat.id == sub_last.c.max_id)
    ).all()
    if not ultimas:
        return {"conversas": []}

    # Não lidas pelo escritório (mensagens do cliente ainda não vistas).
    nao_lidas = dict(
        db.execute(
            select(MensagemChat.empresa_id, func.count())
            .where(MensagemChat.autor == "cliente", MensagemChat.lida_escritorio.is_(False))
            .group_by(MensagemChat.empresa_id)
        ).all()
    )
    emp_ids = [m.empresa_id for m in ultimas]
    emap = {e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_(emp_ids))).all()}

    conversas = []
    for m in ultimas:
        emp = emap.get(m.empresa_id)
        conversas.append({
            "empresa_id": m.empresa_id,
            "empresa_razao_social": emp.razao_social if emp else f"Empresa #{m.empresa_id}",
            "empresa_cnpj": emp.cnpj if emp else None,
            "ultima_mensagem": m.corpo[:120],
            "ultimo_autor": m.autor,
            "ultima_em": m.created_at.isoformat() if m.created_at else None,
            "nao_lidas": int(nao_lidas.get(m.empresa_id, 0)),
        })
    conversas.sort(key=lambda c: c["ultima_em"] or "", reverse=True)
    return {"conversas": conversas}


@router.get("/nao-lidas")
def total_nao_lidas(db: Session = Depends(get_db)) -> dict:
    """Total de mensagens de CLIENTES ainda não lidas pelo escritório (badge)."""
    total = db.scalar(
        select(func.count()).select_from(MensagemChat).where(
            MensagemChat.autor == "cliente", MensagemChat.lida_escritorio.is_(False)
        )
    ) or 0
    return {"total": int(total)}


@router.get("/empresa/{empresa_id}")
def thread_empresa(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Abre a conversa de uma empresa. Marca as mensagens do CLIENTE como lidas
    pelo escritório (quem abre a thread zera o não-lido do outro lado)."""
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    msgs = list(db.scalars(
        select(MensagemChat)
        .where(MensagemChat.empresa_id == empresa_id)
        .order_by(MensagemChat.id)
    ).all())
    # Marca as do cliente como lidas pelo escritório.
    pendentes = [m for m in msgs if m.autor == "cliente" and not m.lida_escritorio]
    if pendentes:
        for m in pendentes:
            m.lida_escritorio = True
        db.commit()
    return {
        "empresa_id": empresa_id,
        "empresa_razao_social": empresa.razao_social,
        "empresa_cnpj": empresa.cnpj,
        "mensagens": [serializar_mensagem(m) for m in msgs],
    }


@router.post("/empresa/{empresa_id}", status_code=201)
def enviar_para_empresa(
    empresa_id: int,
    payload: MensagemCreate,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """O escritório envia uma mensagem pra empresa. `autor='escritorio'` fixo;
    já nasce lida pelo escritório (foi ele que escreveu)."""
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    corpo = payload.corpo.strip()
    if not corpo:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")
    m = MensagemChat(
        empresa_id=empresa_id,
        autor="escritorio",
        autor_usuario_id=user.id,
        autor_nome=user.nome,
        corpo=corpo,
        lida_escritorio=True,
        lida_cliente=False,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return serializar_mensagem(m)
