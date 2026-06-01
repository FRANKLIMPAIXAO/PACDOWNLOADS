"""Cliente HTTP do PAC Download API.

Responsabilidades:
- Autenticar (JWT)
- Listar empresas ativas com cert A1 cadastrado
- Baixar .pfx + senha de uma empresa (uso interno do agente)
- Postar ZIP de XMLs no endpoint upload-em-massa
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EmpresaPAC:
    id: int
    cnpj: str
    razao_social: str
    uf: str | None
    tem_certificado_a1: bool
    cert_a1_validade_ate: str | None
    ativo: bool


@dataclass(slots=True)
class CertificadoBaixado:
    cnpj: str
    pfx_path: Path
    senha: str
    validade_ate: str


class PacClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        password: str,
        *,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token: str | None = None
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, follow_redirects=True,
        )

    # --- Auth ---

    def login(self) -> str:
        """Obtém JWT e cacheia no client."""
        logger.info("Autenticando no PAC como %s", self.email)
        r = self._client.post(
            "/api/v1/auth/login",
            json={"email": self.email, "password": self.password},
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        self._client.headers["Authorization"] = f"Bearer {self._token}"
        return self._token

    def ensure_login(self) -> None:
        if not self._token:
            self.login()

    # --- Empresas ---

    def listar_empresas(self, *, somente_com_cert: bool = True) -> list[EmpresaPAC]:
        """Lista empresas. Por default filtra só as que têm cert A1 (pré-req do agente)."""
        self.ensure_login()
        r = self._client.get("/api/v1/empresas")
        r.raise_for_status()
        data = r.json()
        empresas = [
            EmpresaPAC(
                id=e["id"],
                cnpj=e["cnpj"],
                razao_social=e["razao_social"],
                uf=e.get("uf"),
                tem_certificado_a1=bool(e.get("tem_certificado_a1")),
                cert_a1_validade_ate=e.get("cert_a1_validade_ate"),
                ativo=bool(e.get("ativo", True)),
            )
            for e in data
        ]
        if somente_com_cert:
            empresas = [e for e in empresas if e.ativo and e.tem_certificado_a1]
        return empresas

    # --- Certificado ---

    def baixar_certificado(self, empresa_id: int, destino_dir: Path) -> CertificadoBaixado:
        """Baixa .pfx + senha de UMA empresa pra uso temporário pelo agente.

        Salva o .pfx em `destino_dir/<cnpj>.pfx` e retorna a senha.
        O caller é responsável por apagar o arquivo após uso.
        """
        self.ensure_login()
        r = self._client.get(f"/api/v1/empresas/{empresa_id}/certificado/baixar")
        r.raise_for_status()

        cnpj = r.headers.get("X-Cert-CNPJ", "")
        senha = r.headers.get("X-Cert-Password", "")
        validade = r.headers.get("X-Cert-Validade-Ate", "")
        if not cnpj or not senha:
            raise RuntimeError("Resposta sem headers de cert (X-Cert-CNPJ/X-Cert-Password)")

        destino_dir.mkdir(parents=True, exist_ok=True)
        pfx_path = destino_dir / f"{cnpj}.pfx"
        pfx_path.write_bytes(r.content)
        return CertificadoBaixado(
            cnpj=cnpj, pfx_path=pfx_path, senha=senha, validade_ate=validade,
        )

    # --- Upload em massa ---

    def upload_em_massa(
        self,
        zip_path: Path,
        empresa_id_fallback: int | None = None,
    ) -> dict[str, Any]:
        """Envia o ZIP de XMLs pro endpoint /documentos/upload-em-massa."""
        self.ensure_login()
        files = {
            "arquivo": (zip_path.name, zip_path.read_bytes(), "application/zip"),
        }
        data: dict[str, str] = {}
        if empresa_id_fallback:
            data["empresa_id_fallback"] = str(empresa_id_fallback)
        r = self._client.post(
            "/api/v1/documentos/upload-em-massa", files=files, data=data,
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PacClient":
        self.login()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
