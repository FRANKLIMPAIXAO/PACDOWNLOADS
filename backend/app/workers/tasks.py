from sqlalchemy import select

from app.database import SessionLocal
from app.models.empresa import Empresa
from app.models.procuracao import Procuracao
from app.services.cnd_robo_service import CndRoboService
from app.services.integra_contador_service import IntegraContadorService
from app.services.robo_sefaz_service import RoboSefazService, janela_mes_anterior
from app.services.robo_xml import RoboXMLService
from app.utils.dates import previous_day_bounds
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.executar_download_diario")
def executar_download_diario() -> dict:
    """Baixa NF-es recebidas (DF-e) de todas empresas ativas com token Focus."""
    db = SessionLocal()
    try:
        data_inicio, data_fim = previous_day_bounds()
        service = RoboXMLService(db)
        return service.baixar_distribuicao_multiempresas(data_inicio, data_fim)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.sync_caixa_postal_diario")
def sync_caixa_postal_diario() -> dict:
    """Sync Caixa Postal eCAC de todas empresas com procuracao ATIVA.

    Roda 1x por dia (beat: 8h). Para cada empresa, faz uma chamada
    MSGCONTRIBUINTE61 e persiste mensagens novas. Falhas individuais nao
    interrompem as demais.
    """
    db = SessionLocal()
    resultado: dict[int, dict] = {}
    try:
        service = IntegraContadorService(db)
        # Empresas ativas com pelo menos uma procuracao ATIVA registrada
        empresas = db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.id)
        ).all()
        for empresa in empresas:
            ultima_proc = db.scalar(
                select(Procuracao)
                .where(Procuracao.empresa_id == empresa.id)
                .order_by(Procuracao.sincronizada_em.desc(), Procuracao.id.desc())
            )
            if not ultima_proc or ultima_proc.situacao.upper() != "ATIVA":
                resultado[empresa.id] = {"skip": "sem procuracao ativa"}
                continue
            try:
                r = service.sync_caixa_postal(empresa.id)
                resultado[empresa.id] = {
                    "novas": r.novas,
                    "atualizadas": r.atualizadas,
                    "erros": r.erros,
                }
            except Exception as exc:  # noqa: BLE001
                resultado[empresa.id] = {"erro": str(exc)[:200]}
        return resultado
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.executar_robo_sefaz_mensal")
def executar_robo_sefaz_mensal(empresa_id: int | None = None) -> dict:
    """Cron mensal (dia 5, 03h): roda agente SEFAZ-GO no mês anterior.

    Cria registro `ExecucaoRoboSefaz` com `disparo='cron'`, spawn subprocess
    do agente Playwright que baixa XMLs de todas as empresas com cert A1,
    aguarda terminar, agrega métricas no DB.

    Quando chamado via `disparar_robo_sefaz_agora` (rota /robo-sefaz/disparar),
    usa `disparo='manual'` via task separada.
    """
    db = SessionLocal()
    try:
        servico = RoboSefazService(db)
        ini, fim = janela_mes_anterior()
        execucao = servico.criar_execucao(
            disparo="cron",
            periodo_inicio=ini,
            periodo_fim=fim,
            empresa_id=empresa_id,
            uf="GO",
        )
        resultado = servico.executar(execucao.id)
        return {
            "execucao_id": resultado.id,
            "status": resultado.status,
            "com_zip": resultado.com_zip,
            "sem_notas": resultado.sem_notas,
            "erros": resultado.erros,
            "persistidos": resultado.persistidos,
            "duplicados": resultado.duplicados,
        }
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.executar_robo_sefaz_manual")
def executar_robo_sefaz_manual(
    execucao_id: int, empresa_ids: list[int] | None = None,
) -> dict:
    """Continua execução manual já criada via rota POST /robo-sefaz/disparar.

    A linha já foi inserida com `disparo='manual'` antes do enqueue — aqui
    só roda o subprocess e atualiza.

    `empresa_ids` (opcional) restringe a um subconjunto — usado pelo
    "Reprocessar os que deram erro".
    """
    db = SessionLocal()
    try:
        servico = RoboSefazService(db)
        resultado = servico.executar(execucao_id, empresa_ids=empresa_ids)
        return {
            "execucao_id": resultado.id,
            "status": resultado.status,
            "com_zip": resultado.com_zip,
            "sem_notas": resultado.sem_notas,
            "erros": resultado.erros,
            "persistidos": resultado.persistidos,
            "duplicados": resultado.duplicados,
        }
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.sync_guias_das_diario")
def sync_guias_das_diario(ano: int | None = None) -> dict:
    """Sincroniza guias DAS de todas as empresas Simples Nacional.

    Roda 1x por dia (beat: 09h). Para cada empresa Simples, chama
    PGDASD CONSDECREC13 (declarações do ano) + PAGAMENTOS71 (pagamentos),
    persiste em `guias_das`, marca vencidas como `atrasada`.

    `ano` default = ano corrente. Pode passar explicitamente pra sincronizar
    anos passados.
    """
    from datetime import datetime
    from app.services.guia_das_service import GuiaDASService

    db = SessionLocal()
    try:
        ano = ano or datetime.now().year
        servico = GuiaDASService(db)
        resultados = servico.sync_todas_empresas_simples(ano)
        # Resumo agregado pra log/monitoramento
        total_novas = sum(r.novas for r in resultados.values())
        total_atualizadas = sum(r.atualizadas for r in resultados.values())
        total_pagas = sum(r.pagas_detectadas for r in resultados.values())
        total_erros = sum(r.erros for r in resultados.values())
        return {
            "empresas_processadas": len(resultados),
            "novas": total_novas,
            "atualizadas": total_atualizadas,
            "pagas_detectadas": total_pagas,
            "erros": total_erros,
        }
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.renovar_cnds_vencendo")
def renovar_cnds_vencendo(janela_dias: int = 7) -> dict:
    """Robo SEFAZ semanal: renova CNDs vencendo em <= janela_dias OU vencidas.

    Roda 1x por semana (beat: segunda 6h). Cada CND eh emitida no portal
    correspondente (Federal/Trabalhista/FGTS), salva PDF em storage/cnds/...,
    cria nova linha em `certidoes` com data_validade atualizada.

    Falhas em uma empresa nao interrompem as demais.
    """
    db = SessionLocal()
    try:
        servico = CndRoboService(db)
        resultado = servico.renovar_vencendo(janela_dias=janela_dias)
        return {
            "sucesso": resultado.sucesso,
            "falhas": resultado.falhas,
            "pulados": resultado.pulados,
            "detalhes": resultado.detalhes,
        }
    finally:
        db.close()
