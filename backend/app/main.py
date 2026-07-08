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
from app.models.cliente_empresa import ClienteEmpresa  # noqa: F401
from app.models.cobranca_portal import CobrancaPortal  # noqa: F401
from app.models.conector_email_execucao import ConectorEmailExecucao  # noqa: F401
from app.models.consulta_log import ConsultaLog  # noqa: F401
from app.models.cron_execucao import CronExecucao  # noqa: F401
from app.models.documento_escritorio import DocumentoEscritorio  # noqa: F401
from app.models.documento_fiscal import DocumentoFiscal  # noqa: F401
from app.models.empresa import Empresa  # noqa: F401
from app.models.mensagem_ecac import MensagemEcac  # noqa: F401
from app.models.portal_acesso_log import PortalAcessoLog  # noqa: F401
from app.models.procuracao import Procuracao  # noqa: F401
from app.models.push_subscription import PushSubscription  # noqa: F401
from app.models.receita_mensal import ReceitaMensal  # noqa: F401
from app.models.situacao_fiscal import SituacaoFiscal  # noqa: F401
from app.models.solicitacao_admissao import SolicitacaoAdmissao  # noqa: F401
from app.models.usuario import Usuario
from app.routes import admissoes, agenda, apuracoes, auth, certidoes, cobrancas, conector_email, cte_distribuicao, dashboard, dfe_distribuicao, docs_escritorio, documentos, empresas, guias_das, guias_dctfweb, guias_fgts, integra, integracao, nfse_adn, pacchat_webhook, parcelamentos_pgfn, parcelamentos_simples, portal, prevencao, receitas_mensais, relatorios, robo, robo_sefaz, usuarios
from app.services.auth_service import hash_password


settings = get_settings()

