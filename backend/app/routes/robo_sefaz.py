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


@router.get("/debug-screenshot")
def debug_screenshot(arquivo: str = Query(..., description="Nome do arquivo .png em /agent/sefaz-go/logs/debug/")):
    """Serve um screenshot de debug salvo pelo agente SEFAZ-GO.

    O agente salva PNGs em /agent/sefaz-go/logs/debug/ quando algo da errado
    (ex: sem_docs_<cnpj>_<ts>.png quando o botao 'Baixar todos' nao aparece).
    Esse endpoint serve a imagem pro usuario VER o que o SEFAZ-GO mostrou,
    sem precisar SSH no container.

    Protecao contra path traversal: so aceita nome de arquivo (sem barras) e
    serve estritamente de dentro do diretorio debug.
    """
    from pathlib import Path
    from fastapi.responses import FileResponse

    # Path traversal: rejeita qualquer coisa com / ou ..
    nome = Path(arquivo).name  # descarta qualquer diretorio embutido
    if nome != arquivo or ".." in arquivo:
        raise HTTPException(status_code=400, detail="Nome de arquivo invalido.")
    if not nome.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="So .png e servido aqui.")

    # Tenta os caminhos possiveis do diretorio debug do agente
    candidatos = [
        Path("/agent/sefaz-go/logs/debug") / nome,
        Path("/app/../agent/sefaz-go/logs/debug") / nome,
    ]
    for p in candidatos:
        if p.exists():
            return FileResponse(path=str(p), media_type="image/png", filename=nome)

    # Lista o que tem no dir pra ajudar a debugar
    debug_dir = Path("/agent/sefaz-go/logs/debug")
    existentes = []
    if debug_dir.exists():
        existentes = sorted([f.name for f in debug_dir.glob("*.png")])[-20:]
    raise HTTPException(
        status_code=404,
        detail={
            "erro": f"Screenshot '{nome}' nao encontrado.",
            "screenshots_disponiveis": existentes,
            "dir_existe": debug_dir.exists(),
        },
    )


@router.get("/diagnostico-redis")
def diagnostico_redis() -> dict:
    """Testa conectividade Redis + estado do Celery de dentro do backend.

    Diagnostica o erro "Celery worker ou Redis nao estao rodando" sem precisar
    de SSH/logs. Retorna:
    - redis_url_mascarada (host:port, sem credenciais)
    - eager_mode (se CELERY_TASK_ALWAYS_EAGER — nesse modo nao precisa Redis)
    - redis_ping_ok + tempo + erro
    - celery_broker_ok (tenta abrir conexao com o broker)
    """
    import time
    from app.config import get_settings as _gs
    _s = _gs()

    resultado: dict = {
        "eager_mode": _s.celery_task_always_eager,
    }

    # Mascara a URL (remove senha se houver)
    url = _s.redis_url or ""
    try:
        # redis://[:senha@]host:port/db
        if "@" in url:
            esquema, resto = url.split("://", 1)
            _cred, host_part = resto.split("@", 1)
            resultado["redis_url_mascarada"] = f"{esquema}://***@{host_part}"
        else:
            resultado["redis_url_mascarada"] = url
    except Exception:  # noqa: BLE001
        resultado["redis_url_mascarada"] = "<nao parseavel>"

    # Se eager, nem precisa de Redis — robô roda em thread no backend
    if _s.celery_task_always_eager:
        resultado["aviso"] = (
            "CELERY_TASK_ALWAYS_EAGER=true — robô roda em thread no backend, "
            "NAO precisa de Redis/worker. Nesse modo o disparo nunca da erro de Redis."
        )
        return resultado

    # Ping no Redis direto
    t0 = time.monotonic()
    try:
        import redis as _redis
        client = _redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
        pong = client.ping()
        resultado["redis_ping_ok"] = bool(pong)
        resultado["redis_ping_tempo_s"] = round(time.monotonic() - t0, 3)
    except Exception as exc:  # noqa: BLE001
        resultado["redis_ping_ok"] = False
        resultado["redis_ping_tempo_s"] = round(time.monotonic() - t0, 3)
        resultado["redis_erro"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    # Tenta abrir conexao com o broker Celery (kombu)
    t0 = time.monotonic()
    try:
        from app.workers.celery_app import celery_app
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=1, timeout=5)
        conn.release()
        resultado["celery_broker_ok"] = True
        resultado["celery_broker_tempo_s"] = round(time.monotonic() - t0, 3)
    except Exception as exc:  # noqa: BLE001
        resultado["celery_broker_ok"] = False
        resultado["celery_broker_tempo_s"] = round(time.monotonic() - t0, 3)
        resultado["celery_broker_erro"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    return resultado


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


@router.post("/execucoes/{execucao_id}/reprocessar-erros", response_model=ExecucaoRoboSefazRead, status_code=202)
def reprocessar_erros(
    execucao_id: int,
    db: Session = Depends(get_db),
) -> ExecucaoRoboSefazRead:
    """Cria uma nova execução SÓ com as empresas que falharam na execução dada.

    Lê os erros do `detalhes`, monta uma execução manual restrita a esses ids,
    mesmo período, e dispara. Resolve o caso "rodou tudo, sobraram X erros de
    portal lento/Cloudflare — re-roda só esses sem refazer a carteira".
    """
    from app.config import get_settings
    from app.workers.tasks import executar_robo_sefaz_manual

    servico = RoboSefazService(db)
    origem = servico.obter(execucao_id)
    if not origem:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    ids = servico.empresas_com_erro(origem)
    if not ids:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma empresa com erro nessa execução pra reprocessar.",
        )

    nova = servico.criar_execucao(
        disparo="manual",
        periodo_inicio=origem.periodo_inicio,
        periodo_fim=origem.periodo_fim,
        empresa_id=None,
        uf=origem.uf,
    )
    nova_id = nova.id

    if get_settings().celery_task_always_eager:
        import threading
        threading.Thread(
            target=executar_robo_sefaz_manual,
            args=(nova_id, ids),
            daemon=True,
        ).start()
        return ExecucaoRoboSefazRead.model_validate(nova)

    try:
        executar_robo_sefaz_manual.delay(nova_id, ids)
    except Exception as exc:  # noqa: BLE001
        try:
            db.refresh(nova)
            nova.status = "erro"
            nova.finalizado_em = nova.iniciado_em
            nova.motivo_erro = f"Falha ao enfileirar reprocesso: {exc!r}"[:1000]
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Celery worker/Redis fora do ar — não foi possível reprocessar.",
        )
    return ExecucaoRoboSefazRead.model_validate(nova)


@router.post("/execucoes/{execucao_id}/cancelar", response_model=ExecucaoRoboSefazRead)
def cancelar_execucao(
    execucao_id: int,
    db: Session = Depends(get_db),
) -> ExecucaoRoboSefazRead:
    """Cancela uma execução presa em pendente/rodando (marca como erro).

    Útil quando uma execução fica "zumbi" — ex.: o backend reiniciou (deploy)
    no meio e a thread daemon do robô morreu, deixando a linha eternamente em
    'Rodando'. Idempotente: se já terminou, devolve a linha sem alterar.
    """
    servico = RoboSefazService(db)
    try:
        execucao = servico.cancelar(execucao_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ExecucaoRoboSefazRead.model_validate(execucao)
