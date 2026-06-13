from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
# Importar todos os models antes de Base.metadata.create_all garantir que sao
# registrados na metadata.
from app.models.apuracao import Apuracao  # noqa: F401
from app.models.certidao import Certidao  # noqa: F401
from app.models.consulta_log import ConsultaLog  # noqa: F401
from app.models.documento_fiscal import DocumentoFiscal  # noqa: F401
from app.models.empresa import Empresa  # noqa: F401
from app.models.mensagem_ecac import MensagemEcac  # noqa: F401
from app.models.procuracao import Procuracao  # noqa: F401
from app.models.receita_mensal import ReceitaMensal  # noqa: F401
from app.models.situacao_fiscal import SituacaoFiscal  # noqa: F401
from app.models.usuario import Usuario
from app.routes import agenda, apuracoes, auth, certidoes, dashboard, documentos, empresas, guias_das, guias_dctfweb, guias_fgts, integra, parcelamentos_pgfn, parcelamentos_simples, receitas_mensais, relatorios, robo, robo_sefaz, usuarios
from app.services.auth_service import hash_password


settings = get_settings()

# Marcador de build — BUMP a cada deploy importante. Como o Easypanel não passa
# BUILD_COMMIT no build (commit fica "unknown"), este é o sinal confiável pra
# saber, via GET /version, se o deploy pegou o código novo (cache stale é
# recorrente). Formato livre: AAAA-MM-DD + resumo curto.
APP_BUILD_TAG = "2026-06-13-faturamento-tpnf"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.scalar(select(Usuario).where(Usuario.email == settings.first_superuser_email))
        if not admin:
            db.add(
                Usuario(
                    nome="Administrador",
                    email=settings.first_superuser_email,
                    senha_hash=hash_password(settings.first_superuser_password),
                    ativo=True,
                    is_admin=True,
                )
            )
            db.commit()
        # Recupera execuções do robô SEFAZ presas em 'rodando'/'pendente' — em
        # modo eager a thread morre junto com o processo no restart (deploy),
        # deixando a linha zumbi. Finaliza como erro pra não ficar eterna.
        try:
            from app.services.robo_sefaz_service import RoboSefazService
            RoboSefazService(db).recuperar_execucoes_zumbis()
        except Exception:  # noqa: BLE001 — nunca bloquear a subida do app por isso
            import logging
            logging.getLogger(__name__).exception("Falha ao recuperar execuções zumbis do robô")
        yield
    finally:
        db.close()


app = FastAPI(title=settings.app_name, debug=settings.app_debug, lifespan=lifespan)

# CORS — origens lidas de `ALLOWED_ORIGINS` no .env (csv).
# Dev: http://localhost:3000. Producao: https://app.SEUDOMINIO.com.br.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok", "app": settings.app_name, "mock_provider": settings.use_mock_focus_nfe}


@app.get("/version")
def version() -> dict:
    """Diagnostico do que esta rodando em prod.

    Util pra confirmar que o deploy do Easypanel pegou o codigo novo
    (problema recorrente — imagem Docker reaproveitada do cache).

    Le `BUILD_COMMIT` e `BUILD_DATE` do ambiente (setadas no Dockerfile
    via ARG no build) e tambem tenta ler do .git se disponivel.
    """
    import os
    from pathlib import Path

    commit = os.environ.get("BUILD_COMMIT", "unknown")
    build_date = os.environ.get("BUILD_DATE", "unknown")

    # Fallback: tenta ler do .git se foi copiado pro container
    if commit == "unknown":
        git_head = Path("/app/.git/HEAD")
        if git_head.exists():
            try:
                ref = git_head.read_text().strip()
                if ref.startswith("ref: "):
                    ref_path = Path("/app/.git") / ref[5:]
                    if ref_path.exists():
                        commit = ref_path.read_text().strip()[:12]
                else:
                    commit = ref[:12]
            except OSError:
                pass

    return {
        "app": settings.app_name,
        "build_tag": APP_BUILD_TAG,
        "commit": commit,
        "build_date": build_date,
        "mock_provider": settings.use_mock_focus_nfe,
        "use_mock_integra": getattr(settings, "use_mock_integra", None),
        "use_mock_infosimples": getattr(settings, "use_mock_infosimples", None),
    }


app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(usuarios.router, prefix=settings.api_v1_prefix)
app.include_router(empresas.router, prefix=settings.api_v1_prefix)
app.include_router(documentos.router, prefix=settings.api_v1_prefix)
app.include_router(robo.router, prefix=settings.api_v1_prefix)
app.include_router(robo_sefaz.router, prefix=settings.api_v1_prefix)
app.include_router(guias_das.router, prefix=settings.api_v1_prefix)
app.include_router(parcelamentos_simples.router, prefix=settings.api_v1_prefix)
app.include_router(parcelamentos_pgfn.router, prefix=settings.api_v1_prefix)
app.include_router(guias_dctfweb.router, prefix=settings.api_v1_prefix)
app.include_router(guias_fgts.router, prefix=settings.api_v1_prefix)
app.include_router(relatorios.router, prefix=settings.api_v1_prefix)
app.include_router(integra.router, prefix=settings.api_v1_prefix)
app.include_router(certidoes.router, prefix=settings.api_v1_prefix)
app.include_router(agenda.router, prefix=settings.api_v1_prefix)
app.include_router(apuracoes.router, prefix=settings.api_v1_prefix)
app.include_router(receitas_mensais.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
