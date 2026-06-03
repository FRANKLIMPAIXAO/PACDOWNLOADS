"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import {
  AutoCadastrarTodasResultado,
  Empresa,
  autoCadastrarFocusTodas,
  listarEmpresas,
} from "../../lib/empresas";

function formatCidade(empresa: Empresa): string {
  if (empresa.municipio && empresa.uf) return `${empresa.municipio}/${empresa.uf}`;
  return empresa.municipio || empresa.uf || "—";
}

export default function EmpresasPage() {
  return (
    <ProtectedRoute>
      <EmpresasContent />
    </ProtectedRoute>
  );
}

function EmpresasContent() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoCadBusy, setAutoCadBusy] = useState(false);
  const [autoCadResult, setAutoCadResult] = useState<AutoCadastrarTodasResultado | null>(null);

  function recarregar() {
    listarEmpresas()
      .then(setEmpresas)
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar empresas.");
      });
  }

  useEffect(() => {
    recarregar();
  }, []);

  // Quantas empresas estão elegíveis pra auto-cadastro Focus
  // (ativa + cert A1 + sem focus_token)
  const elegiveisAutoCad = (empresas ?? []).filter(
    (e) => e.ativo && e.tem_certificado_a1 && !e.tem_focus_token,
  );

  async function handleAutoCadastrarTodas() {
    if (elegiveisAutoCad.length === 0) return;
    const ok = confirm(
      `Auto-cadastrar ${elegiveisAutoCad.length} empresa(s) no Focus NFe?\n\n` +
      `Vai usar o FOCUS_MASTER_TOKEN configurado no backend pra cadastrar cada ` +
      `empresa (POST /v2/empresas) reutilizando o cert A1 já salvo no PAC.\n\n` +
      `O token retornado por empresa fica salvo automaticamente (cifrado).\n\n` +
      `Pode levar alguns minutos (1-3 seg por empresa). Continuar?`,
    );
    if (!ok) return;
    setAutoCadBusy(true);
    setAutoCadResult(null);
    try {
      const r = await autoCadastrarFocusTodas();
      setAutoCadResult(r);
      recarregar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Falha ao auto-cadastrar");
    } finally {
      setAutoCadBusy(false);
    }
  }

  const header = (
    <header className="page-header">
      <div>
        <h2>Empresas</h2>
        <p className="muted">
          Cadastro local + integracao Focus NFe (token + certificado A1) por empresa.
        </p>
      </div>
      <div className="page-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {elegiveisAutoCad.length > 0 ? (
          <button
            type="button"
            className="btn-primary"
            onClick={handleAutoCadastrarTodas}
            disabled={autoCadBusy}
            title={
              `Cadastra ${elegiveisAutoCad.length} empresa(s) no Focus NFe ` +
              `reusando o cert A1 já salvo. Usa FOCUS_MASTER_TOKEN do backend.`
            }
          >
            {autoCadBusy
              ? `Cadastrando ${elegiveisAutoCad.length}...`
              : `🔗 Auto-cadastrar ${elegiveisAutoCad.length} no Focus`}
          </button>
        ) : null}
        <Link href="/empresas/novo" className="btn-primary">
          + Nova empresa
        </Link>
      </div>
    </header>
  );

  // Toast de resultado do batch auto-cadastro Focus
  const autoCadToast = autoCadResult ? (
    <section
      className="panel"
      style={{
        background: autoCadResult.falhas > 0
          ? "rgba(239, 68, 68, 0.08)"
          : "rgba(16, 185, 129, 0.08)",
        marginBottom: 16,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <strong>
            {autoCadResult.sucesso > 0 ? "✅ " : ""}
            Auto-cadastro Focus NFe concluído
          </strong>
          <p className="muted" style={{ margin: "4px 0", fontSize: 13 }}>
            ✓ {autoCadResult.sucesso} cadastrada(s) com sucesso ·{" "}
            {autoCadResult.ja_tinham} já tinham token ·{" "}
            {autoCadResult.falhas > 0 ? `❌ ${autoCadResult.falhas} falharam · ` : ""}
            {autoCadResult.sem_cert > 0 ? `${autoCadResult.sem_cert} sem cert A1` : ""}
          </p>
          {autoCadResult.detalhes && autoCadResult.detalhes.length > 0 ? (
            <details style={{ marginTop: 8 }}>
              <summary style={{ cursor: "pointer", fontSize: 13 }}>
                Detalhes por empresa ({autoCadResult.detalhes.length})
              </summary>
              <ul style={{ margin: 8, fontSize: 12 }}>
                {autoCadResult.detalhes.map((d, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>
                    <strong>{d.razao_social}</strong> ({d.cnpj}) —{" "}
                    {d.status === "ok" ? "✅ ok" : `❌ ${d.erro}`}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => setAutoCadResult(null)}
          aria-label="Fechar"
        >
          ✕
        </button>
      </div>
    </section>
  ) : null;

  if (error) {
    return (
      <section className="panel">
        {header}
        <p className="auth-error">{error}</p>
      </section>
    );
  }

  if (empresas === null) {
    return (
      <section className="panel">
        {header}
        <p className="muted">Carregando...</p>
      </section>
    );
  }

  if (empresas.length === 0) {
    return (
      <section className="panel">
        {header}
        <div className="empty-state">
          Nenhuma empresa cadastrada ainda. Clique em <strong>Nova empresa</strong> para comecar.
        </div>
      </section>
    );
  }

  const rows: ReactNode[][] = empresas.map((empresa) => [
    <Link key={empresa.id} href={`/empresas/${empresa.id}`} className="row-link">
      {empresa.razao_social}
    </Link>,
    empresa.cnpj,
    formatCidade(empresa),
    empresa.regime_tributario || "—",
    empresa.ativo ? (
      <span className="pill pill-ok">Ativa</span>
    ) : (
      <span className="pill pill-warn">Inativa</span>
    ),
    empresa.ultimo_nsu_distribuicao ? `NSU ${empresa.ultimo_nsu_distribuicao}` : "—",
  ]);

  return (
    <>
      {header}
      {autoCadToast}
      <DataTable
        title=""
        subtitle={`${empresas.length} empresa(s) cadastrada(s).`}
        headers={["Empresa", "CNPJ", "Cidade", "Regime", "Status", "Ultimo NSU"]}
        rows={rows}
      />
    </>
  );
}
