from datetime import datetime, timezone
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


@router.get("/empresa/{empresa_id}/excel")
def gerar_excel_empresa(empresa_id: int, db: Session = Depends(get_db)) -> FileResponse:
    destination = Path("storage/reports") / f"empresa_{empresa_id}.xlsx"
    file_path = ExcelReportService(db).gerar_excel_empresa(empresa_id, destination)
    return FileResponse(file_path, filename=Path(file_path).name)


@router.get("/geral/excel")
def gerar_excel_geral(db: Session = Depends(get_db)) -> FileResponse:
    destination = Path("storage/reports") / "relatorio_geral.xlsx"
    file_path = ExcelReportService(db).gerar_excel_geral(destination)
    return FileResponse(file_path, filename=Path(file_path).name)


@router.get("/resumo-mensal")
def resumo_mensal(db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_xmls = db.scalar(
        select(func.count()).select_from(DocumentoFiscal).where(DocumentoFiscal.created_at >= month_start)
    ) or 0
    total_nfe = db.scalar(
        select(func.count())
        .select_from(DocumentoFiscal)
        .where(DocumentoFiscal.tipo_documento == TipoDocumento.NFE, DocumentoFiscal.created_at >= month_start)
    ) or 0
    total_cte = db.scalar(
        select(func.count())
        .select_from(DocumentoFiscal)
        .where(DocumentoFiscal.tipo_documento == TipoDocumento.CTE, DocumentoFiscal.created_at >= month_start)
    ) or 0
    total_nfse = db.scalar(
        select(func.count())
        .select_from(DocumentoFiscal)
        .where(DocumentoFiscal.tipo_documento == TipoDocumento.NFSE, DocumentoFiscal.created_at >= month_start)
    ) or 0
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
        "gerado_em": now,
    }
