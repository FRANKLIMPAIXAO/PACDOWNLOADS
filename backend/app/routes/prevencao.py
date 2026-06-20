"""Prevenção — visão consolidada da SAÚDE FISCAL da carteira (estilo Jettax).

Agrega, em UMA chamada, o que o PAC já tem estruturado:
- Situação fiscal (regular/pendências) da certidão FEDERAL (SITFIS) por empresa;
- Débitos: DAS atrasadas (saldo + nº de guias vencidas);
- Parcelamento ativo (PGFN).

A equipe abre a tela e tria POR EXCEÇÃO: mexe só em quem tem pendência/débito,
sem entrar empresa por empresa. Filtros e ordenação ficam no frontend (1 request).
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.certidao import Certidao, TipoCertidao
from app.models.empresa import Empresa
from app.models.guia_das import GuiaDAS
from app.services.auth_service import get_current_user

router = APIRouter(
    prefix="/prevencao",
    tags=["prevencao"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/situacao-fiscal")
def situacao_fiscal_carteira(db: Session = Depends(get_db)) -> dict:
    """Saúde fiscal da carteira inteira, consolidada por empresa + totais."""
    empresas = db.scalars(
        select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.razao_social)
    ).all()

    # Situação fiscal: certidão FEDERAL (SITFIS) MAIS RECENTE por empresa.
    fed: dict[int, Certidao] = {}
    for c in db.scalars(
        select(Certidao)
        .where(Certidao.tipo == TipoCertidao.FEDERAL)
        .order_by(Certidao.created_at.desc())
    ).all():
        fed.setdefault(c.empresa_id, c)

    # Débitos: DAS atrasadas agregadas por empresa (saldo + contagem).
    deb: dict[int, dict] = defaultdict(lambda: {"saldo": 0.0, "qtd": 0})
    for g in db.scalars(select(GuiaDAS).where(GuiaDAS.situacao == "atrasada")).all():
        valor = g.valor_atualizado if g.valor_atualizado is not None else g.valor_principal
        deb[g.empresa_id]["saldo"] += float(valor or 0)
        deb[g.empresa_id]["qtd"] += 1

    # Parcelamento ativo (PGFN). Import tardio — modelo opcional.
    parc_ids: set[int] = set()
    try:
        from app.models.parcelamento_pgfn import ParcelamentoPgfn
        parc_ids = set(db.scalars(select(ParcelamentoPgfn.empresa_id)).all())
    except Exception:  # noqa: BLE001 — sem o modelo/tabela, segue sem parcelamento
        parc_ids = set()

    linhas: list[dict] = []
    tot = {
        "empresas": len(empresas),
        "regular": 0, "com_pendencia": 0, "a_verificar": 0, "sem_dado": 0,
        "empresas_com_debito": 0, "saldo_devedor": 0.0, "guias_vencidas": 0,
        "empresas_com_parcelamento": 0,
    }

    for e in empresas:
        cert = fed.get(e.id)
        situacao, pendencias = cert.regularidade() if cert else (None, [])
        d = deb.get(e.id, {"saldo": 0.0, "qtd": 0})
        saldo = round(d["saldo"], 2)
        venc = d["qtd"]
        tem_parc = e.id in parc_ids

        if situacao == "regular":
            tot["regular"] += 1
        elif situacao == "pendencias":
            tot["com_pendencia"] += 1
        elif situacao == "verificar":
            tot["a_verificar"] += 1
        else:
            tot["sem_dado"] += 1
        if saldo > 0:
            tot["empresas_com_debito"] += 1
            tot["saldo_devedor"] += saldo
            tot["guias_vencidas"] += venc
        if tem_parc:
            tot["empresas_com_parcelamento"] += 1

        linhas.append({
            "empresa_id": e.id,
            "razao_social": e.razao_social,
            "cnpj": e.cnpj,
            "regime": e.regime_tributario,
            "situacao_fiscal": situacao,
            "pendencias": pendencias,
            "saldo_devedor": saldo,
            "guias_vencidas": venc,
            "tem_parcelamento": tem_parc,
            "tem_situacao": cert is not None,
        })

    # Ordena pra triagem: quem tem PROBLEMA primeiro (pendência > débito > resto),
    # e dentro disso pelo maior saldo devedor.
    def _peso(l: dict) -> tuple:
        prob = (
            2 if l["situacao_fiscal"] == "pendencias"
            else 1 if l["saldo_devedor"] > 0 or l["situacao_fiscal"] == "verificar"
            else 0
        )
        return (-prob, -l["saldo_devedor"], l["razao_social"].lower())

    linhas.sort(key=_peso)
    tot["saldo_devedor"] = round(tot["saldo_devedor"], 2)
    return {"totais": tot, "empresas": linhas}
