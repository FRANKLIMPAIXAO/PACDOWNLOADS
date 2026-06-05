"""Serviço pra invocar o agente SEFAZ-GO e registrar execuções no PAC.

Fluxo:
1. `criar_execucao(disparo, periodo, empresa_id)` grava linha `pendente` no DB
2. `executar(execucao_id, ...)` spawn subprocess do agente em
   `agent/sefaz-go/pac_sefaz_agent.py`, captura stdout, espera terminar, lê
   resumo JSON gerado e atualiza a linha com métricas agregadas.
3. Erros de execução (exit != 0 sem resumo) viram `status=erro` com `motivo_erro`.

Por que subprocess (e não import direto):
- O agente usa asyncio + Playwright, o que conflita com o event loop do Celery
- Isola crashes do agente do worker do PAC
- Permite reutilizar o entrypoint CLI já validado (`--empresa`, `--periodo`, `--headless`)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.execucao_robo_sefaz import ExecucaoRoboSefaz

logger = logging.getLogger(__name__)


# Caminhos resolvidos a partir do root do projeto.
# Em produção (VPS Linux) o agente fica em /opt/pac-xml/agent/sefaz-go.
AGENT_DIR_ENV = os.getenv("SEFAZ_AGENT_DIR", "")
DEFAULT_AGENT_DIR = Path(__file__).resolve().parents[3] / "agent" / "sefaz-go"
AGENT_DIR = Path(AGENT_DIR_ENV) if AGENT_DIR_ENV else DEFAULT_AGENT_DIR
AGENT_SCRIPT = AGENT_DIR / "pac_sefaz_agent.py"
AGENT_LOGS = AGENT_DIR / "logs"

# Quanto tempo esperar o agente terminar antes de matar (segurança).
# 120 empresas × 3 min cada = 360 min; arredondamos pra 8h pra folga.
AGENT_TIMEOUT_S = int(os.getenv("SEFAZ_AGENT_TIMEOUT_S", str(8 * 3600)))


def janela_mes_anterior(referencia: date | None = None) -> tuple[date, date]:
    """Devolve (primeiro_dia_mes_anterior, ultimo_dia_mes_anterior).

    Atende ao requisito: "tem q ser sempre 30 dias, do mês anterior, pois
    é quando baixar as notas". Calculado independente do dia do disparo —
    se rodar dia 5/maio, baixa 01/abril a 30/abril.
    """
    hoje = referencia or date.today()
    primeiro_do_mes_atual = hoje.replace(day=1)
    # Truque pra pegar último dia do mês anterior: subtrair 1 dia do dia 1 do mês corrente
    from datetime import timedelta
    ultimo_mes_anterior = primeiro_do_mes_atual - timedelta(days=1)
    primeiro_mes_anterior = ultimo_mes_anterior.replace(day=1)
    return primeiro_mes_anterior, ultimo_mes_anterior


class RoboSefazService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Criação de execução (pendente)
    # ------------------------------------------------------------------
    def criar_execucao(
        self,
        *,
        disparo: str,
        periodo_inicio: date | None = None,
        periodo_fim: date | None = None,
        empresa_id: int | None = None,
        uf: str = "GO",
    ) -> ExecucaoRoboSefaz:
        """Cria registro pendente. Default de período = mês anterior."""
        if disparo not in {"cron", "manual"}:
            raise ValueError(f"disparo inválido: {disparo!r}")
        if periodo_inicio is None or periodo_fim is None:
            ini, fim = janela_mes_anterior()
            periodo_inicio = periodo_inicio or ini
            periodo_fim = periodo_fim or fim

        execucao = ExecucaoRoboSefaz(
            disparo=disparo,
            uf=uf,
            status="pendente",
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            empresa_id=empresa_id,
        )
        self.db.add(execucao)
        self.db.commit()
        self.db.refresh(execucao)
        return execucao

    # ------------------------------------------------------------------
    # Execução síncrona (Celery task chama isso)
    # ------------------------------------------------------------------
    def executar(self, execucao_id: int) -> ExecucaoRoboSefaz:
        """Roda o subprocess do agente e atualiza a linha conforme resultado.

        Bloqueia até o agente terminar (timeout configurável). Não deve ser
        chamado direto pelo request HTTP — usar via Celery task assíncrona.
        """
        execucao = self.db.get(ExecucaoRoboSefaz, execucao_id)
        if execucao is None:
            raise ValueError(f"Execução {execucao_id} não encontrada")
        if execucao.status not in {"pendente"}:
            raise ValueError(
                f"Execução {execucao_id} já está em status {execucao.status!r}",
            )

        execucao.status = "rodando"
        self.db.commit()

        if not AGENT_SCRIPT.exists():
            return self._falhar(
                execucao, f"Script do agente não encontrado: {AGENT_SCRIPT}",
            )

        # Args do agent
        periodo_arg = execucao.periodo_inicio.strftime("%Y-%m")
        cmd: list[str] = [
            "python", str(AGENT_SCRIPT),
            "--periodo", periodo_arg,
        ]
        if execucao.empresa_id:
            cmd.extend(["--empresa", str(execucao.empresa_id)])

        # Em produção sempre headless; deixar variavel HEADLESS=true no .env do agent
        env = os.environ.copy()
        env.setdefault("HEADLESS", "true")

        # Bridge entre nomenclatura backend e agent:
        # - Backend (config.py) usa CAPTCHA_API_KEY
        # - Agent (pac_sefaz_agent.py) usa TWOCAPTCHA_API_KEY
        # Se CAPTCHA_API_KEY estiver setado mas TWOCAPTCHA_API_KEY não,
        # copia o valor pro agent enxergar. Idem PAC_API_URL/EMAIL/PASSWORD
        # que o agent usa pra falar com o próprio backend.
        if env.get("CAPTCHA_API_KEY") and not env.get("TWOCAPTCHA_API_KEY"):
            env["TWOCAPTCHA_API_KEY"] = env["CAPTCHA_API_KEY"]
        env.setdefault("PAC_API_URL", "http://127.0.0.1:8000")
        env.setdefault("PAC_EMAIL", "admin@pacxml.com.br")
        env.setdefault("PAC_PASSWORD", env.get("FIRST_SUPERUSER_PASSWORD", "admin123"))

        antes = datetime.now()
        logger.info(
            "Iniciando agente SEFAZ-GO: cmd=%s timeout=%ss execucao_id=%s",
            cmd, AGENT_TIMEOUT_S, execucao_id,
        )
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(AGENT_DIR),
                env=env,
                capture_output=True,
                text=True,
                timeout=AGENT_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._falhar(
                execucao,
                f"Agente excedeu timeout ({AGENT_TIMEOUT_S}s)",
            )
        except Exception as exc:  # noqa: BLE001
            return self._falhar(execucao, f"Erro ao executar agente: {exc!r}")

        # Lê o último resumo gerado (gerado SEMPRE no fim do main_async)
        resumo_path = self._ultimo_resumo(after=antes)
        if resumo_path is None:
            # Sem resumo → falha. Pega stderr (final 5KB, vasodá pro traceback Python)
            # E também stdout (1KB do final) — Playwright às vezes loga erro real lá.
            stderr_tail = (proc.stderr or "")[-5000:]
            stdout_tail = (proc.stdout or "")[-1000:]
            # Procura linhas "Error:" no stderr inteiro (a mensagem real do
            # Playwright fica entre prints normais e o traceback Python).
            err_lines = []
            for line in (proc.stderr or "").splitlines():
                low = line.lower()
                if any(k in low for k in [
                    "error:", "browser was not", "executable doesn", "missing",
                    "cannot find", "permission denied", "no such",
                ]):
                    err_lines.append(line.strip()[:300])
            chave_errors = " | ".join(err_lines[-5:]) if err_lines else "(nenhuma)"

            return self._falhar(
                execucao,
                (
                    f"Agente terminou exit={proc.returncode} sem gerar resumo. "
                    f"erros_detectados=[{chave_errors}] "
                    f"stdout_tail={stdout_tail!r} "
                    f"stderr_tail={stderr_tail!r}"
                ),
            )

        try:
            detalhes = json.loads(resumo_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return self._falhar(
                execucao,
                f"Falha ao parsear resumo {resumo_path}: {exc!r}",
            )

        # Agrega métricas
        com_zip = sum(1 for r in detalhes if r.get("sucesso") and not r.get("sem_resultados"))
        sem_notas = sum(1 for r in detalhes if r.get("sem_resultados"))
        erros = sum(1 for r in detalhes if not r.get("sucesso"))
        persistidos = sum(
            (r.get("upload_pac") or {}).get("persistidos", 0) for r in detalhes
        )
        duplicados = sum(
            (r.get("upload_pac") or {}).get("duplicados", 0) for r in detalhes
        )

        execucao.status = "concluido" if proc.returncode == 0 else "erro"
        execucao.finalizado_em = self._now_compatible_with(execucao.iniciado_em)
        execucao.total_empresas = len(detalhes)
        execucao.com_zip = com_zip
        execucao.sem_notas = sem_notas
        execucao.erros = erros
        execucao.persistidos = persistidos
        execucao.duplicados = duplicados
        execucao.detalhes = detalhes
        if proc.returncode != 0 and erros:
            primeiro_erro = next(
                (r for r in detalhes if not r.get("sucesso")), None,
            )
            if primeiro_erro:
                execucao.motivo_erro = (
                    f"Pelo menos 1 empresa falhou. Ex: "
                    f"{primeiro_erro.get('razao_social')} → "
                    f"{primeiro_erro.get('motivo')}"
                )[:1000]
        self.db.commit()
        self.db.refresh(execucao)
        logger.info(
            "Execução %s finalizada: status=%s com_zip=%d sem_notas=%d erros=%d",
            execucao_id, execucao.status, com_zip, sem_notas, erros,
        )
        return execucao

    # ------------------------------------------------------------------
    # Listagem / detalhes
    # ------------------------------------------------------------------
    def listar(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[ExecucaoRoboSefaz]:
        stmt = select(ExecucaoRoboSefaz).order_by(desc(ExecucaoRoboSefaz.iniciado_em))
        if status:
            stmt = stmt.where(ExecucaoRoboSefaz.status == status)
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def obter(self, execucao_id: int) -> ExecucaoRoboSefaz | None:
        return self.db.get(ExecucaoRoboSefaz, execucao_id)

    # ------------------------------------------------------------------
    # Cancelamento manual / recuperação de zumbis
    # ------------------------------------------------------------------
    def cancelar(self, execucao_id: int) -> ExecucaoRoboSefaz:
        """Marca uma execução presa em pendente/rodando como erro.

        Usado pelo botão "Cancelar" quando uma execução fica zumbi (ex.: o
        backend reiniciou no meio e a thread daemon morreu, deixando a linha
        eternamente em 'rodando'). Idempotente: se já terminou, é no-op.
        """
        execucao = self.db.get(ExecucaoRoboSefaz, execucao_id)
        if execucao is None:
            raise ValueError(f"Execução {execucao_id} não encontrada")
        if execucao.status in {"concluido", "erro"}:
            return execucao  # já finalizada — nada a fazer
        execucao.status = "erro"
        execucao.finalizado_em = self._now_compatible_with(execucao.iniciado_em)
        execucao.motivo_erro = (
            "Cancelada manualmente — estava presa em "
            f"'{execucao.status}'. Provável reinício do backend (deploy) "
            "matou a thread do robô no meio da execução."
        )[:1000]
        self.db.commit()
        self.db.refresh(execucao)
        return execucao

    def recuperar_execucoes_zumbis(self) -> int:
        """Finaliza execuções presas em pendente/rodando ao subir o backend.

        Em modo eager (CELERY_TASK_ALWAYS_EAGER=true) o robô roda numa thread
        daemon DENTRO do backend. Quando o processo reinicia (deploy/restart),
        a thread morre, mas a linha fica presa em 'rodando' pra sempre — não há
        worker externo pra finalizá-la. Na subida do app, marcamos essas órfãs
        como erro pra não ficarem "Rodando" eternamente.

        Só roda em modo eager. Em produção com Celery worker separado, um
        restart do backend NÃO mata o worker, então uma execução 'rodando' pode
        legitimamente continuar — nesse caso não mexemos.
        """
        from app.config import get_settings

        if not get_settings().celery_task_always_eager:
            return 0

        presas = list(self.db.scalars(
            select(ExecucaoRoboSefaz).where(
                ExecucaoRoboSefaz.status.in_(["pendente", "rodando"]),
            )
        ).all())
        for ex in presas:
            ex.status = "erro"
            ex.finalizado_em = self._now_compatible_with(ex.iniciado_em)
            ex.motivo_erro = (
                "Interrompida por reinício do backend (deploy/restart). A thread "
                "do robô em modo eager morre junto com o processo. Dispare de novo."
            )[:1000]
        if presas:
            self.db.commit()
            logger.warning(
                "recuperar_execucoes_zumbis: %d execução(ões) presas finalizadas como erro: %s",
                len(presas), [e.id for e in presas],
            )
        return len(presas)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------
    @staticmethod
    def _now_compatible_with(ref: datetime | None) -> datetime:
        """Devolve `datetime.now()` no mesmo tipo (naive vs aware) que `ref`.

        Necessário porque `iniciado_em` vem do `server_default=func.now()` do DB
        (aware/UTC no Postgres), mas `datetime.now()` puro do Python é naive
        (hora local). Subtrair os dois daria erro ou duração negativa.
        """
        if ref is not None and ref.tzinfo is not None:
            return datetime.now(timezone.utc)
        return datetime.now()

    def _falhar(self, execucao: ExecucaoRoboSefaz, motivo: str) -> ExecucaoRoboSefaz:
        logger.error("Execução %s falhou: %s", execucao.id, motivo)
        execucao.status = "erro"
        execucao.finalizado_em = self._now_compatible_with(execucao.iniciado_em)
        execucao.motivo_erro = motivo[:1000]
        self.db.commit()
        self.db.refresh(execucao)
        return execucao

    def _ultimo_resumo(self, *, after: datetime) -> Path | None:
        """Acha o resumo_*.json gerado pelo agente depois de `after`."""
        if not AGENT_LOGS.exists():
            return None
        resumos = sorted(
            AGENT_LOGS.glob("resumo_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for r in resumos:
            try:
                if datetime.fromtimestamp(r.stat().st_mtime) >= after:
                    return r
            except OSError:
                continue
        return None
