from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.utils.cnpj import normalize_cnpj, validate_cnpj


SITUACOES_CADASTRAIS_VALIDAS = {"ATIVA", "BAIXADA", "SUSPENSA", "INAPTA", "NULA"}


class EmpresaBase(BaseModel):
    """Campos compartilhados entre Create/Update/Read.

    Manter compatibilidade com versao anterior — todos os campos novos sao
    opcionais para nao quebrar payloads existentes.
    """
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    # --- Cadastrais ---
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    natureza_juridica_codigo: str | None = None
    natureza_juridica_descricao: str | None = None
    tributacao: str | None = None
    regime_tributario: str | None = None
    data_abertura: date | None = None
    data_inicio_sistema: date | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    email_contato: EmailStr | None = None
    situacao_cadastral: str | None = None
    # --- Endereco ---
    cep: str | None = None
    logradouro_tipo: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    # --- Tributario (Simples) ---
    ativo: bool = True
    anexo_simples: str | None = None
    atividade: str | None = None
    iss_aliquota: Decimal | None = None
    folha_12m: Decimal | None = None

    @field_validator("cnpj")
    @classmethod
    def validate_and_normalize_cnpj(cls, value: str) -> str:
        if not validate_cnpj(value):
            raise ValueError("CNPJ invalido")
        return normalize_cnpj(value)

    @field_validator("uf")
    @classmethod
    def normalize_uf(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("anexo_simples")
    @classmethod
    def validate_anexo(cls, value: str | None) -> str | None:
        if not value:
            return None
        v = value.strip().upper()
        if v not in {"I", "II", "III", "IV", "V"}:
            raise ValueError("anexo_simples deve ser I, II, III, IV ou V")
        return v

    @field_validator("situacao_cadastral")
    @classmethod
    def validate_situacao(cls, value: str | None) -> str | None:
        if not value:
            return None
        v = value.strip().upper()
        if v not in SITUACOES_CADASTRAIS_VALIDAS:
            raise ValueError(
                f"situacao_cadastral deve ser uma de {sorted(SITUACOES_CADASTRAIS_VALIDAS)}"
            )
        return v

    @field_validator("cep")
    @classmethod
    def normalize_cep(cls, value: str | None) -> str | None:
        if not value:
            return None
        digits = "".join(c for c in value if c.isdigit())
        if len(digits) != 8:
            raise ValueError("CEP deve ter 8 dígitos")
        return digits


class EmpresaCreate(EmpresaBase):
    pass


class EmpresaUpdate(BaseModel):
    """Atualizacao parcial — todos opcionais."""
    razao_social: str | None = None
    nome_fantasia: str | None = None
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    natureza_juridica_codigo: str | None = None
    natureza_juridica_descricao: str | None = None
    tributacao: str | None = None
    regime_tributario: str | None = None
    data_abertura: date | None = None
    data_inicio_sistema: date | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    email_contato: EmailStr | None = None
    situacao_cadastral: str | None = None
    cep: str | None = None
    logradouro_tipo: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    ativo: bool | None = None
    anexo_simples: str | None = None
    atividade: str | None = None
    iss_aliquota: Decimal | None = None
    folha_12m: Decimal | None = None


class EmpresaRead(EmpresaBase):
    """Representacao publica da empresa.

    NUNCA expor senhas/tokens cifrados — apenas flags booleanas.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    data_cadastro: datetime
    ultimo_nsu_distribuicao: str | None = None
    # Flags de credenciais (booleanas — sem expor secrets)
    tem_focus_token: bool = False
    tem_certificado_a1: bool = False
    cert_a1_validade_ate: date | None = None
    cert_a1_subject: str | None = None
    tem_credenciais_prefeitura: bool = False
    tem_credenciais_emissor_nacional: bool = False
    tem_codigo_acesso_simples: bool = False
    simples_cpf_responsavel: str | None = None


class CertificadoUploadInfo(BaseModel):
    """Resposta do upload de certificado A1."""
    cnpj_certificado: str
    subject: str
    validade_ate: date
    valido_de: date
    bate_cnpj_empresa: bool
    salvo_em: str
