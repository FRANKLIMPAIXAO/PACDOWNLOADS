from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MensagemEcacRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    isn_msg: str
    assunto: str | None = None
    remetente: str | None = None
    data_envio: datetime | None = None
    indicador_leitura: str | None = None
    indicador_relevancia: str | None = None
    sincronizada_em: datetime


class MensagemEcacDetalhe(MensagemEcacRead):
    conteudo_html: str | None = None


class SyncCaixaPostalResposta(BaseModel):
    sincronizadas: int
    novas: int
    atualizadas: int
    erros: int


class ProcuracaoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    cnpj_outorgante: str
    cnpj_outorgado: str
    data_inicio: str | None = None
    data_fim: str | None = None
    situacao: str
    servicos_autorizados: list | None = None
    sincronizada_em: datetime


class DteResposta(BaseModel):
    cnpj: str | None = None
    indicador_optante: bool | None = None
    data_adesao: str | None = None
    raw: dict[str, Any] | None = None


class SituacaoFiscalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    protocolo: str | None = None
    pdf_path: str | None = None
    status: str
    gerada_em: datetime


class PagamentoRead(BaseModel):
    numero_documento: str | None = None
    codigo_receita: str | None = None
    descricao_receita: str | None = None
    data_arrecadacao: str | None = None
    valor_total: float | None = None
