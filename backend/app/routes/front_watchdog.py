"""Rotas do watchdog do FRONT (sem login — chamadas por cron externo/navegador).

Protegido pelo mesmo token dos outros crons (`X-Cron-Token` ou `?token=`), que
já é o padrão do sistema. Não expõe segredo nem dado de cliente — só o estado do
front (uptime/memória) e o histórico das sondagens.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Header, HTTPException

from app.services.front_watchdog import checar, historico

router = APIRouter(prefix="/front-watchdog", tags=["front-watchdog"])


def _exige_token(x_cron_token: str, token: str) -> None:
    esperado = (
        os.getenv("WATCHDOG_TOKEN", "")
        or os.getenv("NFSE_CRON_TOKEN", "")
        or os.getenv("DFE_CRON_TOKEN", "")
    )
    if not esperado:
        raise HTTPException(status_code=503, detail="Nenhum token de cron configurado no servidor.")
    recebido = x_cron_token or token
    if not recebido or not hmac.compare_digest(recebido, esperado):
        raise HTTPException(status_code=401, detail="Token inválido.")


@router.api_route("/check", methods=["GET", "POST"])
def check(
    x_cron_token: str = Header(default=""),
    token: str = "",
    recuperar: bool = True,
) -> dict:
    """Sonda o front UMA vez. Chamado por cron externo a cada ~5 min.

    Depois de N falhas seguidas (WATCHDOG_FALHAS, default 3) dispara o webhook de
    redeploy do Easypanel (EASYPANEL_DEPLOY_HOOK) — o mesmo deploy que era feito
    na mão. `recuperar=false` só observa, sem reiniciar nada."""
    _exige_token(x_cron_token, token)
    return checar(recuperar=recuperar)


@router.get("/historico")
def ver_historico(
    x_cron_token: str = Header(default=""),
    token: str = "",
    limite: int = 100,
) -> dict:
    """Histórico das sondagens — é aqui que se enxerga a CAUSA do travamento:
    `memoria_mb` subindo ao longo do dia e `uptime_s` zerando nos reinícios."""
    _exige_token(x_cron_token, token)
    return historico(limite=max(1, min(limite, 300)))
