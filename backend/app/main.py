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
from app.models.situacao_fiscal import SituacaoFiscal  # noqa: F401
from app.models.usuario import Usuario
from app.routes import agenda, apuracoes, auth, certidoes, dashboard, documentos, empresas, guias_das, guias_dctfweb, guias_fgts, integra, parcelamentos_pgfn, parcelamentos_simples, relatorios, robo, robo_sefaz
from app.services.auth_service import hash_password


settings = get_settings()


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


app.include_router(auth.router, prefix=settings.api_v1_prefix)
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
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
