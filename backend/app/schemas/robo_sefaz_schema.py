"""Schemas Pydantic para o robô SEFAZ-GO."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DispararRoboSefazPayload(BaseModel):
    """Payload opcional para disparar robô manualmente.

    Se omitido, default = mês anterior, todas as empresas com cert A1.
    """
    empresa_id: int | None = Field(
        default=None,
        description="Se preenchido, roda só essa empresa. Caso contrário roda todas.",
    )
    periodo_inicio: date | None = Field(
        default=None,
        description="Default = primeiro dia do mês anterior",
    )
    periodo_fim: date | None = Field(
        default=None,
        description="Default = último dia do mês anterior",
    )
    modo: str = Field(
        default="documentos",
        description="'documentos' (NFes + eventos) ou 'eventos' (regularização: "
                    "só procEventoNFe do período pra aplicar cancelamentos).",
    )


class ExecucaoRoboSefazRead(BaseModel):
    """Resposta resumida de execução (usada em listagem)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    disparo: str
    uf: str
    status: str
    modo: str = "documentos"
    periodo_inicio: date
    periodo_fim: date
    empresa_id: int | None
    iniciado_em: datetime
    finalizado_em: datetime | None
    total_empresas: int
    com_zip: int
    sem_notas: int
    erros: int
    persistidos: int
    duplicados: int
    motivo_erro: str | None
    duracao_segundos: float | None


class DetalheEmpresaExecucao(BaseModel):
    """Resultado de uma empresa específica dentro de uma execução."""
    empresa_id: int | None = None
    cnpj: str | None = None
    razao_social: str | None = None
    sucesso: bool = False
    motivo: str | None = None
    zip_path: str | None = None
    upload_pac: dict | None = None
    duracao_segundos: float = 0.0
    sem_resultados: bool = False


class ExecucaoRoboSefazDetailRead(ExecucaoRoboSefazRead):
    """Resposta completa, com detalhes empresa-a-empresa."""
    detalhes: list[DetalheEmpresaExecucao] | None = None
