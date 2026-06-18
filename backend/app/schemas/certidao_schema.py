from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


TipoCertidaoLiteral = Literal[
    "FEDERAL", "FEDERAL_OFICIAL", "FGTS", "TRABALHISTA", "ESTADUAL", "MUNICIPAL",
]


class CertidaoCreate(BaseModel):
    tipo: TipoCertidaoLiteral
    numero: str | None = None
    data_emissao: date | None = None
    data_validade: date
    observacoes: str | None = None


class CertidaoUpdate(BaseModel):
    numero: str | None = None
    data_emissao: date | None = None
    data_validade: date | None = None
    observacoes: str | None = None


class CertidaoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    tipo: str
    numero: str | None = None
    data_emissao: date | None = None
    data_validade: date
    pdf_path: str | None = None
    observacoes: str | None = None
    created_at: datetime
    updated_at: datetime
    status: str
    dias_para_vencer: int | None = None
    # regular | pendencias | verificar | None (None = sem marcador → vale a data)
    situacao_fiscal: str | None = None
    pendencias: list[str] = []


class CndDashboardResposta(BaseModel):
    empresa_id: int
    empresa_razao_social: str
    cnpj: str
    federal: CertidaoRead | None = None              # SITFIS (Integra)
    federal_oficial: CertidaoRead | None = None      # CND oficial RFB+PGFN
    fgts: CertidaoRead | None = None
    trabalhista: CertidaoRead | None = None
    estadual: CertidaoRead | None = None
    municipal: CertidaoRead | None = None
    score: float  # 0..1 — fracao de tipos com certidao valida
