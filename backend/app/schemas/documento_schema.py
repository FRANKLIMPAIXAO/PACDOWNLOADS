from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.documento_fiscal import TipoDocumento


class DocumentoFiscalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    tipo_documento: TipoDocumento
    chave_acesso: str
    numero: str | None = None
    serie: str | None = None
    data_emissao: datetime | None = None
    cnpj_emitente: str | None = None
    nome_emitente: str | None = None
    cnpj_destinatario: str | None = None
    nome_destinatario: str | None = None
    valor_total: Decimal | None = None
    status: str
    xml_path: str
    json_original: dict | None = None
    cancelada: bool = False
    cancelada_em: date | None = None
    motivo_cancelamento: str | None = None
    protocolo_cancelamento: str | None = None
    # 'emitida' = saída (própria empresa emitiu); 'recebida' = entrada (fornecedor
    # emitiu contra a empresa). Front usa pra esconder botão "Manifestar" em saídas.
    origem: str | None = None
    created_at: datetime


class DocumentoFiltro(BaseModel):
    empresa_id: int | None = None
    tipo_documento: TipoDocumento | None = None
    data_inicio: datetime | None = None
    data_fim: datetime | None = None
