"use client";

import { ReactNode, useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  ResumoMensal,
  gerarExcelEmpresa,
  gerarExcelGeral,
  obterResumoMensal,
} from "../../lib/relatorios";

export default function RelatoriosPage() {
  return (
    <ProtectedRoute>
      <RelatoriosContent />
    </ProtectedRoute>
  );
}

// Competência corrente no formato YYYY-MM (para o <input type="month">).
function competenciaAtual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// "2026-07" → "julho/2026" para os rótulos.
function competenciaLabel(c: string): string {
  const [ano, mes] = c.split("-");
  const nomes = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
  ];
  const idx = Number(mes) - 1;
  return idx >= 0 && idx < 12 ? `${nomes[idx]}/${ano}` : c;
}

function RelatoriosContent() {
  const [competencia, setCompetencia] = useState<string>(competenciaAtual);
  const [resumo, setResumo] = useState<ResumoMensal | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Empresas carregam uma vez; o resumo recarrega a cada troca de competência.
  useEffect(() => {
    listarEmpresas()
      .then(setEmpresas)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Falha ao carregar empresas."));
  }, []);

  useEffect(() => {
    setResumo(null);
    obterResumoMensal(competencia)
      .then(setResumo)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Falha ao carregar resumo."));
  }, [competencia]);

  async function handleGeral() {
    setBusy("geral"); setToast(null); setError(null);
    try {
      await gerarExcelGeral(competencia);
      setToast(`Relatório geral de ${competenciaLabel(competencia)} baixado.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar.");
    } finally {
      setBusy(null);
    }
  }

  async function handleEmpresa(empresa: Empresa) {
    setBusy(`emp-${empresa.id}`); setToast(null); setError(null);
    try {
      await gerarExcelEmpresa(empresa.id, empresa.razao_social, competencia);
      setToast(`Relatório de ${empresa.razao_social} (${competenciaLabel(competencia)}) baixado.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar.");
    } finally {
      setBusy(null);
    }
  }

  const empresaRows: ReactNode[][] = (empresas ?? []).map((e) => [
    e.razao_social,
    e.cnpj,
    e.regime_tributario || "—",
    <button
      key={`x-${e.id}`}
      type="button"
      className="btn-secondary"
      style={{ padding: "5px 11px", fontSize: "0.82rem" }}
      onClick={() => handleEmpresa(e)}
      disabled={busy === `emp-${e.id}`}
    >
      {busy === `emp-${e.id}` ? "..." : "Baixar Excel"}
    </button>,
  ]);

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Relatórios</h2>
          <p className="muted">
            Excel consolidado por empresa e competência. Inclui NF-e, CT-e, NFSe e trilha de erros.
          </p>
        </div>
        <div className="page-actions" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.85rem", color: "var(--muted-strong)" }}>
            Competência
            <input
              type="month"
              value={competencia}
              onChange={(e) => setCompetencia(e.target.value || competenciaAtual())}
              className="btn-secondary"
              style={{ padding: "7px 10px", fontSize: "0.88rem", cursor: "pointer" }}
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            onClick={handleGeral}
            disabled={busy === "geral"}
          >
            {busy === "geral" ? "Gerando..." : "Baixar relatório geral"}
          </button>
        </div>
      </header>

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      <p className="muted" style={{ marginTop: -6, marginBottom: 12, fontSize: "0.86rem" }}>
        Mostrando <strong>{competenciaLabel(competencia)}</strong> — documentos por data de emissão.
      </p>

      <section className="grid">
        <article className="metric metric--cyan">
          <span>XMLs na competência</span>
          <strong>{resumo?.total_xmls_mes ?? "—"}</strong>
          <p>emitidos em {competenciaLabel(competencia)}</p>
        </article>
        <article className="metric metric--emerald">
          <span>NF-e</span>
          <strong>{resumo?.total_nfe ?? "—"}</strong>
          <p>no período</p>
        </article>
        <article className="metric metric--violet">
          <span>CT-e</span>
          <strong>{resumo?.total_cte ?? "—"}</strong>
          <p>no período</p>
        </article>
        <article className="metric metric--amber">
          <span>NFSe</span>
          <strong>{resumo?.total_nfse ?? "—"}</strong>
          <p>no período</p>
        </article>
      </section>

      <section className="panel info-card">
        <h3>Por empresa</h3>
        <p className="muted">
          Excel de <strong>{competenciaLabel(competencia)}</strong> com aba dedicada para NF-e, CT-e e NFSe da empresa.
        </p>
        {empresas === null ? (
          <p className="muted">Carregando...</p>
        ) : empresas.length === 0 ? (
          <p className="muted">Nenhuma empresa cadastrada ainda.</p>
        ) : (
          <DataTable
            headers={["Empresa", "CNPJ", "Regime", "Acao"]}
            rows={empresaRows}
          />
        )}
      </section>
    </>
  );
}
