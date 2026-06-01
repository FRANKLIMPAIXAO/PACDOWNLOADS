"""Cofre simetrico para credenciais sensiveis (Focus token, senhas de portal, etc.).

Usa Fernet (AES-128-CBC + HMAC-SHA256) com chave derivada de `SECRET_KEY` via
SHA-256 -> base64-urlsafe (32 bytes), conforme exigido pelo Fernet.

Uso:
    from app.utils.crypto import encrypt_secret, decrypt_secret

    cipher = encrypt_secret("meu-token-focus")
    plain = decrypt_secret(cipher)

Compatibilidade: tokens nao criptografados (legado) sao detectados pela
ausencia do prefixo "gAAAAA" do Fernet e devolvidos como-vem em `decrypt_secret`,
para permitir migracao gradual.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    digest = hashlib.sha256(secret).digest()  # 32 bytes
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Criptografa um valor sensivel. Retorna string ASCII pronta para o BD."""
    if plaintext is None:
        raise ValueError("encrypt_secret: plaintext nao pode ser None")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str | None) -> str | None:
    """Decriptografa um valor. Tolera valores legados em texto puro.

    - None -> None
    - String vazia -> None
    - Texto puro nao-Fernet -> retorna como veio (compat. com migracao)
    - Fernet token valido -> texto plano
    """
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        # Provavelmente token legado em texto puro (pre-criptografia).
        # Devolver como veio para permitir migracao gradual.
        return ciphertext
