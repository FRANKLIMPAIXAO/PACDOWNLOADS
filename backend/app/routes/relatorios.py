from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.consulta_log import ConsultaLog
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.services.auth_service import get_current_user
from app.services.excel_report import ExcelReportService


router = APIRouter(prefix="/relatorios", tags=["relatorios"], dependencies=[Depends(get_current_user)])

# Brasil sem horário de verão desde 2019 → offset fixo -03:00 pros limites de
# competência (data_emissao é timestamptz; comparar contra tz-aware evita
# deslocar o mês nas bordas por causa do fuso do servidor).
BR_TZ = timezone(timedelta(hours=-3))


def _competencia_bounds(competencia: str | None) -> tuple[datetime | None, datetime | None]:
    """'YYYY-MM' → (início do mês, início do mês seguinte) em horário de Brasília.
    Inválido/ausente → (None, None) = sem filtro (relatório completo)."""
    if not competencia:
        return None, None
    try:
        ano_s, mes_s = competencia.split("-")
        ano, mes = int(ano_s), int(mes_s)
        if not (1 <= mes <= 12):
            return None, None
        inicio = datetime(ano, mes, 1, tzinfo=BR_TZ)
        fim = datetime(ano + 1, 1, 1, tzinfo=BR_TZ) if mes == 12 else datetime(ano, mes + 1, 1, tzinfo=BR_TZ)
        return inicio, fim
    except (ValueError, AttributeError):
        return None, None


@router.get("/empresa/{empresa_id}/excel")
def gerar_excel_empresa(
    empresa_id: int, competencia: str | None = None, db: Session = Depends(get_db)
) -> FileResponse:
    data_min, data_max = _competencia_bounds(competencia)
    sufixo = f"_{competencia}" if data_min else ""
    destination = Path("storage/reports") / f"empresa_{empresa_id}{sufixo}.xlsx"
    file_path = ExcelReportService(db).gerar_excel_empresa(empresa_id, destination, data_min, data_max)
    return FileResponse(file_path, filename=Path(file_path).name)


@router.get("/geral/excel")
def gerar_excel_geral(competencia: str | None = None, db: Session = Depends(get_db)) -> FileResponse:
    data_min, data_max = _competencia_bounds(competencia)
    sufixo = f"_{competencia}" if data_min else ""
    destination = Path("storage/reports") / f"relatorio_geral{sufixo}.xlsx"
    file_path = ExcelReportService(db).gerar_excel_geral(destination, data_min, data_max)
    return FileResponse(file_path, filename=Path(file_path).name)


@router.get("/resumo-mensal")
def resumo_mensal(competencia: str | None = None, db: Session = Depends(get_db)) -> dict:
    # Números por COMPETÊNCIA (mês de emissão) — casa com o Excel. Sem competência,
    # usa o mês corrente em horário de Brasília.
    data_min, data_max = _competencia_bounds(competencia)
    if data_min is None:
        agora = datetime.now(BR_TZ)
        data_min = datetime(agora.year, agora.month, 1, tzinfo=BR_TZ)
        data_max = (
            datetime(agora.year + 1, 1, 1, tzinfo=BR_TZ)
            if agora.month == 12
            else datetime(agora.year, agora.month + 1, 1, tzinfo=BR_TZ)
        )

    def _contar(*extra) -> int:
        return db.scalar(
            select(func.count())
            .select_from(DocumentoFiscal)
            .where(
                DocumentoFiscal.data_emissao >= data_min,
                DocumentoFiscal.data_emissao < data_max,
                *extra,
            )
        ) or 0

    total_xmls = _contar()
    total_nfe = _contar(DocumentoFiscal.tipo_documento == TipoDocumento.NFE)
    total_cte = _contar(DocumentoFiscal.tipo_documento == TipoDocumento.CTE)
    total_nfse = _contar(DocumentoFiscal.tipo_documento == TipoDocumento.NFSE)
    ultimo_log = db.scalar(select(ConsultaLog).order_by(ConsultaLog.created_at.desc()).limit(1))
    empresas_com_erro = db.scalar(
        select(func.count(func.distinct(ConsultaLog.empresa_id))).where(ConsultaLog.status == "erro")
    ) or 0
    return {
        "total_xmls_mes": total_xmls,
        "total_nfe": total_nfe,
        "total_cte": total_cte,
        "total_nfse": total_nfse,
        "empresas_com_erro": empresas_com_erro,
        "ultimo_horario_consulta": ultimo_log.created_at if ultimo_log else None,
        "gerado_em": datetime.now(BR_TZ),
    }
