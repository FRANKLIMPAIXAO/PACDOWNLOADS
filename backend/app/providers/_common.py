from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_data_emissao(value: Any) -> datetime | None:
    """Converte um campo de data para datetime.

    Aceita:
    - datetime (devolve como esta)
    - string ISO 8601 ("2025-08-19", "2025-08-19T12:34:56Z", ...)
    - string YYYYMMDD ("20250819") — formato Serpro
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        # Formato Serpro: YYYYMMDD ou YYYYMMDDHHMMSS
        s = value.strip()
        if len(s) == 8 and s.isdigit():
            try:
                return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        if len(s) == 14 and s.isdigit():
            try:
                return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None
    return None


def parse_data_hora_serpro(data: Any, hora: Any = None) -> datetime | None:
    """Combina campos separados `dataEnvio` ("20250819") + `horaEnvio` ("105007")."""
    if not data:
        return None
    data_str = str(data).strip()
    hora_str = str(hora or "").strip().zfill(6) if hora else ""
    combined = data_str + hora_str if hora_str else data_str
    return parse_data_emissao(combined)
