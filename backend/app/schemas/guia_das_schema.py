"""Schemas Pydantic para guias DAS Simples Nacional."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class GuiaDASRead(BaseModel):
    """Resposta padrão de uma guia DAS (com info da empresa joinada)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    periodo_apuracao: str
    competencia_formatada: str  # MM/YYYY (property do model)
    numero_declaracao: str | None
    recibo_declaracao: str | None
    data_transmissao: datetime | None
    valor_principal: Decimal
    data_vencimento_original: date
    valor_atualizado: Decimal | None
    data_vencimento_atualizada: date | None
    numero_das: str | None
    codigo_barras: str | None
    pdf_path: str | None
    emitida_em: datetime | None
    situacao: str
    data_pagamento: date | None
    valor_pago: Decimal | None
    dias_atraso: int  # property do model
    sincronizada_em: datetime


class GuiaDASComEmpresa(GuiaDASRead):
    """Versão da guia que embute info básica da empresa (dashboard)."""
    empresa_cnpj: str | None = None
    empresa_razao_social: str | None = None


class SyncDASResposta(BaseModel):
    novas: int = 0
    atualizadas: int = 0
    pagas_detectadas: int = 0
    erros: int = 0
    detalhes: list[dict] | None = None


class SyncDASRequest(BaseModel):
    ano: int = Field(default_factory=lambda: datetime.now().year, ge=2020, le=2099)
