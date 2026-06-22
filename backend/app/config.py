from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="PAC XML Downloader", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    use_mock_focus_nfe: bool = Field(default=True, alias="USE_MOCK_FOCUS_NFE")
    focus_base_url: str = Field(default="https://api.focusnfe.com.br", alias="FOCUS_BASE_URL")
    focus_ambiente: str = Field(default="producao", alias="FOCUS_AMBIENTE")
    # Token-mestre da conta Focus, usado apenas para POST /v2/empresas (cadastro
    # inicial). Operacoes por empresa usam o token retornado no cadastro, salvo em
    # `empresas.focus_token`.
    focus_master_token: str = Field(default="", alias="FOCUS_MASTER_TOKEN")

    # --- Integra Contador (Serpro) ---
    use_mock_integra: bool = Field(default=True, alias="USE_MOCK_INTEGRA")
    serpro_auth_url: str = Field(
        default="https://autenticacao.sapi.serpro.gov.br/authenticate",
        alias="SERPRO_AUTH_URL",
    )
    serpro_gateway_url: str = Field(
        default="https://gateway.apiserpro.serpro.gov.br/integra-contador/v1",
        alias="SERPRO_GATEWAY_URL",
    )
    serpro_consumer_key: str = Field(default="", alias="SERPRO_CONSUMER_KEY")
    serpro_consumer_secret: str = Field(default="", alias="SERPRO_CONSUMER_SECRET")
    # Caminho absoluto para o e-CNPJ A1 do escritorio (.pfx ou .p12).
    serpro_cert_path: str = Field(default="", alias="SERPRO_CERT_PATH")
    serpro_cert_password: str = Field(default="", alias="SERPRO_CERT_PASSWORD")
    # CNPJ do contratante (conta Serpro) e do autor do pedido (escritorio contabil).
    # Em escritorios pequenos os dois sao iguais.
    serpro_contratante_cnpj: str = Field(default="", alias="SERPRO_CONTRATANTE_CNPJ")
    serpro_autor_pedido_cnpj: str = Field(default="", alias="SERPRO_AUTOR_PEDIDO_CNPJ")

    # --- Robo SEFAZ (emissao de CNDs) ---
    use_mock_sefaz: bool = Field(default=True, alias="USE_MOCK_SEFAZ")
    captcha_api_key: str = Field(default="", alias="CAPTCHA_API_KEY")
    captcha_provider: str = Field(default="2captcha", alias="CAPTCHA_PROVIDER")

    # --- Infosimples (API de scraping autorizado para CNDs + PGFN) ---
    # Pré-pago por volume: R$ 0,20/consulta (faixa 1-500/mês), cai pra R$ 0,16
    # acima de 500, R$ 0,14 acima de 2k. Franquia mínima R$ 100/mês mesmo
    # sem uso. Cache agressivo no provider (TTL 30d em CND válida, 7d em PGFN
    # parcelamentos) mantém o volume baixo.
    use_mock_infosimples: bool = Field(default=True, alias="USE_MOCK_INFOSIMPLES")
    infosimples_token: str = Field(default="", alias="INFOSIMPLES_TOKEN")
    infosimples_base_url: str = Field(
        default="https://api.infosimples.com/api/v2", alias="INFOSIMPLES_BASE_URL",
    )
    infosimples_timeout: int = Field(default=180, alias="INFOSIMPLES_TIMEOUT")
    # Quantos dias guardar cache de CND válida antes de chamar API de novo.
    # CND VALIDA (validade > 30d) = 30 dias de cache (renovação mensal natural)
    # CND A_VENCER (validade <= 30d) = 7 dias (re-checa semanalmente)
    # CND VENCIDA = 1 dia (tenta diariamente até nova emissão)
    infosimples_cache_cnd_dias: int = Field(default=30, alias="INFOSIMPLES_CACHE_CND_DIAS")
    infosimples_cache_pgfn_dias: int = Field(default=7, alias="INFOSIMPLES_CACHE_PGFN_DIAS")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")

    # Modo "eager": roda task Celery SÍNCRONA no mesmo processo, sem precisar
    # de Redis/worker. Útil em dev local. EM PRODUÇÃO SEMPRE False
    # (deixar Celery worker separado pra não travar requests HTTP).
    celery_task_always_eager: bool = Field(
        default=False, alias="CELERY_TASK_ALWAYS_EAGER",
    )
    storage_path: Path = Field(default=Path("storage/xmls"), alias="STORAGE_PATH")

    access_token_expire_minutes: int = Field(default=480, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")

    # --- E-mail transacional (Resend) ---
    # Domínio pacgestao.com.br já VERIFICADO no Resend (SPF/DKIM ok). Quando a
    # RESEND_API_KEY estiver vazia, o envio é pulado e o link do convite volta
    # na resposta pra colar manualmente (degrada com elegância, não quebra).
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(
        default="PAC Gestão <nao-responda@pacgestao.com.br>", alias="EMAIL_FROM",
    )
    # Base do portal do cliente, usada no link do convite (definir senha).
    portal_url: str = Field(default="https://pacgestao.com.br/portal", alias="PORTAL_URL")

    # --- Conector de SAÍDAS por e-mail (Nível 2 do conector) ---
    # Caixa única (ex.: notas@pacgestao.com.br) onde o cliente manda os XMLs/ZIP
    # das próprias notas. O PAC lê por IMAP (TLS), extrai os anexos e joga no
    # mesmo motor de importação, roteando por CNPJ emitente. Senha SÓ no env
    # (nunca no código/DB). Quando IMAP_HOST/USER/PASSWORD vazios, o conector
    # fica desligado (degrada com elegância).
    imap_host: str = Field(default="", alias="IMAP_HOST")
    imap_port: int = Field(default=993, alias="IMAP_PORT")
    imap_user: str = Field(default="", alias="IMAP_USER")
    imap_password: str = Field(default="", alias="IMAP_PASSWORD")
    imap_folder: str = Field(default="INBOX", alias="IMAP_FOLDER")
    # Token pro cron externo disparar a leitura (header X-Cron-Token).
    conector_email_token: str = Field(default="", alias="CONECTOR_EMAIL_TOKEN")
    # Teto de e-mails processados por execução (evita rodada eterna).
    imap_max_emails: int = Field(default=200, alias="IMAP_MAX_EMAILS")

    @property
    def conector_email_ativo(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_password)
    first_superuser_email: str = Field(default="admin@pacxml.com.br", alias="FIRST_SUPERUSER_EMAIL")
    first_superuser_password: str = Field(default="admin123", alias="FIRST_SUPERUSER_PASSWORD")

    # CORS — origens separadas por virgula (ex: "https://app.dominio.com.br,http://localhost:3000")
    # Default cobre desenvolvimento local; em producao definir explicitamente.
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="ALLOWED_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
