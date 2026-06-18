from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.certidao import Certidao, TipoCertidao
from app.models.empresa import Empresa
from app.schemas.certidao_schema import (
    CertidaoCreate,
    CertidaoRead,
    CertidaoUpdate,
    CndDashboardResposta,
)
from app.services.auth_service import get_current_user
from app.services.cnd_robo_service import CndRoboService


router = APIRouter(prefix="/cnds", tags=["cnds"], dependencies=[Depends(get_current_user)])


_settings = get_settings()


def _certidao_to_read(c: Certidao) -> CertidaoRead:
    situacao_fiscal, pendencias = c.regularidade()
    return CertidaoRead(
        id=c.id,
        empresa_id=c.empresa_id,
        tipo=c.tipo.value if hasattr(c.tipo, "value") else str(c.tipo),
        numero=c.numero,
        data_emissao=c.data_emissao,
        data_validade=c.data_validade,
        pdf_path=c.pdf_path,
        observacoes=c.observacoes,
        created_at=c.created_at,
        updated_at=c.updated_at,
        status=c.status(),
        dias_para_vencer=c.dias_para_vencer,
        situacao_fiscal=situacao_fiscal,
        pendencias=pendencias,
    )


def _cert_ok(cr: CertidaoRead | None) -> bool:
    """Certidão conta como OK no score só se está válida pela DATA e SEM
    pendência/verificação (uma SITFIS irregular ou não-lida não pontua)."""
    return bool(
        cr and cr.status == "VALIDA"
        and cr.situacao_fiscal not in ("pendencias", "verificar")
    )


@router.get("/dashboard", response_model=list[CndDashboardResposta])
def cnd_dashboard(db: Session = Depends(get_db)) -> list[CndDashboardResposta]:
    """Resumo de CNDs por empresa: para cada empresa, pega a CND mais recente
    de cada tipo (5 tipos). Score = fracao de tipos com status VALIDA."""
    empresas = db.scalars(
        select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.razao_social)
    ).all()
    resultado: list[CndDashboardResposta] = []
    for empresa in empresas:
        slot: dict[str, CertidaoRead | None] = {
            "FEDERAL": None, "FEDERAL_OFICIAL": None,
            "FGTS": None, "TRABALHISTA": None,
            "ESTADUAL": None, "MUNICIPAL": None,
        }
        for tipo in slot.keys():
            cert = db.scalar(
                select(Certidao)
                .where(
                    Certidao.empresa_id == empresa.id,
                    Certidao.tipo == TipoCertidao(tipo),
                )
                .order_by(Certidao.data_validade.desc(), Certidao.id.desc())
            )
            if cert:
                slot[tipo] = _certidao_to_read(cert)
        # Score considera 5 tipos basicos (FEDERAL conta uma so vez — usa SITFIS
        # OU CND oficial, o que estiver valido E regular). FEDERAL_OFICIAL nao
        # soma extra. CND com pendencia/nao-verificada NAO pontua.
        federal_ok = _cert_ok(slot["FEDERAL"]) or _cert_ok(slot["FEDERAL_OFICIAL"])
        validos = (
            (1 if federal_ok else 0)
            + sum(
                1 for k in ("FGTS", "TRABALHISTA", "ESTADUAL", "MUNICIPAL")
                if _cert_ok(slot[k])
            )
        )
        resultado.append(
            CndDashboardResposta(
                empresa_id=empresa.id,
                empresa_razao_social=empresa.razao_social,
                cnpj=empresa.cnpj,
                federal=slot["FEDERAL"],
                federal_oficial=slot["FEDERAL_OFICIAL"],
                fgts=slot["FGTS"],
                trabalhista=slot["TRABALHISTA"],
                estadual=slot["ESTADUAL"],
                municipal=slot["MUNICIPAL"],
                score=validos / 5.0,
            )
        )
    return resultado


@router.get("/empresa/{empresa_id}", response_model=list[CertidaoRead])
def listar_por_empresa(empresa_id: int, db: Session = Depends(get_db)) -> list[CertidaoRead]:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    certs = db.scalars(
        select(Certidao)
        .where(Certidao.empresa_id == empresa_id)
        .order_by(Certidao.tipo, Certidao.data_validade.desc())
    ).all()
    return [_certidao_to_read(c) for c in certs]