# Marcador de build — BUMP a cada deploy importante. Como o Easypanel não passa
# BUILD_COMMIT no build (commit fica "unknown"), este é o sinal confiável pra
# saber, via GET /version, se o deploy pegou o código novo (cache stale é
# recorrente). Formato livre: AAAA-MM-DD + resumo curto.
APP_BUILD_TAG = "2026-07-08-webpush-diag-version"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # BLINDAGEM (lição do deploy do portal 16/06): NADA no startup pode impedir
    # o app de SUBIR. Se algo aqui falhar (ex.: uma migration que não aplicou e
    # deixou o schema defasado), logamos e seguimos. Melhor o app no ar com uma
    # feature quebrada (erro 500 claro no endpoint X) do que o sistema INTEIRO
    # fora — quando o app nem sobe, o Traefik responde 502 SEM header CORS e o
    # browser mostra um enganoso "erro de CORS / Failed to fetch".
    import logging
    log = logging.getLogger(__name__)
    # AVISO DE SEGURANÇA (não derruba — respeita a blindagem acima). Em produção,
    # SECRET_KEY fraco = JWT forjável + senhas dos certs decifráveis. Veja o
    # estado completo em GET /usuarios/seguranca-diagnostico (admin).
    _sk = settings.secret_key or ""
    if settings.is_production and (_sk in ("", "change-me") or len(_sk) < 32):
        log.warning(
            "🔴 SEGURANCA: SECRET_KEY fraco/default em PRODUCAO — assina JWT e cifra "
            "as senhas dos certificados. Configure um valor forte e unico (>=32 chars) JA."
        )
    if settings.is_production and settings.first_superuser_password == "admin123":
        log.warning("🔴 SEGURANCA: senha de admin no default 'admin123' em PRODUCAO — troque JA.")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:  # noqa: BLE001
        log.exception("Falha no create_all do startup (seguindo mesmo assim)")
    # ÍNDICES DE PERFORMANCE (idempotente, sem migration manual). `data_emissao`
    # não tinha índice e é o filtro/ordenação da lista, do resumo e da agregação
    # mensal do dashboard → com 14k+ docs virava varredura de tabela inteira em 3
    # lugares. CREATE INDEX IF NOT EXISTS é no-op após a 1ª vez (Postgres + SQLite).
    # CADA DDL em SUA PRÓPRIA transação + try/except. CRÍTICO: se rodarem juntas
    # num só `begin()` e UMA falha, a transação inteira faz rollback e as colunas
    # NÃO são criadas — foi o que derrubou o login (model lê `senha_provisoria`,
    # coluna inexistente → 500 em TODA query de Usuario). Isolado, uma falha não
    # contamina as outras. ADD IF NOT EXISTS ANTES de servir (trauma do is_cliente).
    from sqlalchemy import text
    _ddl_startup = [
        "CREATE INDEX IF NOT EXISTS ix_docfiscal_data_emissao ON documentos_fiscais (data_emissao)",
        "CREATE INDEX IF NOT EXISTS ix_docfiscal_empresa_data ON documentos_fiscais (empresa_id, data_emissao)",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS anexo_servico VARCHAR(4)",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS senha_provisoria BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS so_servico BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS motivo_inativacao VARCHAR(255)",
    ]
    for _stmt in _ddl_startup:
        try:
            with engine.begin() as conn:
                # lock_timeout: se uma conexão `idle in transaction` estiver
                # segurando lock na tabela, o ALTER FALHA RÁPIDO (4s) em vez de
                # pendurar o startup inteiro (foi o que causou o crash loop — o
                # app nunca ficava pronto e o Easypanel reiniciava em loop).
                conn.execute(text("SET LOCAL lock_timeout = '4s'"))
                conn.execute(text(_stmt))
        except Exception:  # noqa: BLE001 — nunca derrubar o app por DDL de startup
            log.exception("Falha no DDL de startup (seguindo): %s", _stmt)
    db = SessionLocal()
    try:
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
        except Exception:  # noqa: BLE001 — nunca derrubar o app por causa do bootstrap
            db.rollback()
            log.exception("Bootstrap do admin falhou no startup (seguindo mesmo assim)")
        # Recupera execuções do robô SEFAZ presas em 'rodando'/'pendente' — em
        # modo eager a thread morre junto com o processo no restart (deploy),
        # deixando a linha zumbi. Finaliza como erro pra não ficar eterna.
        try:
            from app.services.robo_sefaz_service import RoboSefazService
            RoboSefazService(db).recuperar_execucoes_zumbis()
        except Exception:  # noqa: BLE001 — nunca bloquear a subida do app por isso
            log.exception("Falha ao recuperar execuções zumbis do robô")
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

    # Diagnóstico do Web Push SEM expor segredo: só booleans (a chave PÚBLICA não
    # é segredo; a privada nunca sai). push_web_ok=true → VAPID configurado.
    _vapid_pub = bool(getattr(settings, "vapid_public_key", ""))
    _vapid_priv = bool(getattr(settings, "vapid_private_key", ""))
    try:
        import pywebpush  # noqa: F401
        _pywebpush_ok = True
    except Exception:  # noqa: BLE001
        _pywebpush_ok = False
    return {
        "app": settings.app_name,
        "build_tag": APP_BUILD_TAG,
        "commit": commit,
        "build_date": build_date,
        "mock_provider": settings.use_mock_focus_nfe,
        "use_mock_integra": getattr(settings, "use_mock_integra", None),
        "use_mock_infosimples": getattr(settings, "use_mock_infosimples", None),
        # Web Push: os 3 têm que ser true pra notificação funcionar.
        "push_web_ok": _vapid_pub and _vapid_priv and _pywebpush_ok,
        "vapid_publica_setada": _vapid_pub,
        "vapid_privada_setada": _vapid_priv,
        "pywebpush_instalado": _pywebpush_ok,
    }


app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(usuarios.router, prefix=settings.api_v1_prefix)
app.include_router(empresas.router, prefix=settings.api_v1_prefix)
app.include_router(documentos.router, prefix=settings.api_v1_prefix)
app.include_router(dfe_distribuicao.router, prefix=settings.api_v1_prefix)
app.include_router(dfe_distribuicao.router_cron, prefix=settings.api_v1_prefix)
app.include_router(cte_distribuicao.router, prefix=settings.api_v1_prefix)
app.include_router(cte_distribuicao.router_cron, prefix=settings.api_v1_prefix)
app.include_router(portal.router, prefix=settings.api_v1_prefix)
app.include_router(pacchat_webhook.router, prefix=settings.api_v1_prefix)
app.include_router(prevencao.router, prefix=settings.api_v1_prefix)
app.include_router(conector_email.router, prefix=settings.api_v1_prefix)
app.include_router(conector_email.router_cron, prefix=settings.api_v1_prefix)
app.include_router(docs_escritorio.router, prefix=settings.api_v1_prefix)
app.include_router(admissoes.router, prefix=settings.api_v1_prefix)
app.include_router(integracao.router, prefix=settings.api_v1_prefix)
app.include_router(nfse_adn.router, prefix=settings.api_v1_prefix)
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
app.include_router(cobrancas.router, prefix=settings.api_v1_prefix)
app.include_router(agenda.router, prefix=settings.api_v1_prefix)
app.include_router(apuracoes.router, prefix=settings.api_v1_prefix)
app.include_router(receitas_mensais.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
