from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.utils.cnpj import normalize_cnpj, validate_cnpj


class EnderecoFocusSchema(BaseModel):
    logradouro: str
    numero: str
    complemento: str | None = None
    bairro: str | None = None
    codigo_municipio: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None

    @field_validator("uf")
    @classmethod
    def normalize_uf(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class EmpresaFocusPayload(BaseModel):
    """Payload para cadastro/atualizacao de empresa na Focus NFe.

    Mapeia para os campos esperados pela Focus em POST/PUT /v2/empresas
    (multipart). Os campos `arquivo_certificado` e `senha_certificado` sao
    enviados separadamente pelo endpoint, nao por aqui.
    """

    cnpj: str
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    nome: str
    nome_fantasia: str | None = None
    fone: str | None = None
    email: str | None = None
    regime_tributario: str | None = None
    # Flags Focus — sem estes 4 a Focus retorna 500 generico no POST /v2/empresas.
    # Default None pra nao quebrar PUT (atualizacao parcial) — sao setados
    # explicitamente em `auto_cadastrar_focus` na hora do cadastro.
    habilita_nfe: bool | None = None
    habilita_nfce: bool | None = None
    habilita_cte: bool | None = None
    habilita_nfse: bool | None = None
    discrimina_impostos: bool | None = None
    enviar_email_destinatario: bool | None = None
    # Datas de inicio do recebimento DF-e (formato YYYY-MM-DD).
    # IMPORTANTE Focus: documentos anteriores sao ignorados; apos definida,
    # NAO PODE ser alterada. Default em auto_cadastrar = data do cadastro.
    data_inicio_recebimento_nfe: str | None = None
    data_inicio_recebimento_cte: str | None = None
    endereco: EnderecoFocusSchema

    @field_validator("cnpj")
    @classmethod
    def validate_and_normalize_cnpj(cls, value: str) -> str:
        if not validate_cnpj(value):
            raise ValueError("CNPJ invalido")
        return normalize_cnpj(value)


class EmpresaFocusRead(BaseModel):
    cnpj: str
    nome: str | None = None
    nome_fantasia: str | None = None
    regime_tributario: str | None = None
    habilita_nfe: bool | None = None
    habilita_nfce: bool | None = None
    habilita_cte: bool | None = None
    habilita_nfse: bool | None = None
    certificado_valido_de: str | None = None
    certificado_valido_ate: str | None = None
    # Os tokens NUNCA sao retornados ao cliente; o backend salva em
    # `empresas.focus_token` e nao expoe via API.


class EmpresaFocusTokenPayload(BaseModel):
    """Importa um token Focus gerado manualmente no painel."""

    token: str = Field(min_length=10)


class CertificadoInfoRead(BaseModel):
    serial_number: str | None = None
    issuer_name: str | None = None
    not_valid_before: datetime | None = None
    not_valid_after: datetime | None = None
    thumbprint: str | None = None
    subject_name: str | None = None
    cnpj: str | None = None
    nome_razao_social: str | None = None


class StatusIntegracaoEmpresaRead(BaseModel):
    empresa_local_id: int
    empresa_local_cnpj: str
    tem_token: bool
    empresa_focus: dict[str, Any] | None = None
