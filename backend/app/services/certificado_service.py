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

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from app.config import get_settings
from app.models.empresa import Empresa


def _restringir_permissao(caminho: Path, modo: int) -> None:
    """chmod best-effort (no-op tolerante em Windows/FS sem suporte). Em Linux
    (produção) garante que o .pfx/dir não fique legível por outros usuários."""
    try:
        os.chmod(caminho, modo)
    except (OSError, NotImplementedError):
        pass


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
    _restringir_permissao(p, 0o700)  # só o dono lê os certs
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

    # Salva o .pfx no disco com permissão restrita (0600 — só o dono lê).
    destino = _certificados_dir() / f"{cnpj_empresa}.pfx"
    destino.write_bytes(pfx_bytes)
    _restringir_permissao(destino, 0o600)

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


@dataclass(slots=True)
class CertificadoDiagnostico:
    """Resultado do diagnostico de um cert A1 ja salvo no PAC.

    Diferente de `validar_certificado_pfx`, este NUNCA lanca HTTPException —
    qualquer falha vira `ok=False` + `erro=str`. O objetivo eh dar feedback
    estruturado pro frontend exibir uma checklist tipo "senha OK / vencido?
    / CNPJ bate?", sem matar a request.
    """
    ok: bool
    mac_ok: bool  # True se pkcs12 abriu com a senha salva
    subject: str | None
    valido_de: date | None
    validade_ate: date | None
    vencido: bool | None
    dias_pra_vencer: int | None
    cnpj_certificado: str | None
    cnpj_empresa: str
    bate_com_empresa: bool | None
    path_existe: bool
    senha_decifravel: bool
    erro: str | None


def diagnosticar_certificado_empresa(empresa: Empresa) -> CertificadoDiagnostico:
    """Roda checks no cert A1 salvo da empresa sem chamar nenhuma API externa.

    Sequencia:
    1. Existe `cert_a1_path` no banco? Se nao, ok=False imediato.
    2. Arquivo existe no disco?
    3. Conseguimos decifrar a senha cifrada (Fernet / SECRET_KEY alinhada)?
    4. pkcs12 abre com a senha (MAC verify)?
    5. Cert vencido?
    6. CNPJ extraido do Subject bate com `empresa.cnpj`?

    Retorna `CertificadoDiagnostico` com todos os campos preenchidos ate onde
    deu pra ir antes de qualquer falha.
    """
    cnpj_empresa = (empresa.cnpj or "").replace(".", "").replace("/", "").replace("-", "")

    if not empresa.cert_a1_path:
        return CertificadoDiagnostico(
            ok=False, mac_ok=False, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=False, senha_decifravel=False,
            erro="Empresa nao tem cert_a1_path cadastrado.",
        )

    pfx_path = Path(empresa.cert_a1_path)
    if not pfx_path.exists():
        return CertificadoDiagnostico(
            ok=False, mac_ok=False, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=False, senha_decifravel=False,
            erro=f"Arquivo .pfx nao encontrado no caminho salvo ({pfx_path.name}).",
        )

    senha = empresa.get_cert_a1_senha()
    if senha is None:
        return CertificadoDiagnostico(
            ok=False, mac_ok=False, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=True, senha_decifravel=False,
            erro=(
                "Senha cifrada nao decifravel — provavelmente SECRET_KEY do "
                ".env mudou desde que o cert foi cadastrado. Refaca o upload."
            ),
        )

    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError:
        return CertificadoDiagnostico(
            ok=False, mac_ok=False, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=True, senha_decifravel=True,
            erro="lib cryptography nao instalada no backend.",
        )

    pfx_bytes = pfx_path.read_bytes()
    try:
        _key, certificate, _extras = pkcs12.load_key_and_certificates(
            pfx_bytes, senha.encode("utf-8"),
        )
    except ValueError as exc:
        # MAC verify failed = senha errada (causa #1 do Focus 500)
        return CertificadoDiagnostico(
            ok=False, mac_ok=False, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=True, senha_decifravel=True,
            erro=(
                f"PFX nao abriu com a senha salva (MAC verify failed): {exc}. "
                "Provavelmente senha digitada errada no momento do upload. "
                "Refaca o upload do cert com a senha correta."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return CertificadoDiagnostico(
            ok=False, mac_ok=False, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=True, senha_decifravel=True,
            erro=f"PFX invalido / corrompido: {type(exc).__name__}: {exc}",
        )

    if not certificate:
        return CertificadoDiagnostico(
            ok=False, mac_ok=True, subject=None, valido_de=None,
            validade_ate=None, vencido=None, dias_pra_vencer=None,
            cnpj_certificado=None, cnpj_empresa=cnpj_empresa,
            bate_com_empresa=None, path_existe=True, senha_decifravel=True,
            erro="PFX abriu mas nao contem certificado X.509.",
        )

    subject = certificate.subject.rfc4514_string()
    try:
        nv_after = certificate.not_valid_after_utc
        nv_before = certificate.not_valid_before_utc
    except AttributeError:
        nv_after = certificate.not_valid_after.replace(tzinfo=timezone.utc)
        nv_before = certificate.not_valid_before.replace(tzinfo=timezone.utc)

    validade = nv_after.date()
    inicio = nv_before.date()
    hoje = datetime.now(timezone.utc).date()
    vencido = validade < hoje
    dias_pra_vencer = (validade - hoje).days

    cnpj_cert = _extrair_cnpj_subject(subject)
    bate = bool(cnpj_cert and cnpj_cert == cnpj_empresa)

    # ok=True somente se passou em TODOS os checks
    tudo_ok = (not vencido) and bate

    erro: str | None = None
    if vencido:
        erro = f"Certificado vencido em {validade.isoformat()} ({-dias_pra_vencer} dias atras)."
    elif not bate:
        erro = (
            f"CNPJ do cert ({cnpj_cert}) NAO bate com a empresa ({cnpj_empresa}). "
            "Cert pode ser de outra empresa."
        )

    return CertificadoDiagnostico(
        ok=tudo_ok,
        mac_ok=True,
        subject=subject[:300],
        valido_de=inicio,
        validade_ate=validade,
        vencido=vencido,
        dias_pra_vencer=dias_pra_vencer,
        cnpj_certificado=cnpj_cert,
        cnpj_empresa=cnpj_empresa,
        bate_com_empresa=bate,
        path_existe=True,
        senha_decifravel=True,
        erro=erro,
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
