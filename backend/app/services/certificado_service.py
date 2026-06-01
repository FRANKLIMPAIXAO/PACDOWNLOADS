"""Servico de gerenciamento de certificado A1 por empresa.

Fluxo:
1. Frontend envia `.pfx` + senha via multipart.
2. Validamos com `cryptography.pkcs12` (carrega -> pega subject/validade).
3. Extraimos o CNPJ do Subject DN (formato ICP-Brasil:
   `CN=<RAZAO>:<CNPJ>` ou OU contendo o CNPJ).
4. Comparamos com o `empresa.cnpj` cadastrado (warning se diferir).
5. Salvamos `.pfx` em `storage/certs/<cnpj>.pfx` (gitignored).
6. Senha cifrada no banco via cofre Fernet (`empresa.set_cert_a1_senha`).
7. Subject + validade ate salvos pra exibicao no front (nao precisa abrir
   o .pfx toda vez).
8. (opcional) Se a empresa ja tem `focus_token`, pode acionar
   `provider.atualizar_empresa` pra sincronizar com a Focus tambem.

Storage:
- `storage/certs/<cnpj>.pfx` (permissoes restritas no deploy, gitignored)
- Senha em `empresas.cert_a1_senha_cifrada` (Fernet)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings
from app.models.empresa import Empresa


_settings = get_settings()


@dataclass(slots=True)
class CertificadoInfo:
    cnpj_certificado: str
    subject: str
    validade_ate: date
    valido_de: date
    bate_cnpj_empresa: bool
    salvo_em: str


def _certificados_dir() -> Path:
    """Diretorio onde armazenamos os .pfx por empresa.

    Usa `STORAGE_PATH` do .env como root, criando subdir `certs` ao lado dos XMLs.
    """
    storage_root = Path(_settings.storage_path).parent
    p = storage_root / "certs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _extrair_cnpj_subject(subject_rfc4514: str) -> str | None:
    """Extrai o CNPJ de 14 digitos do Subject DN de um certificado ICP-Brasil.

    Padroes comuns:
      - CN=PAC INTELIGENCIA TRIBUTARIA LTDA:37165535000122
      - OU=37165535000122
      - Em algum lugar do DN: ':<14 digits>' ou '<14 digits>'.
    """
    # Procura 14 digitos consecutivos no DN
    m = re.search(r"(?<!\d)(\d{14})(?!\d)", subject_rfc4514)
    return m.group(1) if m else None


def validar_certificado_pfx(
    pfx_bytes: bytes,
    senha: str,
) -> tuple[str, date, date, str | None]:
    """Carrega o .pfx, retorna (subject_dn, validade_ate, valido_de, cnpj).

    Lanca HTTPException 400 se cert/senha invalidos.
    """
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="cryptography nao instalada no backend",
        ) from exc

    try:
        private_key, certificate, _extras = pkcs12.load_key_and_certificates(
            pfx_bytes, senha.encode("utf-8"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Falha ao abrir .pfx: senha incorreta ou arquivo corrompido ({exc})",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"PFX invalido: {exc}",
        ) from exc

    if not certificate:
        raise HTTPException(status_code=400, detail="PFX sem certificado")

    subject = certificate.subject.rfc4514_string()

    # `not_valid_after_utc` / `not_valid_before_utc` (cryptography >= 41)
    try:
        nv_after = certificate.not_valid_after_utc
        nv_before = certificate.not_valid_before_utc
    except AttributeError:
        nv_after = certificate.not_valid_after.replace(tzinfo=timezone.utc)
        nv_before = certificate.not_valid_before.replace(tzinfo=timezone.utc)

    validade = nv_after.date()
    inicio = nv_before.date()

    # Aviso se ja vencido
    if validade < datetime.now(timezone.utc).date():
        raise HTTPException(
            status_code=400,
            detail=f"Certificado vencido em {validade.isoformat()}.",
        )

    cnpj_cert = _extrair_cnpj_subject(subject)
    return subject, validade, inicio, cnpj_cert


def salvar_certificado_para_empresa(
    db,
    empresa: Empresa,
    pfx_bytes: bytes,
    senha: str,
    *,
    permitir_cnpj_diferente: bool = False,
) -> CertificadoInfo:
    """Valida + persiste cert da empresa.

    Se o CNPJ extraido do cert nao bate com `empresa.cnpj`, lanca HTTPException
    a menos que `permitir_cnpj_diferente=True` (ex: matriz cadastrando filial).
    """
    subject, validade, inicio, cnpj_cert = validar_certificado_pfx(pfx_bytes, senha)

    cnpj_empresa = (empresa.cnpj or "").replace(".", "").replace("/", "").replace("-", "")
    bate = bool(cnpj_cert and cnpj_cert == cnpj_empresa)
    if cnpj_cert and not bate and not permitir_cnpj_diferente:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CNPJ do certificado ({cnpj_cert}) nao bate com a empresa "
                f"({cnpj_empresa}). Se for matriz+filial intencional, envie "
                "`permitir_cnpj_diferente=true`."
            ),
        )

    # Salva o .pfx no disco
    destino = _certificados_dir() / f"{cnpj_empresa}.pfx"
    destino.write_bytes(pfx_bytes)

    empresa.cert_a1_path = str(destino)
    empresa.cert_a1_validade_ate = validade
    empresa.cert_a1_subject = subject[:300]
    empresa.set_cert_a1_senha(senha)
    db.commit()
    db.refresh(empresa)

    return CertificadoInfo(
        cnpj_certificado=cnpj_cert or "",
        subject=subject,
        validade_ate=validade,
        valido_de=inicio,
        bate_cnpj_empresa=bate,
        salvo_em=str(destino),
    )


def remover_certificado(db, empresa: Empresa) -> None:
    """Apaga o .pfx do disco e limpa campos do banco."""
    if empresa.cert_a1_path:
        p = Path(empresa.cert_a1_path)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    empresa.cert_a1_path = None
    empresa.cert_a1_validade_ate = None
    empresa.cert_a1_subject = None
    empresa.set_cert_a1_senha(None)
    db.commit()
