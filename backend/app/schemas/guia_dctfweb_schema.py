"""Schemas Pydantic para Guias DCTFWeb."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GuiaDctfwebRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    categoria: str
    ano_pa: str
    mes_pa: str | None
    dia_pa: str | None
    cno_afericao: int | None
    num_proc_reclamatoria: str | None
    origem: str  # 'ativa' | 'andamento'
    pdf_path: str
    emitida_em: datetime
    periodo_formatado: str


class GuiaDctfwebComEmpresa(GuiaDctfwebRead):
    empresa_cnpj: str | None = None
    empresa_razao_social: str | None = None


class EmitirGuiaDctfwebPayload(BaseModel):
    """Payload pra POST /guias-dctfweb/empresa/{id}/emitir-(ativa|andamento)."""
    categoria: str | int = Field(
        default="GERAL_MENSAL",
        description="Categoria DCTFWeb. Aceita string ('GERAL_MENSAL') ou int (40).",
    )
    ano_pa: str = Field(..., description="Ano período apuração (YYYY)")
    mes_pa: str | None = Field(
        default=None,
        description="Mês PA (01-12). Não usar para categorias 41 e 51 (13º).",
    )
    dia_pa: str | None = Field(
        default=None, description="Só para categoria 45 ESPETACULO_DESPORTIVO",
    )
    cno_afericao: int | None = Field(
        default=None, description="Número CNO. Só para categoria 44 AFERICAO",
    )
    num_proc_reclamatoria: str | None = Field(
        default=None, description="Só para categoria 46 RECLAMATORIA_TRABALHISTA",
    )
