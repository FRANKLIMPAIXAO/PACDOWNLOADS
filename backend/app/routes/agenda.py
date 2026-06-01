"""Agenda fiscal (calendario) + alertas consolidados.

Sem tabela proprio — gera eventos derivados de:
- vencimento de CNDs (`certidoes`)
- prazos fiscais recorrentes do mes (DAS, DCTFWeb, GPS, FGTS)
- mensagens eCAC nao lidas (sem prazo, mas conta como alerta)
- certificados Focus a vencer (cobre via campos da empresa quando disponivel)
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.certidao import Certidao
from app.models.empresa import Empresa
from app.models.mensagem_ecac import MensagemEcac
from app.services.auth_service import get_current_user


router = APIRouter(
    prefix="/agenda", tags=["agenda"], dependencies=[Depends(get_current_user)],
)


SeveridadeT = Literal["info", "ok", "warn", "err"]


class EventoAgenda(BaseModel):
    data: date
    titulo: str
    descricao: str | None = None
    tipo: str  # CND | DAS | DCTFWEB | GPS | FGTS | ECAC | OUTRO
    severidade: SeveridadeT
    empresa_id: int | None = None
    empresa_nome: str | None = None


class AlertaItem(BaseModel):
    titulo: str
    descricao: str
    severidade: SeveridadeT
    tipo: str
    empresa_id: int | None = None


class AlertasResposta(BaseModel):
    cnds_vencidas: int
    cnds_a_vencer: int
    mensagens_nao_lidas: int
    empresas_sem_procuracao: int
    itens: list[AlertaItem]


# --- Prazos fiscais recorrentes (regras simples; podem virar tabela depois) ---
# Cada tupla: (dia_do_mes, titulo, tipo, descricao)
PRAZOS_RECORRENTES: list[tuple[int, str, str, str]] = [
    (7,  "FGTS",     "FGTS",     "Recolhimento mensal do FGTS"),
    (15, "DCTFWeb",  "DCTFWEB",  "Transmissao DCTFWeb da competencia anterior"),
    (15, "EFD-Reinf","DCTFWEB",  "Transmissao EFD-Reinf"),
    (20, "DAS",      "DAS",      "Vencimento DAS Simples Nacional"),
    (20, "GPS / INSS","GPS",     "Vencimento GPS / INSS empregado"),
    (25, "PIS/COFINS/IPI", "OUTRO", "DARF PIS/COFINS/IPI"),
]


def _ajusta_dia_util(d: date) -> date:
    """Se cair em sabado/domingo, anda para sexta-feira (regra simples)."""
    weekday = d.weekday()
    if weekday == 5:   # sabado
        return d.replace(day=d.day - 1)
    if weekday == 6:   # domingo
        return d.replace(day=d.day - 2)
    return d


def _parse_mes(mes: str | None) -> tuple[int, int]:
    """Converte 'YYYY-MM' em (ano, mes). Default = mes atual."""
    if mes:
        try:
            ano, m = mes.split("-")
            return int(ano), int(m)
        except (ValueError, AttributeError):
            pass
    today = date.today()
    return today.year, today.month


@router.get("/eventos", response_model=list[EventoAgenda])
def listar_eventos(
    mes: str | None = Query(None, description="YYYY-MM (default: mes atual)"),
    db: Session = Depends(get_db),
) -> list[EventoAgenda]:
    """Lista eventos do calendario fiscal para o mes informado."""
    ano, m = _parse_mes(mes)
    _, last_day = monthrange(ano, m)
    primeiro_dia = date(ano, m, 1)
    ultimo_dia = date(ano, m, last_day)
    eventos: list[EventoAgenda] = []

    # 1) Prazos fiscais recorrentes (uma vez por mes)
    for dia, titulo, tipo, descricao in PRAZOS_RECORRENTES:
        if dia > last_day:
            continue
        d = _ajusta_dia_util(date(ano, m, dia))
        eventos.append(EventoAgenda(
            data=d, titulo=titulo, descricao=descricao,
            tipo=tipo, severidade="info",
        ))

    # 2) CNDs vencendo no mes
    certs = db.scalars(
        select(Certidao).where(
            Certidao.data_validade >= primeiro_dia,
            Certidao.data_validade <= ultimo_dia,
        )
    ).all()
    empresas_dict = {
        e.id: e for e in db.scalars(select(Empresa)).all()
    }
    for cert in certs:
        empresa = empresas_dict.get(cert.empresa_id)
        eventos.append(EventoAgenda(
            data=cert.data_validade,
            titulo=f"CND {cert.tipo.value if hasattr(cert.tipo, 'value') else cert.tipo} vence",
            descricao=f"{empresa.razao_social if empresa else ''} · numero {cert.numero or '—'}",
            tipo="CND",
            severidade="warn",
            empresa_id=cert.empresa_id,
            empresa_nome=empresa.razao_social if empresa else None,
        ))

    eventos.sort(key=lambda e: (e.data, e.tipo))
    return eventos


@router.get("/alertas", response_model=AlertasResposta)
def listar_alertas(db: Session = Depends(get_db)) -> AlertasResposta:
    """Resumo consolidado de alertas para o card no dashboard."""
    hoje = date.today()
    em_30d = date.fromordinal(hoje.toordinal() + 30)

    # CNDs (status calculado em Python, agrupar mais recente por (empresa, tipo))
    todas_certidoes = db.scalars(
        select(Certidao).order_by(Certidao.data_validade.desc())
    ).all()
    mais_recente: dict[tuple[int, str], Certidao] = {}
    for c in todas_certidoes:
        key = (c.empresa_id, c.tipo.value if hasattr(c.tipo, "value") else str(c.tipo))
        if key not in mais_recente:
            mais_recente[key] = c

    cnds_vencidas = sum(1 for c in mais_recente.values() if c.data_validade < hoje)
    cnds_a_vencer = sum(
        1 for c in mais_recente.values()
        if hoje <= c.data_validade <= em_30d
    )

    # Mensagens nao lidas
    mensagens_nao_lidas = len(db.scalars(
        select(MensagemEcac).where(MensagemEcac.indicador_leitura == "0")
    ).all())

    # Empresas ativas sem procuracao registrada
    from app.models.procuracao import Procuracao
    empresas_ids_com_proc = {
        p.empresa_id for p in db.scalars(select(Procuracao)).all()
        if (p.situacao or "").upper() == "ATIVA"
    }
    empresas_ativas = db.scalars(
        select(Empresa).where(Empresa.ativo.is_(True))
    ).all()
    empresas_sem_procuracao = len([
        e for e in empresas_ativas if e.id not in empresas_ids_com_proc
    ])

    # Constroi itens para exibicao (top 12)
    itens: list[AlertaItem] = []
    empresas_dict = {e.id: e for e in empresas_ativas}

    # CNDs vencidas/a vencer
    for c in sorted(mais_recente.values(), key=lambda c: c.data_validade):
        empresa = empresas_dict.get(c.empresa_id)
        nome = empresa.razao_social if empresa else f"#{c.empresa_id}"
        tipo_label = c.tipo.value if hasattr(c.tipo, "value") else str(c.tipo)
        if c.data_validade < hoje:
            dias = (hoje - c.data_validade).days
            itens.append(AlertaItem(
                titulo=f"CND {tipo_label} vencida ha {dias}d",
                descricao=nome,
                severidade="err",
                tipo="CND",
                empresa_id=c.empresa_id,
            ))
        elif c.data_validade <= em_30d:
            dias = (c.data_validade - hoje).days
            itens.append(AlertaItem(
                titulo=f"CND {tipo_label} vence em {dias}d",
                descricao=nome,
                severidade="warn",
                tipo="CND",
                empresa_id=c.empresa_id,
            ))
        if len(itens) >= 12:
            break

    if len(itens) < 12 and mensagens_nao_lidas:
        itens.append(AlertaItem(
            titulo=f"{mensagens_nao_lidas} mensagem(ns) nao lida(s) no eCAC",
            descricao="Acesse Prevencao para revisar",
            severidade="info",
            tipo="ECAC",
        ))

    if len(itens) < 12 and empresas_sem_procuracao:
        itens.append(AlertaItem(
            titulo=f"{empresas_sem_procuracao} empresa(s) sem procuracao ativa",
            descricao="Sincronize a procuracao em /prevencao",
            severidade="warn",
            tipo="PROCURACAO",
        ))

    return AlertasResposta(
        cnds_vencidas=cnds_vencidas,
        cnds_a_vencer=cnds_a_vencer,
        mensagens_nao_lidas=mensagens_nao_lidas,
        empresas_sem_procuracao=empresas_sem_procuracao,
        itens=itens,
    )
