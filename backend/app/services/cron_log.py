"""Registro/listagem das execuções dos crons de distribuição (DF-e e CT-e).

Usado pelos routers de cron (dfe_distribuicao, cte_distribuicao) pra dar
visibilidade no relatório. Nunca derruba a rodada do cron."""
from __future__ import annotations

import json
import logging

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.cron_execucao import CronExecucao

logger = logging.getLogger("pac.cron_log")


def registrar_cron(db: Session, tipo: str, resultado: dict) -> None:
    """Grava 1 execução do cron (tipo='dfe'|'cte') a partir do dict do cron_diario.

    Espera `resultado['processadas']` = lista de itens por empresa, cada um com
    `resumos`/`completas`/`cstat`. Resiliente: erro aqui não afeta o cron."""
    try:
        proc = resultado.get("processadas", []) or []
        novos = sum((p.get("resumos") or 0) + (p.get("completas") or 0) for p in proc)
        com_656 = sum(1 for p in proc if str(p.get("cstat")) == "656")
        db.add(CronExecucao(
            tipo=tipo,
            total_elegiveis=resultado.get("total_elegiveis", 0),
            processadas=len(proc),
            novos=novos,
            com_656=com_656,
            detalhe=json.dumps(proc, ensure_ascii=False)[:8000],
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Falha ao registrar execução do cron %s", tipo)


def listar_execucoes(db: Session, tipo: str, limit: int = 30) -> list[dict]:
    limit = max(1, min(limit, 200))
    linhas = list(db.scalars(
        select(CronExecucao)
        .where(CronExecucao.tipo == tipo)
        .order_by(desc(CronExecucao.criado_em))
        .limit(limit)
    ).all())

    def _json(txt: str | None) -> list:
        if not txt:
            return []
        try:
            return json.loads(txt)
        except Exception:  # noqa: BLE001
            return []

    return [
        {
            "id": e.id,
            "criado_em": e.criado_em.isoformat() if e.criado_em else None,
            "tipo": e.tipo,
            "total_elegiveis": e.total_elegiveis,
            "processadas": e.processadas,
            "novos": e.novos,
            "com_656": e.com_656,
            "detalhe": _json(e.detalhe),
            "erro_msg": e.erro_msg,
        }
        for e in linhas
    ]