@router.post(
    "/empresa/{empresa_id}",
    response_model=CertidaoRead,
    status_code=status.HTTP_201_CREATED,
)
def criar(empresa_id: int, payload: CertidaoCreate, db: Session = Depends(get_db)) -> CertidaoRead:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    cert = Certidao(
        empresa_id=empresa_id,
        tipo=TipoCertidao(payload.tipo),
        numero=payload.numero,
        data_emissao=payload.data_emissao,
        data_validade=payload.data_validade,
        observacoes=payload.observacoes,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return _certidao_to_read(cert)


@router.put("/{certidao_id}", response_model=CertidaoRead)
def atualizar(certidao_id: int, payload: CertidaoUpdate, db: Session = Depends(get_db)) -> CertidaoRead:
    cert = db.get(Certidao, certidao_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certidao nao encontrada")
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(cert, k, v)
    db.commit()
    db.refresh(cert)
    return _certidao_to_read(cert)


@router.delete("/{certidao_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(certidao_id: int, db: Session = Depends(get_db)) -> None:
    cert = db.get(Certidao, certidao_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certidao nao encontrada")
    if cert.pdf_path:
        try:
            Path(cert.pdf_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(cert)
    db.commit()
    return None


@router.put("/{certidao_id}/pdf", response_model=CertidaoRead)
async def upload_pdf(
    certidao_id: int,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> CertidaoRead:
    cert = db.get(Certidao, certidao_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certidao nao encontrada")
    if not arquivo.filename or not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pdf")
    storage_root = Path(_settings.storage_path).parent / "cnds"
    storage_root.mkdir(parents=True, exist_ok=True)
    path = storage_root / f"cnd-{cert.id}-{arquivo.filename}"
    content = await arquivo.read()
    path.write_bytes(content)
    cert.pdf_path = str(path)
    db.commit()
    db.refresh(cert)
    return _certidao_to_read(cert)


@router.get("/{certidao_id}/pdf")
def baixar_pdf(certidao_id: int, db: Session = Depends(get_db)):
    cert = db.get(Certidao, certidao_id)
    if not cert or not cert.pdf_path:
        raise HTTPException(status_code=404, detail="PDF nao encontrado")
    p = Path(cert.pdf_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="PDF removido do storage")
    return FileResponse(path=str(p), filename=p.name, media_type="application/pdf")


# --- Robo SEFAZ: emissao automatica ---


@router.post("/empresa/{empresa_id}/renovar", response_model=CertidaoRead)
def renovar_cnd_automatica(
    empresa_id: int, tipo: str, db: Session = Depends(get_db),
):
    """Emite/renova um comprovante de regularidade fiscal automaticamente.

    Query param `tipo`:
    - FEDERAL          -> SITFIS via Integra Contador (uso interno)
    - FEDERAL_OFICIAL  -> CND oficial RFB+PGFN (Playwright + captcha)
    - TRABALHISTA      -> CNDT TST (Playwright + captcha)
    - FGTS             -> CRF Caixa (Playwright + captcha)

    Se `USE_MOCK_SEFAZ=true`, devolve PDF mockado para validar fluxo.
    """
    # Tipos com provider automatizado (Integra ou Infosimples).
    # TRABALHISTA e MUNICIPAL ficam de fora — cadastro manual via POST /cnds/empresa/{id}.
    tipos_automatizados = ("FEDERAL", "FEDERAL_OFICIAL", "FGTS", "ESTADUAL")
    if tipo not in tipos_automatizados:
        raise HTTPException(
            status_code=400,
            detail=(
                f"tipo {tipo!r} não tem renovação automática. "
                f"Aceitos: {', '.join(tipos_automatizados)}. "
                "TRABALHISTA/MUNICIPAL: cadastre manualmente via POST /cnds/empresa/{id}."
            ),
        )
    cert = CndRoboService(db).renovar_cnd(empresa_id, tipo)  # type: ignore[arg-type]
    return _certidao_to_read(cert)


@router.post("/renovar-vencendo")
def renovar_vencendo(janela_dias: int = 7, db: Session = Depends(get_db)):
    """Renova todas CNDs vencendo em <= janela_dias OU ja vencidas, p/ todas
    empresas ativas. Usado pelo Celery beat semanal."""
    return CndRoboService(db).renovar_vencendo(janela_dias=janela_dias)
