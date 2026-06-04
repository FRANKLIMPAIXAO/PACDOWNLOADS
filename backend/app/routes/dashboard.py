"""Dashboard agregado — endpoint unico que retorna metricas reais
do escritorio pra a tela inicial.

Tudo agregado no servidor pra evitar baixar listas grandes no frontend.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.certidao import Certidao
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.models.execucao_robo_sefaz import ExecucaoRoboSefaz
from app.models.guia_das import GuiaDAS
from app.models.guia_dctfweb import GuiaDctfweb
from app.models.guia_fgts import GuiaFgts
from app.models.mensagem_ecac import MensagemEcac
from app.models.parcelamento_pgfn import ParcelamentoPgfn
from app.models.parcelamento_simples import ParcelamentoSimples
from app.services.auth_service import get_current_user


router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


def _decimal_to_float(v: Decimal | None) -> float:
    if v is None:
        return 0.0
    return float(v)


@router.get("/resumo")
def resumo_dashboard(
    mes: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Retorna metricas agregadas pra dashboard.

    Parametros:
        mes: 'YYYY-MM' ou None (default = mes atual)

    Estrutura:
        {
            "mes": "2026-05",
            "empresas": {total, ativas, sem_focus_token, sem_cert_a1},
            "documentos_mes": {total, baixados, canceladas, valor_total, ...},
            "manifestacao": {pendentes, manifestadas},
            "cnds": {vencendo_30d, vencidas},
            "ecac": {nao_lidas, alta_nao_lidas},
            "certificados": {vencendo_60d, vencidos},
            "top_fornecedores": [{cnpj, nome, valor, qtd}, ...],
        }
    """
    hoje = date.today()
    if mes:
        ano, m = mes.split("-")
        ref_ano, ref_mes = int(ano), int(m)
    else:
        ref_ano, ref_mes = hoje.year, hoje.month

    inicio_mes = datetime(ref_ano, ref_mes, 1, tzinfo=timezone.utc)
    if ref_mes == 12:
        fim_mes = datetime(ref_ano + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fim_mes = datetime(ref_ano, ref_mes + 1, 1, tzinfo=timezone.utc)

    # --- Empresas ---
    empresas = db.scalars(select(Empresa)).all()
    emp_total = len(empresas)
    emp_ativas = sum(1 for e in empresas if e.ativo)
    emp_sem_token = sum(1 for e in empresas if e.ativo and not e.focus_token)
    emp_sem_cert = sum(1 for e in empresas if e.ativo and not e.cert_a1_path)

    # --- Documentos do mes ---
    # Separa EMITIDAS (saida — faturamento real) de RECEBIDAS (entrada).
    # Faturamento = valor das emitidas ativas (o que a empresa vendeu).
    docs_q = select(
        func.count(DocumentoFiscal.id).label("total"),
        func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor_total"),
        func.sum(case((DocumentoFiscal.cancelada == True, 1), else_=0)).label("canceladas"),  # noqa: E712
        # Emitidas (saida)
        func.sum(case((DocumentoFiscal.origem == "emitida", 1), else_=0)).label("emitidas"),
        func.sum(case((DocumentoFiscal.origem == "recebida", 1), else_=0)).label("recebidas"),
        # Faturamento = emitidas ativas
        func.coalesce(func.sum(case(
            ((DocumentoFiscal.origem == "emitida") & (DocumentoFiscal.cancelada == False),  # noqa: E712
             DocumentoFiscal.valor_total),
            else_=0,
        )), 0).label("faturamento"),
    ).where(
        DocumentoFiscal.data_emissao >= inicio_mes,
        DocumentoFiscal.data_emissao < fim_mes,
    )
    docs_row = db.execute(docs_q).one()

    # Documentos totais (todos os meses)
    total_geral = db.scalar(select(func.count(DocumentoFiscal.id))) or 0

    # --- Pendentes de manifestacao ---
    # Considera pendente: NFe recebida sem `json_original.manifestado_em`.
    # SQLite/JSON1: usa json_extract.
    pendentes_q = db.scalars(
        select(DocumentoFiscal).where(
            DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
            DocumentoFiscal.origem == "recebida",
            DocumentoFiscal.cancelada == False,
        )
    ).all()
    pendentes = sum(
        1 for d in pendentes_q
        if not (d.json_original or {}).get("manifestado_em")
    )
    manifestadas = sum(
        1 for d in pendentes_q
        if (d.json_original or {}).get("manifestado_em")
    )

    # --- CNDs vencendo / vencidas ---
    limite_cnd = hoje + timedelta(days=30)
    cnds_vencendo = db.scalar(
        select(func.count(Certidao.id)).where(
            Certidao.data_validade >= hoje,
            Certidao.data_validade <= limite_cnd,
        )
    ) or 0
    cnds_vencidas = db.scalar(
        select(func.count(Certidao.id)).where(
            Certidao.data_validade < hoje,
        )
    ) or 0

    # --- Mensagens eCAC ---
    nao_lidas = db.scalar(
        select(func.count(MensagemEcac.id)).where(
            MensagemEcac.indicador_leitura != "1",
        )
    ) or 0
    alta_nao_lidas = db.scalar(
        select(func.count(MensagemEcac.id)).where(
            MensagemEcac.indicador_leitura != "1",
            MensagemEcac.indicador_relevancia == "1",
        )
    ) or 0

    # --- Certificados A1 vencendo / vencidos ---
    limite_cert = hoje + timedelta(days=60)
    certs_vencendo = sum(
        1 for e in empresas
        if e.cert_a1_validade_ate and hoje <= e.cert_a1_validade_ate <= limite_cert
    )
    certs_vencidos = sum(
        1 for e in empresas
        if e.cert_a1_validade_ate and e.cert_a1_validade_ate < hoje
    )

    # --- DAS Simples Nacional: atrasadas + valor ---
    das_rows = db.execute(
        select(
            func.count(GuiaDAS.id).label("qtd"),
            func.coalesce(func.sum(GuiaDAS.valor_principal), 0).label("valor"),
        ).where(GuiaDAS.situacao == "atrasada")
    ).one()
    das_atrasadas_qtd = int(das_rows.qtd or 0)
    das_atrasadas_valor = _decimal_to_float(das_rows.valor)

    # DAS em aberto (mes corrente, ainda no prazo)
    das_em_aberto_mes = db.scalar(
        select(func.count(GuiaDAS.id)).where(
            GuiaDAS.situacao == "em_aberto",
            GuiaDAS.data_vencimento_original >= hoje,
            GuiaDAS.data_vencimento_original <= hoje + timedelta(days=30),
        )
    ) or 0

    # --- PARCSN: parcelamentos ativos + parcelas restantes ---
    parc_ativos = db.scalar(
        select(func.count(ParcelamentoSimples.id))
    ) or 0
    parc_total_restantes = db.scalar(
        select(func.coalesce(func.sum(
            (ParcelamentoSimples.quantidade_parcelas - ParcelamentoSimples.parcelas_pagas)
        ), 0)).where(
            ParcelamentoSimples.quantidade_parcelas.isnot(None),
            ParcelamentoSimples.parcelas_pagas.isnot(None),
        )
    ) or 0

    # --- PGFN: parcelamentos Dívida Ativa (não-baixados) ---
    pgfn_ativos = db.scalar(
        select(func.count(ParcelamentoPgfn.id)).where(
            ParcelamentoPgfn.situacao != "nao_listado_mais",
        )
    ) or 0
    pgfn_valor_total = db.scalar(
        select(func.coalesce(func.sum(ParcelamentoPgfn.valor_total), 0)).where(
            ParcelamentoPgfn.situacao != "nao_listado_mais",
        )
    ) or 0
    pgfn_valor_pago = db.scalar(
        select(func.coalesce(func.sum(ParcelamentoPgfn.valor_total_pago), 0)).where(
            ParcelamentoPgfn.situacao != "nao_listado_mais",
        )
    ) or 0
    pgfn_restantes = db.scalar(
        select(func.coalesce(func.sum(
            (ParcelamentoPgfn.quantidade_parcelas - ParcelamentoPgfn.parcelas_pagas)
        ), 0)).where(
            ParcelamentoPgfn.situacao != "nao_listado_mais",
            ParcelamentoPgfn.quantidade_parcelas.isnot(None),
            ParcelamentoPgfn.parcelas_pagas.isnot(None),
        )
    ) or 0

    # --- DCTFWeb: guias emitidas no mes (visao operacional do escritorio) ---
    dctfweb_mes = db.scalar(
        select(func.count(GuiaDctfweb.id)).where(
            GuiaDctfweb.emitida_em >= inicio_mes,
            GuiaDctfweb.emitida_em < fim_mes,
        )
    ) or 0
    # Quantas empresas ATIVAS ainda nao tem DCTFWeb emitida no mes
    cnpjs_com_dctfweb = {
        row[0] for row in db.execute(
            select(GuiaDctfweb.empresa_id).where(
                GuiaDctfweb.emitida_em >= inicio_mes,
                GuiaDctfweb.emitida_em < fim_mes,
            ).distinct()
        ).all()
    }
    dctfweb_empresas_pendentes = sum(
        1 for e in empresas
        if e.ativo and e.id not in cnpjs_com_dctfweb
    )

    # --- FGTS Digital: guias emitidas pendentes de pagamento ---
    # 'situacao' guarda o estado salvo; status real considera vencimento.
    # Pendente = nao paga (situacao != 'paga'). Filtramos por vencimento p/ buckets.
    limite_fgts_30 = hoje + timedelta(days=30)

    fgts_pendentes_qtd = db.scalar(
        select(func.count(GuiaFgts.id)).where(GuiaFgts.situacao != "paga")
    ) or 0
    fgts_valor_a_pagar = db.scalar(
        select(func.coalesce(func.sum(GuiaFgts.valor_total), 0)).where(
            GuiaFgts.situacao != "paga",
        )
    ) or 0
    fgts_vencidas_qtd = db.scalar(
        select(func.count(GuiaFgts.id)).where(
            GuiaFgts.situacao != "paga",
            GuiaFgts.data_vencimento.isnot(None),
            GuiaFgts.data_vencimento < hoje,
        )
    ) or 0
    fgts_vencendo_30d_qtd = db.scalar(
        select(func.count(GuiaFgts.id)).where(
            GuiaFgts.situacao != "paga",
            GuiaFgts.data_vencimento >= hoje,
            GuiaFgts.data_vencimento <= limite_fgts_30,
        )
    ) or 0
    # Quantas empresas ATIVAS NÃO têm guia emitida no mês de referência
    # (ajuda a alertar pra cron mensal que ainda não foi disparado)
    fgts_periodo_ref = f"{ref_ano:04d}{ref_mes:02d}"
    cnpjs_com_fgts_mes = {
        row[0] for row in db.execute(
            select(GuiaFgts.empresa_id).where(
                GuiaFgts.periodo == fgts_periodo_ref,
            ).distinct()
        ).all()
    }
    fgts_empresas_sem_guia_mes = sum(
        1 for e in empresas
        if e.ativo and e.id not in cnpjs_com_fgts_mes
    )

    # --- Robo SEFAZ: ultima execucao + status ---
    ultima_exec = db.execute(
        select(ExecucaoRoboSefaz)
        .order_by(ExecucaoRoboSefaz.iniciado_em.desc())
        .limit(1)
    ).scalar_one_or_none()
    robo_em_andamento = db.scalar(
        select(func.count(ExecucaoRoboSefaz.id)).where(
            ExecucaoRoboSefaz.status.in_(["pendente", "rodando"]),
        )
    ) or 0
    robo_status = {
        "ultima_execucao_iniciada_em": ultima_exec.iniciado_em.isoformat() if ultima_exec else None,
        "ultima_execucao_status": ultima_exec.status if ultima_exec else None,
        "ultima_execucao_persistidos": int(ultima_exec.persistidos) if ultima_exec else 0,
        "ultima_execucao_erros": int(ultima_exec.erros) if ultima_exec else 0,
        "em_andamento": int(robo_em_andamento),
    }

    # --- Top 5 fornecedores do mes (por valor) ---
    top_q = (
        select(
            DocumentoFiscal.cnpj_emitente,
            DocumentoFiscal.nome_emitente,
            func.count(DocumentoFiscal.id).label("qtd"),
            func.coalesce(func.sum(DocumentoFiscal.valor_total), 0).label("valor"),
        )
        .where(
            DocumentoFiscal.data_emissao >= inicio_mes,
            DocumentoFiscal.data_emissao < fim_mes,
            DocumentoFiscal.cancelada == False,
            DocumentoFiscal.origem == "recebida",
        )
        .group_by(DocumentoFiscal.cnpj_emitente, DocumentoFiscal.nome_emitente)
        .order_by(func.sum(DocumentoFiscal.valor_total).desc())
        .limit(5)
    )
    top_fornecedores = [
        {
            "cnpj": row.cnpj_emitente,
            "nome": row.nome_emitente,
            "qtd": int(row.qtd),
            "valor": _decimal_to_float(row.valor),
        }
        for row in db.execute(top_q).all()
    ]

    return {
        "mes": f"{ref_ano:04d}-{ref_mes:02d}",
        "empresas": {
            "total": emp_total,
            "ativas": emp_ativas,
            "sem_focus_token": emp_sem_token,
            "sem_certificado_a1": emp_sem_cert,
        },
        "documentos_mes": {
            "total": int(docs_row.total),
            "valor_total": _decimal_to_float(docs_row.valor_total),
            "canceladas": int(docs_row.canceladas or 0),
            "geral_acumulado": total_geral,
            # Novos campos: separação emitidas/recebidas + faturamento real
            "emitidas": int(docs_row.emitidas or 0),
            "recebidas": int(docs_row.recebidas or 0),
            "faturamento": _decimal_to_float(docs_row.faturamento),
        },
        "manifestacao": {
            "pendentes": pendentes,
            "manifestadas": manifestadas,
        },
        "cnds": {
            "vencendo_30d": cnds_vencendo,
            "vencidas": cnds_vencidas,
        },
        "ecac": {
            "nao_lidas": nao_lidas,
            "alta_nao_lidas": alta_nao_lidas,
        },
        "certificados": {
            "vencendo_60d": certs_vencendo,
            "vencidos": certs_vencidos,
        },
        "das_simples": {
            "atrasadas_qtd": das_atrasadas_qtd,
            "atrasadas_valor": das_atrasadas_valor,
            "em_aberto_30d": int(das_em_aberto_mes),
        },
        "parcsn": {
            "ativos": int(parc_ativos),
            "parcelas_restantes_total": int(parc_total_restantes),
        },
        "pgfn": {
            "ativos": int(pgfn_ativos),
            "valor_total": _decimal_to_float(pgfn_valor_total),
            "valor_pago": _decimal_to_float(pgfn_valor_pago),
            "parcelas_restantes_total": int(pgfn_restantes),
        },
        "dctfweb": {
            "emitidas_mes": int(dctfweb_mes),
            "empresas_pendentes": int(dctfweb_empresas_pendentes),
        },
        "fgts": {
            "pendentes_qtd": int(fgts_pendentes_qtd),
            "valor_a_pagar": _decimal_to_float(fgts_valor_a_pagar),
            "vencidas_qtd": int(fgts_vencidas_qtd),
            "vencendo_30d_qtd": int(fgts_vencendo_30d_qtd),
            "empresas_sem_guia_mes": int(fgts_empresas_sem_guia_mes),
        },
        "robo_sefaz": robo_status,
        "top_fornecedores": top_fornecedores,
    }


@router.get("/por-empresa")
def por_empresa(db: Session = Depends(get_db)) -> list[dict]:
    """Devolve uma linha por empresa ATIVA com indicadores consolidados.

    Usado pela tabela "Visao por empresa" no dashboard.
    """
    hoje = date.today()
    inicio_mes = datetime(hoje.year, hoje.month, 1, tzinfo=timezone.utc)
    if hoje.month == 12:
        fim_mes = datetime(hoje.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fim_mes = datetime(hoje.year, hoje.month + 1, 1, tzinfo=timezone.utc)

    empresas = db.scalars(
        select(Empresa).where(Empresa.ativo == True).order_by(Empresa.razao_social)  # noqa: E712
    ).all()

    # NFes do mes por empresa (agregado de uma vez)
    docs_por_empresa = {
        row.empresa_id: int(row.qtd)
        for row in db.execute(
            select(
                DocumentoFiscal.empresa_id,
                func.count(DocumentoFiscal.id).label("qtd"),
            )
            .where(
                DocumentoFiscal.data_emissao >= inicio_mes,
                DocumentoFiscal.data_emissao < fim_mes,
                DocumentoFiscal.cancelada == False,  # noqa: E712
            )
            .group_by(DocumentoFiscal.empresa_id)
        ).all()
    }

    # DAS atrasadas por empresa
    das_por_empresa = {
        row.empresa_id: (int(row.qtd), _decimal_to_float(row.valor))
        for row in db.execute(
            select(
                GuiaDAS.empresa_id,
                func.count(GuiaDAS.id).label("qtd"),
                func.coalesce(func.sum(GuiaDAS.valor_principal), 0).label("valor"),
            )
            .where(GuiaDAS.situacao == "atrasada")
            .group_by(GuiaDAS.empresa_id)
        ).all()
    }

    # PARCSN ativos por empresa
    parcsn_por_empresa = {
        row.empresa_id: int(row.qtd)
        for row in db.execute(
            select(
                ParcelamentoSimples.empresa_id,
                func.count(ParcelamentoSimples.id).label("qtd"),
            )
            .group_by(ParcelamentoSimples.empresa_id)
        ).all()
    }

    # PGFN ativos por empresa (não-baixados)
    pgfn_por_empresa = {
        row.empresa_id: int(row.qtd)
        for row in db.execute(
            select(
                ParcelamentoPgfn.empresa_id,
                func.count(ParcelamentoPgfn.id).label("qtd"),
            )
            .where(ParcelamentoPgfn.situacao != "nao_listado_mais")
            .group_by(ParcelamentoPgfn.empresa_id)
        ).all()
    }

    # FGTS pendentes por empresa (não-paga) + flag de emissão no mês corrente
    fgts_pendentes_por_empresa = {
        row.empresa_id: int(row.qtd)
        for row in db.execute(
            select(
                GuiaFgts.empresa_id,
                func.count(GuiaFgts.id).label("qtd"),
            )
            .where(GuiaFgts.situacao != "paga")
            .group_by(GuiaFgts.empresa_id)
        ).all()
    }
    fgts_periodo_atual = f"{hoje.year:04d}{hoje.month:02d}"
    fgts_emitida_mes_set = {
        row[0] for row in db.execute(
            select(GuiaFgts.empresa_id).where(
                GuiaFgts.periodo == fgts_periodo_atual,
            ).distinct()
        ).all()
    }

    # DCTFWeb emitida no mes? (uma flag por empresa)
    dctfweb_emitida_set = {
        row[0] for row in db.execute(
            select(GuiaDctfweb.empresa_id).where(
                GuiaDctfweb.emitida_em >= inicio_mes,
                GuiaDctfweb.emitida_em < fim_mes,
            ).distinct()
        ).all()
    }

    # Ultima execucao do robo por empresa
    ultima_exec_por_empresa: dict[int, ExecucaoRoboSefaz] = {}
    execucoes = db.scalars(
        select(ExecucaoRoboSefaz)
        .where(ExecucaoRoboSefaz.empresa_id.isnot(None))
        .order_by(ExecucaoRoboSefaz.iniciado_em.desc())
    ).all()
    for ex in execucoes:
        if ex.empresa_id and ex.empresa_id not in ultima_exec_por_empresa:
            ultima_exec_por_empresa[ex.empresa_id] = ex

    resultado: list[dict] = []
    for emp in empresas:
        das_qtd, das_valor = das_por_empresa.get(emp.id, (0, 0.0))
        ex = ultima_exec_por_empresa.get(emp.id)
        cert_status = "ausente"
        if emp.cert_a1_validade_ate:
            if emp.cert_a1_validade_ate < hoje:
                cert_status = "vencido"
            elif emp.cert_a1_validade_ate <= hoje + timedelta(days=60):
                cert_status = "vencendo"
            else:
                cert_status = "ok"

        resultado.append({
            "empresa_id": emp.id,
            "cnpj": emp.cnpj,
            "razao_social": emp.razao_social,
            "uf": emp.uf,
            "regime": emp.regime_tributario,
            "nfes_mes": docs_por_empresa.get(emp.id, 0),
            "das_atrasadas_qtd": das_qtd,
            "das_atrasadas_valor": das_valor,
            "parcsn_ativos": parcsn_por_empresa.get(emp.id, 0),
            "pgfn_ativos": pgfn_por_empresa.get(emp.id, 0),
            "fgts_pendentes": fgts_pendentes_por_empresa.get(emp.id, 0),
            "fgts_mes_emitida": emp.id in fgts_emitida_mes_set,
            "dctfweb_mes_emitida": emp.id in dctfweb_emitida_set,
            "cert_a1_status": cert_status,
            "cert_a1_validade": emp.cert_a1_validade_ate.isoformat() if emp.cert_a1_validade_ate else None,
            "tem_focus_token": bool(emp.focus_token),
            "ultima_execucao_robo": {
                "iniciado_em": ex.iniciado_em.isoformat(),
                "status": ex.status,
                "persistidos": int(ex.persistidos or 0),
                "erros": int(ex.erros or 0),
            } if ex else None,
        })
    return resultado
