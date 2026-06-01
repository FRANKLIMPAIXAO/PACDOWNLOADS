from celery import Celery
from celery.schedules import crontab

from app.config import get_settings


settings = get_settings()

celery_app = Celery("pac_xml_downloader", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "America/Sao_Paulo"
celery_app.conf.broker_connection_retry_on_startup = True

# Modo eager: task.delay() executa SÍNCRONA no mesmo processo (sem Redis/worker).
# Útil em dev local — ativar via env CELERY_TASK_ALWAYS_EAGER=true no .env.
# EM PRODUÇÃO, manter False (Celery worker separado).
if settings.celery_task_always_eager:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True  # erros viram exceptions sincronas
celery_app.conf.beat_schedule = {
    "download-diario-07h": {
        "task": "app.workers.tasks.executar_download_diario",
        "schedule": crontab(hour=7, minute=0),
    },
    "sync-caixa-postal-diario-08h": {
        "task": "app.workers.tasks.sync_caixa_postal_diario",
        "schedule": crontab(hour=8, minute=0),
    },
    "renovar-cnds-segunda-06h": {
        "task": "app.workers.tasks.renovar_cnds_vencendo",
        "schedule": crontab(day_of_week=1, hour=6, minute=0),  # segunda-feira 6h
    },
    # Robô SEFAZ-GO: dia 5 do mês às 03h, baixa o mês anterior inteiro (30 dias)
    "robo-sefaz-mensal-dia5-03h": {
        "task": "app.workers.tasks.executar_robo_sefaz_mensal",
        "schedule": crontab(day_of_month=5, hour=3, minute=0),
    },
    # Guias DAS Simples Nacional: sync diário às 09h pra capturar pagamentos
    # do dia anterior e detectar novas guias atrasadas (vencimento dia 20).
    "sync-guias-das-diario-09h": {
        "task": "app.workers.tasks.sync_guias_das_diario",
        "schedule": crontab(hour=9, minute=0),
    },
}
