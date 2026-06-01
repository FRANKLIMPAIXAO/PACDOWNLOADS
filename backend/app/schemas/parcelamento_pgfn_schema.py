"""Schemas Pydantic para Parcelamentos PGFN (Dívida Ativa)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ParcelamentoPgfnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    modalidade: str
    numero: str
    data_pedido: date | None
    situacao: str | None
    valor_total: Decimal | None
    valor_total_pago: Decimal | None
    quantidade_parcelas: int | None
    parcelas_pagas: int | None
    parcelas_restantes: int | None
    percentual_concluido: float | None
    sincronizado_em: datetime


class ParcelamentoPgfnComEmpresa(ParcelamentoPgfnRead):
    empresa_cnpj: str | None = None
    empresa_razao_social: str | None = None


class SyncPgfnResposta(BaseModel):
    novos: int = 0
    atualizados: int = 0
    removidos: int = 0
    erros: int = 0
    veio_do_cache: bool = False
    detalhes: list[dict] | None = None
