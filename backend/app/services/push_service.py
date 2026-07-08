"""Envio de Web Push (notificação do portal no celular, tipo WhatsApp).

Lazy-import do pywebpush: o app SOBE mesmo sem a dep instalada (antes do rebuild)
— o push só fica ativo quando a imagem é reconstruída com o requirements novo. Sem
chaves VAPID configuradas, também é no-op (o portal funciona igual, só não notifica).
"""
from __future__ import annotations

import json
import logging

from app.config import get_settings

logger = logging.getLogger("pac.push")


def push_configurado() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def enviar_push(subs: list, titulo: str, corpo: str, url: str = "/portal", tag: str = "pacchat") -> list[str]:
    """Envia a notificação pra cada inscrição (`subs` = objetos com .endpoint,
    .p256dh, .auth). Retorna os endpoints MORTOS (404/410) pra quem chamou apagar
    do banco. Nunca levanta — falha de um device não derruba os outros."""
    if not subs:
        return []
    s = get_settings()
    if not push_configurado():
        logger.info("Push desligado (sem VAPID) — %s inscrição(ões) ignorada(s)", len(subs))
        return []
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush não instalado — precisa REBUILD da imagem. Push pulado.")
        return []

    payload = json.dumps({"title": titulo, "body": corpo, "url": url, "tag": tag})
    mortos: list[str] = []
    for sub in subs:
        info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=s.vapid_private_key,
                # dict NOVO a cada envio: o pywebpush injeta aud/exp e mutaria um
                # dict compartilhado (aud errado pro próximo endpoint).
                vapid_claims={"sub": s.vapid_subject},
            )
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):
                mortos.append(sub.endpoint)  # inscrição expirou/foi removida → limpar
            else:
                logger.warning("Falha ao enviar push (status %s): %s", code, str(exc)[:200])
        except Exception as exc:  # noqa: BLE001 — push é best-effort
            logger.warning("Erro inesperado no push: %s", str(exc)[:200])
    return mortos
