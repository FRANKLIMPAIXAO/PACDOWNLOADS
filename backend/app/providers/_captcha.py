"""Resolver de captcha via servico externo (2captcha.com).

Suporta 2 modos:
- Imagem (texto distorcido): usa endpoint `/in.php` com `method=base64`.
- reCAPTCHA v2: nao usado pelo CNDT, mas helper deixado para futuro.

Custo medio em 2captcha: USD 1 / 1000 captchas resolvidos. Resolve em
5-15 segundos por captcha.

Para usar: setar `CAPTCHA_API_KEY` no .env. Sem isso, levanta erro claro.
"""
from __future__ import annotations

import base64
import time
from typing import Final

import requests

from app.config import get_settings


_settings = get_settings()


CAPTCHA_API_BASE: Final = "http://2captcha.com"
CAPTCHA_TIMEOUT_S: Final = 180  # 3 min — captchas dificeis podem demorar
CAPTCHA_POLL_INTERVAL: Final = 5


class CaptchaError(Exception):
    """Falha na resolucao de captcha (timeout, chave invalida, captcha errado, etc)."""


def resolver_captcha_imagem(image_bytes: bytes, *, api_key: str | None = None) -> str:
    """Envia imagem de captcha para 2captcha e retorna o texto resolvido.

    Bloqueia a thread enquanto espera (5-180s). Use em background tasks.
    """
    key = api_key or _settings.captcha_api_key
    if not key:
        raise CaptchaError(
            "CAPTCHA_API_KEY nao configurada. Setar no .env "
            "(crie conta em 2captcha.com — ~US$ 1 / 1000 captchas)."
        )

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    # 1. Submit
    try:
        r = requests.post(
            f"{CAPTCHA_API_BASE}/in.php",
            data={
                "key": key,
                "method": "base64",
                "body": image_b64,
                "json": "1",
            },
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
    except requests.RequestException as exc:
        raise CaptchaError(f"Falha ao enviar captcha: {exc}") from exc

    if payload.get("status") != 1:
        raise CaptchaError(f"2captcha rejeitou submissao: {payload.get('request')}")

    captcha_id = payload["request"]

    # 2. Poll resultado
    deadline = time.time() + CAPTCHA_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(CAPTCHA_POLL_INTERVAL)
        try:
            r = requests.get(
                f"{CAPTCHA_API_BASE}/res.php",
                params={"key": key, "action": "get", "id": captcha_id, "json": "1"},
                timeout=30,
            )
            r.raise_for_status()
            payload = r.json()
        except requests.RequestException:
            continue
        if payload.get("status") == 1:
            return str(payload["request"])
        if payload.get("request") == "CAPCHA_NOT_READY":
            continue
        raise CaptchaError(f"2captcha falhou: {payload.get('request')}")

    raise CaptchaError(f"Timeout aguardando resolucao do captcha (id={captcha_id})")


def reportar_captcha_errado(captcha_id: str, *, api_key: str | None = None) -> None:
    """Reporta captcha resolvido errado (refund automatico no 2captcha)."""
    key = api_key or _settings.captcha_api_key
    if not key or not captcha_id:
        return
    try:
        requests.get(
            f"{CAPTCHA_API_BASE}/res.php",
            params={"key": key, "action": "reportbad", "id": captcha_id, "json": "1"},
            timeout=10,
        )
    except requests.RequestException:
        pass
