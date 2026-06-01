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

function RelatoriosContent() {
  const [resumo, setResumo] = useState<ResumoMensal | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([obterResumoMensal(), listarEmpresas()])
      .then(([r, e]) => { setResumo(r); setEmpresas(e); })
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar relatorios.");
      });
  }, []);

  async function handleGeral() {
    setBusy("geral"); setToast(null); setError(null);
    try {
      await gerarExcelGeral();
      setToast("relatorio_geral.xlsx baixado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar.");
    } finally {
      setBusy(null);
    }
  }

  async function handleEmpresa(empresa: Empresa) {
    setBusy(`emp-${empresa.id}`); setToast(null); setError(null);
    try {
      await gerarExcelEmpresa(empresa.id, empresa.razao_social);
      setToast(`Relatorio de ${empresa.razao_social} baixado.`);
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
          <h2>Relatorios</h2>
          <p className="muted">
            Excel consolidado por empresa e periodo. Inclui NF-e, CT-e, NFSe e trilha de erros.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleGeral}
            disabled={busy === "geral"}
          >
            {busy === "geral" ? "Gerando..." : "Baixar relatorio geral"}
          </button>
        </div>
      </header>

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      <section className="grid">
        <article className="metric metric--cyan">
          <span>XMLs no mes</span>
          <strong>{resumo?.total_xmls_mes ?? "—"}</strong>
          <p>baixados desde o dia 1</p>
        </article>
        <article className="metric metric--emerald">
          <span>NF-e</span>
          <strong>{resumo?.total_nfe ?? "—"}</strong>
          <p>recebidas no periodo</p>
        </article>
        <article className="metric metric--violet">
          <span>CT-e</span>
          <strong>{resumo?.total_cte ?? "—"}</strong>
          <p>recebidas no periodo</p>
        </article>
        <article className="metric metric--amber">
          <span>NFSe</span>
          <strong>{resumo?.total_nfse ?? "—"}</strong>
          <p>recebidas no periodo</p>
        </article>
      </section>

      <section className="panel info-card">
        <h3>Por empresa</h3>
        <p className="muted">
          Excel com aba dedicada para NF-e, CT-e e NFSe da empresa selecionada.
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
