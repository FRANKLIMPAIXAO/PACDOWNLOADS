"use client";

import { useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  GuiaDASComEmpresa,
  baixarPdf,
  dashboardAtrasadas,
  emitirGuiaAtualizada,
  formatarDataBR,
  formatarReal,
  situacaoLabel,
  situacaoPillClass,
  syncEmpresa,
} from "../../lib/guias-das";

export default function GuiasDASPage() {
  return (
    <ProtectedRoute>
      <DASContent />
    </ProtectedRoute>
  );
}

function DASContent() {
  const [atrasadas, setAtrasadas] = useState<GuiaDASComEmpresa[] | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [empresaSync, setEmpresaSync] = useState<number | "todas">("todas");
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    carregar();
  }, []);

  async function carregar() {
    setBusy("carregar");
    setErro(null);
    try {
      const [g, e] = await Promise.all([
        dashboardAtrasadas(),
        listarEmpresas(),
      ]);
      setAtrasadas(g);
      setEmpresas(e);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar dados");
    } finally {
      setBusy(null);
    }
  }

  async function handleSync() {
    if (empresaSync === "todas") {
      setErro("Sync 'todas as empresas' precisa rodar via Celery (worker). Selecione uma empresa específica pra disparo imediato.");
      return;
    }
    const ano = new Date().getFullYear();
    setBusy("sync");
    setErro(null);
    try {
      const r = await syncEmpresa(empresaSync as number, ano);
      setToast(
        `Sync OK: ${r.novas} novas, ${r.atualizadas} atualizadas, ${r.pagas_detectadas} pagas detectadas` +
        (r.erros > 0 ? `, ${r.erros} erros` : ""),
      );
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao sincronizar");
    } finally {
      setBusy(null);
    }
  }

  async function handleAtualizar(guiaId: number) {
    setBusy(`atualizar-${guiaId}`);
    setErro(null);
    try {
      const guia = await emitirGuiaAtualizada(guiaId);
      setToast(
        `Guia ${guia.competencia_formatada} emitida! Valor atualizado: ${formatarReal(guia.valor_atualizado)}`,
      );
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao emitir guia atualizada");
    } finally {
      setBusy(null);
    }
  }

  async function handleDownload(guiaId: number, competencia: string) {
    setBusy(`pdf-${guiaId}`);
    setErro(null);
    try {
      const blob = await baixarPdf(guiaId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `DAS_${competencia.replace("/", "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao baixar PDF");
    } finally {
      setBusy(null);
    }
  }

  // Totalizadores
  const totalAtrasadasValor =
    atrasadas?.reduce(
      (acc, g) => acc + parseFloat(g.valor_principal || "0"),
      0,
    ) ?? 0;
  const totalEmpresasComAtraso = new Set(
    atrasadas?.map((g) => g.empresa_id) ?? [],
  ).size;

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Guias DAS — Simples Nacional</h1>
          <p className="muted">
            Controle de DAS atrasadas e emissão de guias atualizadas (com
            Selic+mora) via Integra Contador.
          </p>
        </div>
      </header>

      {toast ? (
        <div className="toast" onClick={() => setToast(null)}>
          {toast}
        </div>
      ) : null}
      {erro ? (
        <div className="toast toast-error" onClick={() => setErro(null)}>
          {erro}
        </div>
      ) : null}

      {/* Card de totais */}
      <section className="table-card" style={{ marginBottom: 16 }}>
        <header>
          <h2>Resumo de atrasadas</h2>
        </header>
        <dl className="kv-grid" style={{ padding: 16 }}>
          <dt>Guias atrasadas</dt>
          <dd>
            <strong>{atrasadas?.length ?? "—"}</strong>
          </dd>
          <dt>Empresas com atraso</dt>
          <dd>{totalEmpresasComAtraso}</dd>
          <dt>Valor total (sem mora)</dt>
          <dd>{formatarReal(totalAtrasadasValor)}</dd>
        </dl>
      </section>

      {/* Sincronizar manualmente */}
      <section className="table-card" style={{ marginBottom: 16 }}>
        <header>
          <h2>Sincronizar via Integra Contador</h2>
        </header>
        <div style={{ padding: 16, display: "flex", gap: 12, alignItems: "center" }}>
          <select
            value={empresaSync}
            onChange={(e) =>
              setEmpresaSync(
                e.target.value === "todas" ? "todas" : Number(e.target.value),
              )
            }
            disabled={busy !== null}
            style={{ minWidth: 280 }}
          >
            <option value="todas">— Selecione empresa —</option>
            {empresas?.map((e) => (
              <option key={e.id} value={e.id}>
                {e.razao_social} ({e.cnpj})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSync}
            disabled={busy !== null || empresaSync === "todas"}
          >
            {busy === "sync" ? "Sincronizando..." : "Sincronizar ano atual"}
          </button>
          <small className="muted">
            Para sync de todas: rode o worker Celery (task <code>sync_guias_das_diario</code>).
          </small>
        </div>
      </section>

      {/* Tabela de atrasadas */}
      {atrasadas === null ? (
        <p className="muted">Carregando…</p>
      ) : atrasadas.length === 0 ? (
        <section className="table-card">
          <header>
            <h2>Dashboard — DAS atrasadas</h2>
          </header>
          <p className="muted" style={{ padding: 16 }}>
            Nenhuma guia atrasada agora. 🎉 Quando alguma vencer sem pagamento,
            aparece aqui automaticamente após o próximo sync (cron 09h).
          </p>
        </section>
      ) : (
        <DataTable
          title={`Dashboard — DAS atrasadas (${atrasadas.length})`}
          subtitle="Ordenado por vencimento mais antigo. Clique em 'Atualizar' pra emitir guia com Selic+mora; depois 'PDF' pra baixar."
          headers={[
            "Empresa",
            "Competência",
            "Vencimento",
            "Valor original",
            "Atraso",
            "Situação",
            "Atualizado",
            "Ações",
          ]}
          rows={atrasadas.map((g) => [
            <span key={`emp-${g.id}`}>
              <strong>{g.empresa_razao_social ?? `#${g.empresa_id}`}</strong>
              <br />
              <small className="muted">{g.empresa_cnpj}</small>
            </span>,
            g.competencia_formatada,
            formatarDataBR(g.data_vencimento_original),
            formatarReal(g.valor_principal),
            <span key={`atr-${g.id}`}>
              {g.dias_atraso > 0 ? <strong>{g.dias_atraso}d</strong> : "—"}
            </span>,
            <span key={`sit-${g.id}`} className={situacaoPillClass(g.situacao)}>
              {situacaoLabel(g.situacao)}
            </span>,
            g.valor_atualizado ? (
              <span key={`va-${g.id}`}>
                {formatarReal(g.valor_atualizado)}
                <br />
                <small className="muted">
                  Venc: {formatarDataBR(g.data_vencimento_atualizada)}
                </small>
              </span>
            ) : (
              <span className="muted">—</span>
            ),
            <div key={`act-${g.id}`} style={{ display: "flex", gap: 4 }}>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => handleAtualizar(g.id)}
                disabled={busy !== null}
              >
                {busy === `atualizar-${g.id}` ? "..." : "Atualizar"}
              </button>
              {g.pdf_path ? (
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => handleDownload(g.id, g.competencia_formatada)}
                  disabled={busy !== null}
                >
                  {busy === `pdf-${g.id}` ? "..." : "PDF"}
                </button>
              ) : null}
            </div>,
          ])}
        />
      )}
    </main>
  );
}
