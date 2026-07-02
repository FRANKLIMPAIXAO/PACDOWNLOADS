"""Prevenção — visão consolidada da SAÚDE FISCAL da carteira (estilo Jettax).

Agrega, em UMA chamada, o que o PAC já tem estruturado:
- Situação fiscal (regular/pendências) da certidão FEDERAL (SITFIS) por empresa;
- Débitos: DAS atrasadas (saldo + nº de guias vencidas);
- Parcelamento ativo (PGFN).

A equipe abre a tela e tria POR EXCEÇÃO: mexe só em quem tem pendência/débito,
sem entrar empresa por empresa. Filtros e ordenação ficam no frontend (1 request).
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.certidao import Certidao, TipoCertidao
from app.models.empresa import Empresa
from app.models.guia_das import GuiaDAS
from app.services.auth_service import get_current_user

logger = logging.getLogger("pac.prevencao")

router = APIRouter(
    prefix="/prevencao",
    tags=["prevencao"],
    dependencies=[Depends(get_current_user)],
)

# Job em memória (eager, --workers 1) pra atualização do SITFIS da carteira.
# Cada SITFIS leva ~30-60s via Integra → 100+ empresas = ~1-2h → tem que ser
# background com polling (o request sync estouraria o Traefik 60s).
_SITFIS_JOBS: dict[str, dict] = {}
_SITFIS_LOCK = threading.Lock()


def _job_rodando() -> str | None:
    with _SITFIS_LOCK:
        for jid, j in _SITFIS_JOBS.items():
            if j.get("status") == "rodando":
                return jid
    return None


def _rodar_atualizacao_sitfis(job_id: str) -> None:
    """Puxa o SITFIS (situação fiscal FEDERAL) de TODAS as empresas ativas via
    Integra Contador, sequencial. Atualiza o progresso no dict compartilhado.
    Resiliente: erro numa empresa NÃO derruba o lote."""
    from app.services.cnd_robo_service import CndRoboService

    db = SessionLocal()
    try:
        empresas = db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.razao_social)
        ).all()
        svc = CndRoboService(db)
        with _SITFIS_LOCK:
            _SITFIS_JOBS[job_id]["total"] = len(empresas)
        for emp in empresas:
            with _SITFIS_LOCK:
                _SITFIS_JOBS[job_id]["atual"] = emp.razao_social
            try:
                svc.renovar_cnd(emp.id, "FEDERAL")  # type: ignore[arg-type]
                with _SITFIS_LOCK:
                    _SITFIS_JOBS[job_id]["sucesso"] += 1
            except Exception as exc:  # noqa: BLE001 — uma falha não para o lote
                logger.warning("SITFIS falhou empresa %s: %s", emp.id, exc)
                with _SITFIS_LOCK:
                    _SITFIS_JOBS[job_id]["falhas"] += 1
                    erros = _SITFIS_JOBS[job_id]["erros"]
                    if len(erros) < 50:
                        erros.append({"empresa": emp.razao_social, "erro": str(exc)[:200]})
            finally:
                with _SITFIS_LOCK:
                    _SITFIS_JOBS[job_id]["feitas"] += 1
        with _SITFIS_LOCK:
            _SITFIS_JOBS[job_id]["status"] = "concluido"
            _SITFIS_JOBS[job_id]["atual"] = None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Atualização SITFIS da carteira falhou")
        with _SITFIS_LOCK:
            _SITFIS_JOBS[job_id]["status"] = "erro"
            _SITFIS_JOBS[job_id]["erro_geral"] = str(exc)[:300]
    finally:
        db.close()


@router.post("/atualizar-situacao-fiscal")
def atualizar_situacao_fiscal(db: Session = Depends(get_db)) -> dict:
    """Dispara, em BACKGROUND, a atualização do SITFIS de toda a carteira (puxa
    a situação fiscal FEDERAL via Integra Contador). Responde na hora com job_id;
    o front faz polling em /atualizar-situacao-fiscal/status/{job_id}.

    Só 1 job por vez (evita gasto dobrado no Integra)."""
    rodando = _job_rodando()
    if rodando:
        return {"job_id": rodando, "ja_rodando": True}
    job_id = uuid.uuid4().hex
    with _SITFIS_LOCK:
        _SITFIS_JOBS[job_id] = {
            "status": "rodando", "total": 0, "feitas": 0,
            "sucesso": 0, "falhas": 0, "atual": None, "erros": [],
            "iniciado_em": datetime.now(timezone.utc).isoformat(),
        }
    threading.Thread(
        target=_rodar_atualizacao_sitfis, args=(job_id,), daemon=True,
    ).start()
    return {"job_id": job_id, "ja_rodando": False}


@router.get("/atualizar-situacao-fiscal/status/{job_id}")
def status_atualizacao_sitfis(job_id: str) -> dict:
    with _SITFIS_LOCK:
        job = _SITFIS_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job não encontrado (pode ter reiniciado).")
        return dict(job)


# --- Caixa Postal (mensagens e-CAC) da carteira: sync background + agregação ---
_MSG_JOBS: dict[str, dict] = {}
_MSG_LOCK = threading.Lock()


def _msg_job_rodando() -> str | None:
    with _MSG_LOCK:
        for jid, j in _MSG_JOBS.items():
            if j.get("status") == "rodando":
                return jid
    return None


def _rodar_sync_mensagens(job_id: str) -> None:
    """Sincroniza a Caixa Postal (mensagens e-CAC) de TODAS as ativas via Integra
    (MSGCONTRIBUINTE61), sequencial. Resiliente: erro numa empresa não para o lote."""
    from app.services.integra_contador_service import IntegraContadorService

    db = SessionLocal()
    try:
        empresas = db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.razao_social)
        ).all()
        svc = IntegraContadorService(db)
        with _MSG_LOCK:
            _MSG_JOBS[job_id]["total"] = len(empresas)
        for emp in empresas:
            with _MSG_LOCK:
                _MSG_JOBS[job_id]["atual"] = emp.razao_social
            try:
                svc.sync_caixa_postal(emp.id)
                with _MSG_LOCK:
                    _MSG_JOBS[job_id]["sucesso"] += 1
            except Exception as exc:  # noqa: BLE001 — uma falha não para o lote
                logger.warning("Sync caixa postal falhou empresa %s: %s", emp.id, exc)
                with _MSG_LOCK:
                    _MSG_JOBS[job_id]["falhas"] += 1
                    erros = _MSG_JOBS[job_id]["erros"]
                    if len(erros) < 50:
                        erros.append({"empresa": emp.razao_social, "erro": str(exc)[:200]})
            finally:
                with _MSG_LOCK:
                    _MSG_JOBS[job_id]["feitas"] += 1
        with _MSG_LOCK:
            _MSG_JOBS[job_id]["status"] = "concluido"
            _MSG_JOBS[job_id]["atual"] = None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Sync mensagens da carteira falhou")
        with _MSG_LOCK:
            _MSG_JOBS[job_id]["status"] = "erro"
            _MSG_JOBS[job_id]["erro_geral"] = str(exc)[:300]
    finally:
        db.close()


@router.post("/atualizar-mensagens")
def atualizar_mensagens() -> dict:
    """Dispara em BACKGROUND a sincronização da Caixa Postal (e-CAC) de toda a
    carteira via Integra Contador. CUSTA chamadas Integra. 1 job por vez.
    Front faz polling em /atualizar-mensagens/status/{job_id}."""
    rodando = _msg_job_rodando()
    if rodando:
        return {"job_id": rodando, "ja_rodando": True}
    job_id = uuid.uuid4().hex
    with _MSG_LOCK:
        _MSG_JOBS[job_id] = {
            "status": "rodando", "total": 0, "feitas": 0,
            "sucesso": 0, "falhas": 0, "atual": None, "erros": [],
            "iniciado_em": datetime.now(timezone.utc).isoformat(),
        }
    threading.Thread(target=_rodar_sync_mensagens, args=(job_id,), daemon=True).start()
    return {"job_id": job_id, "ja_rodando": False}


@router.get("/atualizar-mensagens/status/{job_id}")
def status_atualizar_mensagens(job_id: str) -> dict:
    with _MSG_LOCK:
        job = _MSG_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job não encontrado (pode ter reiniciado).")
        return dict(job)


def _classificar_mensagem(assunto: str) -> str:
    """Classifica a mensagem e-CAC por TIPO pelo assunto (estilo Jettax)."""
    a = (assunto or "").lower()
    if "exclus" in a:
        return "Termo de Exclusão SN"
    if "intima" in a:
        return "Termo de Intimação"
    if "malha" in a:
        return "Malha Fiscal"
    if "pronampe" in a:
        return "Pronampe"
    if "parcela" in a:
        return "Parcelamento"
    return "e-CAC (outras)"


@router.get("/mensagens-resumo")
def mensagens_resumo(db: Session = Depends(get_db)) -> dict:
    """Agrega as mensagens da Caixa Postal (e-CAC) de TODA a carteira, classificadas
    por TIPO. Alimenta a aba Mensagens do /prevencao (cards + lista filtrável)."""
    from app.models.mensagem_ecac import MensagemEcac

    rows = db.execute(
        select(
            MensagemEcac.empresa_id, Empresa.razao_social, Empresa.cnpj,
            MensagemEcac.assunto, MensagemEcac.indicador_leitura,
            MensagemEcac.indicador_relevancia, MensagemEcac.data_envio,
            MensagemEcac.isn_msg,
        )
        .join(Empresa, Empresa.id == MensagemEcac.empresa_id)
        .order_by(MensagemEcac.data_envio.desc().nullslast())
    ).all()

    tipos: dict[str, dict] = {}
    itens: list[dict] = []
    for empresa_id, razao, cnpj, assunto, leitura, relev, data_envio, isn in rows:
        tipo = _classificar_mensagem(assunto or "")
        d = tipos.setdefault(
            tipo,
            {"tipo": tipo, "total": 0, "nao_lidas": 0, "relevantes_nao_lidas": 0, "_emp": set()},
        )
        d["total"] += 1
        d["_emp"].add(empresa_id)
        nao_lida = leitura != "1"
        if nao_lida:
            d["nao_lidas"] += 1
            if relev == "1":
                d["relevantes_nao_lidas"] += 1
        if len(itens) < 400:  # amostra (mais recentes) pra lista; front filtra
            itens.append({
                "empresa_id": empresa_id, "empresa": razao, "cnpj": cnpj, "tipo": tipo,
                "assunto": assunto, "nao_lida": nao_lida, "relevante": relev == "1",
                "data_envio": data_envio.isoformat() if data_envio else None, "isn_msg": isn,
            })

    resumo = []
    for d in tipos.values():
        d["empresas"] = len(d.pop("_emp"))
        resumo.append(d)
    resumo.sort(key=lambda x: (x["relevantes_nao_lidas"], x["nao_lidas"], x["total"]), reverse=True)
    return {
        "total_mensagens": sum(d["total"] for d in resumo),
        "total_nao_lidas": sum(d["nao_lidas"] for d in resumo),
        "total_relevantes_nao_lidas": sum(d["relevantes_nao_lidas"] for d in resumo),
        "por_tipo": resumo,
        "mensagens": itens,
    }


def _tipo_omissao(pendencia: str) -> str | None:
    """Se a pendência é uma OMISSÃO de declaração, devolve o tipo canônico
    (DCTFWeb, DASN, DEFIS…). Senão (débito, parcelamento, inscrição), None.
    O SITFIS escreve 'Omissão de <declaração>'."""
    p = (pendencia or "").lower()
    if "omiss" not in p:
        return None
    if "dctfweb" in p or "dctf-web" in p or "dctf web" in p:
        return "DCTFWeb"
    if "dasn" in p or "simei" in p:
        return "DASN"
    if "defis" in p:
        return "DEFIS"
    if "dirf" in p:
        return "DIRF"
    if "ecf" in p:
        return "ECF"
    if "efd" in p or "contribui" in p:
        return "EFD-Contrib"
    if "pgdas" in p:
        return "PGDAS"
    if "dctf" in p:
        return "DCTF"
    return "Outras"


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
    # Ausência de declarações (omissões), por tipo — Fase 2.
    aus_por_tipo: dict[str, int] = defaultdict(int)
    aus_empresas = 0
    aus_total = 0

    for e in empresas:
        cert = fed.get(e.id)
        situacao, pendencias = cert.regularidade() if cert else (None, [])
        d = deb.get(e.id, {"saldo": 0.0, "qtd": 0})
        saldo = round(d["saldo"], 2)
        venc = d["qtd"]
        tem_parc = e.id in parc_ids

        # Quais declarações esta empresa está OMITINDO (das pendências do SITFIS).
        ausencias_emp = sorted({t for p in pendencias if (t := _tipo_omissao(p))})
        if ausencias_emp:
            aus_empresas += 1
            aus_total += len(ausencias_emp)
            for t in ausencias_emp:
                aus_por_tipo[t] += 1

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
            "ausencias": ausencias_emp,
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
    ausencias = {
        "empresas": aus_empresas,
        "total": aus_total,
        "por_tipo": dict(sorted(aus_por_tipo.items(), key=lambda kv: -kv[1])),
    }
    return {"totais": tot, "ausencias": ausencias, "empresas": linhas}
