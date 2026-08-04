"""Watchdog do FRONTEND — o backend (estável) vigia o front e o revive sozinho.

PROBLEMA QUE RESOLVE: todo dia o processo Node do front TRAVA (aceita TCP/TLS e
nunca responde) e, como NÃO morre, o Docker/Swarm o considera saudável e nunca
reinicia — só um deploy manual recuperava. Tentar um HEALTHCHECK no Dockerfile
saiu pela culatra (virou restart loop e derrubou o site de vez), então a sonda
passa a viver FORA do container do front: aqui.

DUAS FUNÇÕES:
1. AUTO-RECUPERAÇÃO — depois de N falhas seguidas, dispara o webhook de deploy do
   Easypanel (mesma coisa que o usuário fazia na mão). Só age com o webhook
   configurado; sem ele, apenas registra.
2. DIAGNÓSTICO — guarda o histórico (uptime + memória do front) pra descobrir a
   CAUSA do travamento (ex.: memória subindo até travar) em vez de só remediar.

Config (env):
  FRONT_URL              default https://pacgestao.com.br
  EASYPANEL_DEPLOY_HOOK  webhook de redeploy do serviço do front (opcional)
  WATCHDOG_FALHAS        falhas seguidas antes de reiniciar (default 3)
"""
from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone

import requests

logger = logging.getLogger("pac.front_watchdog")

# Histórico em memória (zera no restart do backend). ~300 leituras = 25h a 5min.
_HIST: deque[dict] = deque(maxlen=300)
_ESTADO: dict = {"falhas_seguidas": 0, "ultimo_restart": None, "restarts": 0}

TIMEOUT_S = 12


def _front_url() -> str:
    return (os.getenv("FRONT_URL", "") or "https://pacgestao.com.br").rstrip("/")


def checar(*, recuperar: bool = True) -> dict:
    """Sonda o front e registra. Se falhar N vezes seguidas, dispara o redeploy.

    `recuperar=False` só observa (útil pra testar sem mexer em produção)."""
    url = f"{_front_url()}/api/health"
    agora = datetime.now(timezone.utc).isoformat()
    reg: dict = {"em": agora, "ok": False}

    try:
        r = requests.get(url, timeout=TIMEOUT_S)
        reg["http"] = r.status_code
        if r.status_code == 200:
            reg["ok"] = True
            try:
                corpo = r.json()
                # Estes dois são a PROVA da causa raiz: uptime baixo = reiniciou;
                # memória subindo ao longo do dia = vazamento.
                reg["uptime_s"] = corpo.get("uptime_s")
                reg["memoria_mb"] = (corpo.get("memoria_mb") or {}).get("rss")
            except ValueError:
                pass
    except requests.Timeout:
        # TRAVADO: conecta mas não responde — a assinatura exata do problema.
        reg["erro"] = "timeout"
    except requests.RequestException as exc:
        reg["erro"] = f"{type(exc).__name__}"

    if reg["ok"]:
        _ESTADO["falhas_seguidas"] = 0
    else:
        _ESTADO["falhas_seguidas"] += 1
    reg["falhas_seguidas"] = _ESTADO["falhas_seguidas"]

    limite = max(1, int(os.getenv("WATCHDOG_FALHAS", "3") or 3))
    hook = os.getenv("EASYPANEL_DEPLOY_HOOK", "").strip()
    if recuperar and not reg["ok"] and _ESTADO["falhas_seguidas"] >= limite:
        if hook:
            try:
                requests.post(hook, timeout=20)
                _ESTADO["falhas_seguidas"] = 0  # dá tempo do deploy subir
                _ESTADO["ultimo_restart"] = agora
                _ESTADO["restarts"] += 1
                reg["acao"] = "redeploy_disparado"
                logger.warning("Front sem responder %sx — redeploy disparado.", limite)
            except requests.RequestException as exc:
                reg["acao"] = f"falha_ao_disparar: {type(exc).__name__}"
                logger.exception("Falha ao disparar o redeploy do front")
        else:
            reg["acao"] = "sem_EASYPANEL_DEPLOY_HOOK"

    _HIST.appendleft(reg)
    return reg


def historico(limite: int = 100) -> dict:
    """Últimas leituras + resumo. É aqui que se lê a causa: veja `memoria_mb`
    crescendo e o `uptime_s` zerando."""
    itens = list(_HIST)[:limite]
    oks = [i for i in itens if i.get("ok")]
    mems = [i["memoria_mb"] for i in oks if i.get("memoria_mb")]
    return {
        "front_url": _front_url(),
        "leituras": len(_HIST),
        "falhas_seguidas": _ESTADO["falhas_seguidas"],
        "restarts_disparados": _ESTADO["restarts"],
        "ultimo_restart": _ESTADO["ultimo_restart"],
        "hook_configurado": bool(os.getenv("EASYPANEL_DEPLOY_HOOK", "").strip()),
        "memoria_mb_min": min(mems) if mems else None,
        "memoria_mb_max": max(mems) if mems else None,
        "historico": itens,
    }
