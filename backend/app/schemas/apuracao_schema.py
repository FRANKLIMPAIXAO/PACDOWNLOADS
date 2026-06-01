from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApuracaoCreate(BaseModel):
    empresa_id: int
    ano_mes: str  # "YYYYMM"
    receita_bruta: float
    receitas_segregadas: list[dict[str, Any]] | None = None


class ApuracaoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    ano_mes: str
    regime: str
    status: str
    receita_bruta: Decimal | None = None
    valor_devido: Decimal | None = None
    numero_declaracao: str | None = None
    recibo: str | None = None
    transmitida_em: datetime | None = None
    das_numero_documento: str | None = None
    das_codigo_barras: str | None = None
    das_data_vencimento: str | None = None
    das_pdf_path: str | None = None
    receitas_segregadas: list | None = None
    created_at: datetime
    updated_at: datetime


class ResumoMesResposta(BaseModel):
    ano_mes: str
    total_empresas_ativas: int
    apuracoes_geradas: int
    pendentes: int
    transmitidas: int
    das_gerados: int
    pagos: int
    valor_devido_total: float
    valor_pago: float
    empresas_pendentes: list[dict[str, Any]]
