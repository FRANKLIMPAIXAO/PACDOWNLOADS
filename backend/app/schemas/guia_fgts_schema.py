"""Schemas Pydantic para Guias FGTS Digital."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class GuiaFgtsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    periodo: str
    competencia_formatada: str | None
    data_vencimento: date | None
    valor_total: Decimal
    valor_mensal: Decimal | None
    valor_rescisorio: Decimal | None
    valor_compensatorio: Decimal | None
    valor_encargos: Decimal | None
    quantidade_trabalhadores: int | None
    pdf_url_infosimples: str | None
    pdf_path: str | None
    situacao: str
    status_calculado: str
    dias_para_vencer: int | None
    data_pagamento: date | None
    emitida_em: datetime


class GuiaFgtsComEmpresa(GuiaFgtsRead):
    empresa_cnpj: str | None = None
    empresa_razao_social: str | None = None


class EmitirFgtsPayload(BaseModel):
    """Payload pra emissão de Guia FGTS Digital."""
    periodo: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmitirFgtsResposta(BaseModel):
    sucesso: bool
    guia: GuiaFgtsRead | None = None
    erro: str | None = None


class HistoricoFgtsResposta(BaseModel):
    total_guias: int
    total_paginas: int
    pagina: int
    guias: list[dict]
    empregador: dict | None
    procurador: dict | None
