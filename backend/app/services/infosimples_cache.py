"""Cache TTL pra Infosimples — economiza pré-pago em re-consultas.

Estratégia:
- get_or_call(cnpj, endpoint, fetcher, ttl_dias, force=False)
- Se cache não-expirado existe → devolve direto, sem custo
- Se expirado/inexistente OU force=True → chama fetcher, salva resposta, devolve
- Cache é por (cnpj, endpoint, payload_hash) — payload_hash hoje é vazio,
  reservado pra quando endpoint receber filtros adicionais

NÃO é decorator pra manter explícito o TTL por chamada (CND válida = 30d,
CND vencida = 1d — calculado pelo caller baseado na situação).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cache_infosimples import CacheInfosimples


logger = logging.getLogger(__name__)


T = TypeVar("T")


def _so_digitos(cnpj: str) -> str:
    return "".join(c for c in (cnpj or "") if c.isdigit())


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalizar_dt(dt: datetime | None) -> datetime | None:
    """Garante datetime aware (UTC) — DB pode devolver naive em SQLite."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _payload_hash(payload: dict | None) -> str:
    if not payload:
        return ""
    serial = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(serial.encode()).hexdigest()


def get_cache(
    db: Session,
    *,
    cnpj: str,
    endpoint: str,
    payload: dict | None = None,
) -> dict | None:
    """Devolve resposta cacheada se não-expirada, senão None."""
    cnpj_d = _so_digitos(cnpj)
    h = _payload_hash(payload)
    row = db.scalar(
        select(CacheInfosimples).where(
            CacheInfosimples.cnpj == cnpj_d,
            CacheInfosimples.endpoint == endpoint,
            CacheInfosimples.payload_hash == h,
        )
    )
    if not row:
        return None
    expires = _normalizar_dt(row.expires_at)
    if expires and expires < _agora_utc():
        logger.debug(
            "Cache expirado para %s %s (expirou em %s)",
            cnpj_d, endpoint, expires,
        )
        return None
    try:
        return json.loads(row.response_json)
    except (ValueError, TypeError):
        logger.warning("Cache inválido para %s %s — ignorando", cnpj_d, endpoint)
        return None


def set_cache(
    db: Session,
    *,
    cnpj: str,
    endpoint: str,
    response: dict,
    ttl_dias: int,
    payload: dict | None = None,
    custo_centavos: int = 20,  # R$ 0,20 = faixa 1-500 consultas/mês
) -> None:
    """Salva (ou atualiza) entrada de cache. Commit imediato."""
    cnpj_d = _so_digitos(cnpj)
    h = _payload_hash(payload)
    expires = _agora_utc() + timedelta(days=ttl_dias)
    response_json = json.dumps(response, default=str)

    existing = db.scalar(
        select(CacheInfosimples).where(
            CacheInfosimples.cnpj == cnpj_d,
            CacheInfosimples.endpoint == endpoint,
            CacheInfosimples.payload_hash == h,
        )
    )
    if existing:
        existing.response_json = response_json
        existing.expires_at = expires
        existing.custo_centavos = custo_centavos
    else:
        db.add(CacheInfosimples(
            cnpj=cnpj_d,
            endpoint=endpoint,
            payload_hash=h,
            response_json=response_json,
            expires_at=expires,
            custo_centavos=custo_centavos,
        ))
    db.commit()


def get_or_call(
    db: Session,
    *,
    cnpj: str,
    endpoint: str,
    fetcher: Callable[[], T],
    ttl_dias: int,
    payload: dict | None = None,
    serializer: Callable[[T], dict] = lambda x: x.__dict__ if hasattr(x, "__dict__") else x,
    deserializer: Callable[[dict], T] | None = None,
    force: bool = False,
) -> tuple[T, bool]:
    """High-level helper: devolve (resultado, veio_do_cache).

    - `fetcher`: callable que faz a chamada cara à API (recebe nada, retorna T)
    - `serializer`: como T vira dict pra JSON (default `__dict__`)
    - `deserializer`: opcional — como dict vira T de volta. Se None, devolve dict.

    Em endpoints onde a resposta é uma dataclass (CndInfosimples), passe um
    deserializer que reconstrói a dataclass do dict. Pra listas, embrulhe.
    """
    if not force:
        cached = get_cache(db, cnpj=cnpj, endpoint=endpoint, payload=payload)
        if cached is not None:
            logger.info("Cache HIT %s %s", _so_digitos(cnpj), endpoint)
            if deserializer:
                return deserializer(cached), True
            return cached, True  # type: ignore[return-value]

    logger.info("Cache MISS %s %s — chamando API", _so_digitos(cnpj), endpoint)
    resultado = fetcher()
    try:
        as_dict = serializer(resultado)
        set_cache(
            db, cnpj=cnpj, endpoint=endpoint,
            response=as_dict, ttl_dias=ttl_dias, payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao cachear (não bloqueia): %s", exc)
    return resultado, False


def invalidar(
    db: Session,
    *,
    cnpj: str | None = None,
    endpoint: str | None = None,
) -> int:
    """Apaga entradas do cache. Útil pra debug ou "limpar tudo dessa empresa"."""
    stmt = select(CacheInfosimples)
    if cnpj:
        stmt = stmt.where(CacheInfosimples.cnpj == _so_digitos(cnpj))
    if endpoint:
        stmt = stmt.where(CacheInfosimples.endpoint == endpoint)
    rows = list(db.scalars(stmt).all())
    for r in rows:
        db.delete(r)
    db.commit()
    return len(rows)
