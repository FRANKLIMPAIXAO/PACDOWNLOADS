"use client";

import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  AgendamentoInfo,
  DetalheEmpresa,
  ExecucaoRoboSefaz,
  ExecucaoRoboSefazDetail,
  cancelarExecucao,
  dispararRobo,
  formatarDuracao,
  formatarPeriodo,
  listarExecucoes,
  obterAgendamento,
  obterExecucao,
  statusLabel,
  statusPillClass,
} from "../../lib/robo-sefaz";

// Formata "Xs atrás" / "Xm atrás" pra mostrar quanto tempo passou
function segundosAtras(d: Date): string {
  const diff = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (diff < 5) return "agora mesmo";
  if (diff < 60) return `${diff}s atrás`;
  const m = Math.floor(diff / 60);
  return `${m}min ${diff % 60}s atrás`;
}

// Default: mês anterior (mesma janela do agente sem args)
function defaultPeriodo(): { inicio: string; fim: string } {
  const hoje = new Date();
  const primeiroDoMes = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  const ultimoMesAnterior = new Date(primeiroDoMes.getTime() - 86400_000);
  const primeiroMesAnterior = new Date(
    ultimoMesAnterior.getFullYear(),
    ultimoMesAnterior.getMonth(),
    1,
  );
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { inicio: iso(primeiroMesAnterior), fim: iso(ultimoMesAnterior) };
}

// Polling adaptativo: mais rápido nos primeiros 30s após disparo
// (execuções costumam levar 30-90s), volta pra 5s depois.
const POLL_INTERVAL_FAST_MS = 2_000;
const POLL_INTERVAL_SLOW_MS = 5_000;
const FAST_WINDOW_MS = 30_000;

export default function RoboSefazPage() {
  return (
    <ProtectedRoute>
      <RoboSefazContent />
    </ProtectedRoute>
  );
}

