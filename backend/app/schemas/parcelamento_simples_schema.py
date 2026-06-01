"""Schemas Pydantic para Parcelamentos Simples Nacional (PARCSN)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ParcelamentoSimplesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    modalidade: str
    numero: int
    data_pedido: date | None
    situacao: str | None
    data_situacao: date | None
    valor_total: Decimal | None
    valor_total_pago: Decimal | None
    quantidade_parcelas: int | None
    parcelas_pagas: int | None
    parcelas_restantes: int | None
    percentual_concluido: float | None
    sincronizado_em: datetime


class ParcelamentoSimplesComEmpresa(ParcelamentoSimplesRead):
    empresa_cnpj: str | None = None
    empresa_razao_social: str | None = None


class SyncParcsnResposta(BaseModel):
    novos: int = 0
    atualizados: int = 0
    erros: int = 0
    detalhes: list[dict] | None = None


class ParcelaGeravelRead(BaseModel):
    parcela: int      # YYYYMM
    valor: Decimal


class EmitirDasParcelaPayload(BaseModel):
    parcela_ano_mes: int  # YYYYMM
