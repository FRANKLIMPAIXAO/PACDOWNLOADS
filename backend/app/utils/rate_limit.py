"""Rate-limit simples EM MEMÓRIA (zera no restart) — anti brute-force de login.

Sem Redis: um dict de deques por chave. Chave típica = "ip|email" e "ip".
Não é distribuído (cada worker tem o seu), mas com 1-2 workers já corta ataque
de força bruta na prática. Se um dia precisar ser global, trocar por Redis.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

_FALHAS: dict[str, deque] = defaultdict(deque)


def bloqueado(chave: str, limite: int, janela_s: int = 300) -> bool:
    """True se `chave` acumulou >= `limite` falhas na janela (default 5 min)."""
    dq = _FALHAS[chave]
    agora = time.time()
    while dq and agora - dq[0] > janela_s:
        dq.popleft()
    return len(dq) >= limite


def registrar_falha(chave: str) -> None:
    _FALHAS[chave].append(time.time())


def limpar(*chaves: str) -> None:
    """Zera as falhas (chamar no login BEM-sucedido)."""
    for c in chaves:
        _FALHAS.pop(c, None)