function RoboSefazContent() {
  const [agendamento, setAgendamento] = useState<AgendamentoInfo | null>(null);
  const [execucoes, setExecucoes] = useState<ExecucaoRoboSefaz[] | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [detalhe, setDetalhe] = useState<ExecucaoRoboSefazDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [ultimaAtualizacao, setUltimaAtualizacao] = useState<Date | null>(null);
  const [_tickCount, setTickCount] = useState(0); // força re-render do "Xs atrás"

  // Filtros do "Rodar agora"
  const periodoDefault = useMemo(() => defaultPeriodo(), []);
  const [empresaIdSel, setEmpresaIdSel] = useState<string>(""); // "" = todas
  const [periodoInicio, setPeriodoInicio] = useState<string>(periodoDefault.inicio);
  const [periodoFim, setPeriodoFim] = useState<string>(periodoDefault.fim);

  // Refs pro polling — não causa re-render quando muda
  const aliveRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fastUntilRef = useRef<number>(0); // timestamp ms até quando usar polling fast

  // Empresas elegíveis: ativas + com cert A1 (sem cert o agente falha)
  const empresasElegiveis = useMemo(
    () => (empresas ?? []).filter((e) => e.ativo && e.tem_certificado_a1),
    [empresas],
  );

  // Carrega lista de execuções + agenda próxima iteração se necessário.
  // Esta função vive no escopo do componente (não dentro do useEffect) pra
  // poder ser chamada de qualquer handler (Disparar, Atualizar manual, etc).
  const carregar = useCallback(async () => {
    try {
      const [ag, exs, emps] = await Promise.all([
        obterAgendamento(),
        listarExecucoes({ limit: 50 }),
        listarEmpresas(),
      ]);
      if (!aliveRef.current) return;
      setAgendamento(ag);
      setExecucoes(exs);
      setEmpresas(emps);
      setUltimaAtualizacao(new Date());

      const temAtiva = exs.some(
        (e) => e.status === "pendente" || e.status === "rodando",
      );
      if (temAtiva && aliveRef.current) {
        // Polling fast nos primeiros 30s depois do último Disparar (caso
        // recém-iniciado), depois cai pra slow.
        const agora = Date.now();
        const intervalo =
          agora < fastUntilRef.current
            ? POLL_INTERVAL_FAST_MS
            : POLL_INTERVAL_SLOW_MS;
        timerRef.current = setTimeout(carregar, intervalo);
      } else {
        // Sem ativas — para de polar mas mantém "última atualização" no UI.
        timerRef.current = null;
      }
    } catch (e) {
      if (aliveRef.current) {
        setErro(e instanceof ApiError ? e.message : "Falha ao carregar dados");
      }
    }
  }, []);

  // Inicializa polling no mount + cleanup no unmount
  useEffect(() => {
    aliveRef.current = true;
    carregar();
    return () => {
      aliveRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [carregar]);

  // Tick a cada 1s pra atualizar "última atualização: Xs atrás" no UI
  useEffect(() => {
    const id = setInterval(() => setTickCount((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  async function handleDisparar() {
    setBusy("disparar");
    setErro(null);
    if (periodoInicio > periodoFim) {
      setErro("Período inválido: início é depois do fim.");
      setBusy(null);
      return;
    }
    try {
      const empresa_id = empresaIdSel ? Number(empresaIdSel) : null;
      const nova = await dispararRobo({
        empresa_id,
        periodo_inicio: periodoInicio,
        periodo_fim: periodoFim,
      });
      const empresaNome = empresa_id
        ? empresasElegiveis.find((e) => e.id === empresa_id)?.razao_social ?? `empresa #${empresa_id}`
        : `todas as ${empresasElegiveis.length} empresas`;
      setToast(
        `Robô disparado! Execução #${nova.id} criada (${empresaNome} · ${formatarPeriodo(nova.periodo_inicio, nova.periodo_fim)}).`,
      );
      // Marca janela de polling rápido (2s) pelos próximos 30s
      fastUntilRef.current = Date.now() + FAST_WINDOW_MS;
      // Cancela timer pendente e força carregar imediatamente — vai se
      // auto-reagendar enquanto a nova execução estiver rodando
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      await carregar();
    } catch (e) {
      setErro(
        e instanceof ApiError
          ? e.message
          : "Falha ao disparar robô — verifique se o Celery worker está rodando.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleAtualizar() {
    setBusy("atualizar");
    setErro(null);
    // Cancela polling pendente e força carregar agora
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    await carregar();
    setBusy(null);
  }

  async function handleVerDetalhes(id: number) {
    setBusy(`detalhe-${id}`);
    setErro(null);
    try {
      const det = await obterExecucao(id);
      setDetalhe(det);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar detalhes");
    } finally {
      setBusy(null);
    }
  }

  async function handleCancelar(id: number) {
    const ok = confirm(
      `Cancelar a execução #${id}?\n\n` +
      "Use isso quando ela ficou presa em 'Rodando' (ex.: o backend reiniciou " +
      "no meio e a thread do robô morreu). Marca como erro pra liberar o " +
      "histórico. Não interrompe um robô que esteja realmente baixando notas.",
    );
    if (!ok) return;
    setBusy(`cancelar-${id}`);
    setErro(null);
    try {
      await cancelarExecucao(id);
      setToast(`Execução #${id} cancelada (marcada como erro).`);
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao cancelar execução");
    } finally {
      setBusy(null);
    }
  }

  const headers = [
    "ID",
    "Disparo",
    "Período",
    "Status",
    "Empresas",
    "Com ZIP",
    "Sem notas",
    "Erros",
    "Persistidos",
    "Duração",
    "",
  ];

  const rows =
    execucoes?.map((e): ReactNode[] => [
      `#${e.id}`,
      e.disparo === "cron" ? "🕐 Cron" : "▶ Manual",
      formatarPeriodo(e.periodo_inicio, e.periodo_fim),
      <span key={`status-${e.id}`} className={statusPillClass(e.status)}>
        {statusLabel(e.status)}
      </span>,
      e.total_empresas,
      e.com_zip,
      e.sem_notas,
      e.erros > 0 ? <strong key={`err-${e.id}`}>{e.erros}</strong> : 0,
      e.persistidos,
      formatarDuracao(e.duracao_segundos),
      <span key={`acoes-${e.id}`} style={{ display: "inline-flex", gap: 6 }}>
        <button
          className="btn-ghost"
          onClick={() => handleVerDetalhes(e.id)}
          disabled={busy !== null}
        >
          Detalhes
        </button>
        {e.status === "rodando" || e.status === "pendente" ? (
          <button
            className="btn-ghost"
            style={{ color: "rgb(248,113,113)" }}
            onClick={() => handleCancelar(e.id)}
            disabled={busy !== null}
            title="Cancelar execução presa em Rodando"
          >
            {busy === `cancelar-${e.id}` ? "..." : "Cancelar"}
          </button>
        ) : null}
      </span>,
    ]) ?? [];

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Robô SEFAZ-GO</h1>
          <p>Baixa automaticamente os XMLs de NFes emitidas no portal SEFAZ-GO.</p>
        </div>
      </header>

      {/* Painel de disparo manual com filtro de empresa + período */}
      <section className="table-card">
        <header>
          <h2>Rodar agora</h2>
          <p className="muted">
            Escolhe uma empresa específica (ou deixa "Todas") + período. Default = mês anterior.
          </p>
        </header>
        <div
          style={{
            padding: 16,
            display: "grid",
            gridTemplateColumns: "2fr 1fr 1fr auto",
            gap: 12,
            alignItems: "end",
          }}
        >
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Empresa</span>
            <select
              value={empresaIdSel}
              onChange={(e) => setEmpresaIdSel(e.target.value)}
              disabled={busy !== null || empresas === null}
            >
              <option value="">
                Todas ({empresasElegiveis.length} com cert A1)
              </option>
              {empresasElegiveis.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} ({e.cnpj})
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Início</span>
            <input
              type="date"
              value={periodoInicio}
              onChange={(e) => setPeriodoInicio(e.target.value)}
              disabled={busy !== null}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Fim</span>
            <input
              type="date"
              value={periodoFim}
              onChange={(e) => setPeriodoFim(e.target.value)}
              disabled={busy !== null}
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            onClick={handleDisparar}
            disabled={busy !== null}
          >
            {busy === "disparar" ? "Disparando..." : "▶ Rodar"}
          </button>
        </div>
        {empresas !== null && empresasElegiveis.length === 0 ? (
          <p className="muted" style={{ padding: "0 16px 16px" }}>
            ⚠ Nenhuma empresa com certificado A1 cadastrado. O robô não pode rodar.
          </p>
        ) : null}
      </section>

      {toast ? (
        <div className="toast toast" onClick={() => setToast(null)}>
          {toast}
        </div>
      ) : null}
      {erro ? (
        <div className="toast toast-error" onClick={() => setErro(null)}>
          {erro}
        </div>
      ) : null}

      {/* Card do agendamento */}
      <section className="table-card">
        <header>
          <h2>Agendamento mensal</h2>
        </header>
        {agendamento ? (
          <dl className="kv-grid">
            <dt>Status</dt>
            <dd>
              <span
                className={
                  agendamento.ativo ? "pill pill-ok" : "pill pill-muted"
                }
              >
                {agendamento.ativo ? "Ativo" : "Inativo"}
              </span>
            </dd>
            <dt>Cron</dt>
            <dd>
              <code>{agendamento.cron_expression}</code>
            </dd>
            <dt>UF</dt>
            <dd>{agendamento.uf}</dd>
            <dt>Janela</dt>
            <dd>
              {agendamento.janela === "mes_anterior"
                ? "Mês anterior (30 dias)"
                : agendamento.janela}
            </dd>
            <dt>Descrição</dt>
            <dd>{agendamento.descricao}</dd>
          </dl>
        ) : (
          <p className="muted">Carregando agendamento…</p>
        )}
      </section>

      {/* Barra de status do polling + botão Atualizar manual.
          Aparece sempre que tem execuções carregadas (ou nem que vazio).
          Resolve o bug: lista nunca atualizava após Disparar porque o
          useEffect só agendava polling se já tinha rodando no mount. */}
      {execucoes !== null ? (
        <section
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 14px",
            background: "rgba(255,255,255,0.02)",
            borderRadius: 8,
            marginTop: 4,
            marginBottom: 4,
            fontSize: 13,
          }}
        >
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <strong>Histórico de execuções</strong>
            {execucoes.some((e) => e.status === "pendente" || e.status === "rodando") ? (
              <span className="pill pill-info">⟳ atualizando a cada 2s</span>
            ) : (
              <span className="muted">parado (sem execuções ativas)</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span className="muted">
              {ultimaAtualizacao
                ? `última atualização: ${segundosAtras(ultimaAtualizacao)}`
                : "—"}
            </span>
            <button
              type="button"
              className="btn-ghost"
              onClick={handleAtualizar}
              disabled={busy !== null}
              title="Forçar atualização agora"
            >
              {busy === "atualizar" ? "..." : "↻ Atualizar"}
            </button>
          </div>
        </section>
      ) : null}

      {/* Tabela de execuções */}
      {execucoes === null ? (
        <p className="muted">Carregando execuções…</p>
      ) : execucoes.length === 0 ? (
        <section className="table-card">
          <p className="muted" style={{ padding: 16 }}>
            Nenhuma execução ainda. Clique em <strong>Rodar</strong> pra
            disparar a primeira ou aguarde o cron mensal (dia 5 às 03h).
          </p>
        </section>
      ) : (
        <DataTable
          subtitle="Últimas 50 execuções, ordenadas por mais recentes."
          headers={headers}
          rows={rows}
        />
      )}

      {/* Drawer/modal com detalhes empresa-a-empresa */}
      {detalhe ? (
        <DetalhesExecucaoModal
          execucao={detalhe}
          onFechar={() => setDetalhe(null)}
        />
      ) : null}
    </main>
  );
}

function DetalhesExecucaoModal({
  execucao,
  onFechar,
}: {
  execucao: ExecucaoRoboSefazDetail;
  onFechar: () => void;
}) {
  const detalhes = execucao.detalhes ?? [];
  return (
    <div className="modal-backdrop" onClick={onFechar}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>Execução #{execucao.id}</h2>
          <button type="button" className="btn-ghost" onClick={onFechar}>
            ✕
          </button>
        </header>
        <div className="modal-body">
          <p>
            <strong>Período:</strong>{" "}
            {formatarPeriodo(execucao.periodo_inicio, execucao.periodo_fim)}{" "}
            • <strong>Status:</strong>{" "}
            <span className={statusPillClass(execucao.status)}>
              {statusLabel(execucao.status)}
            </span>{" "}
            • <strong>Duração:</strong>{" "}
            {formatarDuracao(execucao.duracao_segundos)}
          </p>
          {execucao.motivo_erro ? (
            <p className="muted">
              <strong>Motivo erro:</strong> {execucao.motivo_erro}
            </p>
          ) : null}
          {detalhes.length === 0 ? (
            <p className="muted">Sem detalhes empresa-a-empresa.</p>
          ) : (
            <table className="table-compact">
              <thead>
                <tr>
                  <th>Empresa</th>
                  <th>CNPJ</th>
                  <th>Resultado</th>
                  <th>Duração</th>
                  <th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {detalhes.map((d, idx) => (
                  <tr key={idx}>
                    <td>{d.razao_social ?? "—"}</td>
                    <td>{d.cnpj ?? "—"}</td>
                    <td>
                      <span className={statusPillFromDetalhe(d)}>
                        {labelFromDetalhe(d)}
                      </span>
                    </td>
                    <td>{formatarDuracao(d.duracao_segundos)}</td>
                    <td>
                      <small>{d.motivo ?? "—"}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function statusPillFromDetalhe(d: DetalheEmpresa): string {
  if (d.sem_resultados) return "pill pill-muted";
  if (d.sucesso) return "pill pill-ok";
  return "pill pill-err";
}

function labelFromDetalhe(d: DetalheEmpresa): string {
  if (d.sem_resultados) return "Sem notas";
  if (d.sucesso) {
    const novos = d.upload_pac?.persistidos ?? 0;
    const dup = d.upload_pac?.duplicados ?? 0;
    const total = d.upload_pac?.total_arquivos ?? novos + dup;
    if (total === 0) return "OK";
    // Mostra "novos / total" pra deixar claro que duplicados foram baixados
    // mas já existiam no banco (não é erro, não é vazio — é dedup).
    if (dup > 0 && novos === 0) return `OK (${dup} já existiam)`;
    if (dup > 0) return `OK (${novos} novos, ${dup} dup)`;
    return `OK (${novos} XMLs)`;
  }
  return "Erro";
}
