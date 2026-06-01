"""Rotas REST do robô SEFAZ-GO.

- `GET  /robo-sefaz/execucoes`         lista paginada de execuções
- `GET  /robo-sefaz/execucoes/{id}`    detalhes (com info empresa-a-empresa)
- `POST /robo-sefaz/disparar`          dispara robô manualmente (cria
                                       linha + enfileira task assíncrona)
- `GET  /robo-sefaz/agendamento`       info estática do cron mensal
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.robo_sefaz_schema import (
    DispararRoboSefazPayload,
    ExecucaoRoboSefazDetailRead,
    ExecucaoRoboSefazRead,
)
from app.services.auth_service import get_current_user
from app.services.robo_sefaz_service import RoboSefazService

router = APIRouter(
    prefix="/robo-sefaz",
    tags=["robo-sefaz"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/agendamento")
def info_agendamento() -> dict:
    """Info estática do cron mensal (lê do celery_app.conf.beat_schedule).

    Hoje hardcoded: dia 5 às 03h, baixa mês anterior. Quando virar
    configurável via DB, este endpoint vai expor a config dinâmica.
    """
    return {
        "ativo": True,
        "cron_expression": "0 3 5 * *",
        "descricao": "Robô SEFAZ-GO mensal: dia 5 às 03h, baixa mês anterior",
        "uf": "GO",
        "janela": "mes_anterior",
    }


@router.get("/execucoes", response_model=list[ExecucaoRoboSefazRead])
def listar_execucoes(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ExecucaoRoboSefazRead]:
    servico = RoboSefazService(db)
    execucoes = servico.listar(limit=limit, offset=offset, status=status)
    return [ExecucaoRoboSefazRead.model_validate(e) for e in execucoes]


@router.get("/execucoes/{execucao_id}", response_model=ExecucaoRoboSefazDetailRead)
def obter_execucao(
    execucao_id: int, db: Session = Depends(get_db),
) -> ExecucaoRoboSefazDetailRead:
    servico = RoboSefazService(db)
    execucao = servico.obter(execucao_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return ExecucaoRoboSefazDetailRead.model_validate(execucao)


@router.post("/disparar", response_model=ExecucaoRoboSefazRead, status_code=202)
def disparar_robo(
    payload: DispararRoboSefazPayload | None = None,
    db: Session = Depends(get_db),
) -> ExecucaoRoboSefazRead:
    """Dispara o robô SEFAZ-GO agora (assíncrono via Celery).

    Cria a linha `ExecucaoRoboSefaz` com status `pendente`, enfileira a task
    `executar_robo_sefaz_manual` no Celery e devolve a linha já criada
    (status 202 + corpo) — o frontend deve dar polling em
    `GET /robo-sefaz/execucoes/{id}` pra ver o progresso.
    """
    # Importa task aqui pra evitar ciclo de import (worker → service → route)
    from app.config import get_settings
    from app.workers.tasks import executar_robo_sefaz_manual

    payload = payload or DispararRoboSefazPayload()
    servico = RoboSefazService(db)
    execucao = servico.criar_execucao(
        disparo="manual",
        periodo_inicio=payload.periodo_inicio,
        periodo_fim=payload.periodo_fim,
        empresa_id=payload.empresa_id,
        uf="GO",
    )
    execucao_id = execucao.id

    # Em DEV com CELERY_TASK_ALWAYS_EAGER=true, .delay() roda síncrono no mesmo
    # thread → bloquearia a request por ~3min/empresa. Pra evitar, em eager mode
    # dispara em thread separada (fire-and-forget) e devolve 202 imediatamente.
    # Em produção (eager=False), Celery worker separado faz isso naturalmente.
    if get_settings().celery_task_always_eager:
        import threading
        threading.Thread(
            target=executar_robo_sefaz_manual,  # chama a função direto, não .delay()
            args=(execucao_id,),
            daemon=True,
        ).start()
        return ExecucaoRoboSefazRead.model_validate(execucao)

    # Modo produção: enfileira no Redis pro worker pegar.
    # Captura erro de Redis/Celery fora do ar pra devolver 503 elegante
    # (sem isso, o ConnectionError vira 500 sem headers CORS no navegador).
    try:
        executar_robo_sefaz_manual.delay(execucao_id)
    except Exception as exc:  # noqa: BLE001  (kombu.OperationalError, redis.ConnectionError, etc)
        # Marca a execução como erro pra ficar registrado no histórico.
        # Usa o iniciado_em real (já gravado pelo DB) pra evitar mismatch de
        # timezone — finalizado_em precisa ser na mesma referência (UTC ou local)
        # senão duracao_segundos vira negativo.
        try:
            db.refresh(execucao)
            execucao.status = "erro"
            execucao.finalizado_em = execucao.iniciado_em  # 0s de duração (falha imediata)
            execucao.motivo_erro = (
                f"Falha ao enfileirar no Celery (worker/Redis fora do ar?): {exc!r}"
            )[:1000]
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise HTTPException(
            status_code=503,
            detail=(
                "Não foi possível enfileirar a execução: Celery worker ou Redis "
                "não estão rodando. Suba os dois antes de disparar o robô. "
                "(O registro da execução foi salvo com status 'erro' pra histórico.)"
            ),
        )
    return ExecucaoRoboSefazRead.model_validate(execucao)
