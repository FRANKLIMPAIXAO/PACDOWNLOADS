"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import {
  MesReceita,
  listarReceitasMensais,
  puxarReceitaDaReceita,
  salvarReceitasMensais,
} from "../lib/receitas-mensais";

function fmtMes(anoMes: string): string {
  const ano = anoMes.slice(0, 4);
  const mes = anoMes.slice(4);
  const nomes = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  return `${nomes[Number(mes)] || mes}/${ano}`;
}

function fmtBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Grade de faturamento dos 12 meses anteriores à competência — RBT12.
 * Sem isso o DAS de empresas migradas não bate com o da Receita.
 */
export function Rbt12Card({
  empresaId,
  anoMes,
  onSalvo,
}: {
  empresaId: number;
  anoMes: string;
  onSalvo?: () => void;
}) {
  const [meses, setMeses] = useState<MesReceita[]>([]);
  const [rbt12, setRbt12] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setError(null);
    try {
      const r = await listarReceitasMensais(empresaId, anoMes);
      setMeses(r.meses);
      setRbt12(r.rbt12);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Falha ao carregar faturamento.");
    }
  }, [empresaId, anoMes]);

  useEffect(() => { carregar(); }, [carregar]);

  function setValor(i: number, campo: "valor_interno" | "valor_externo", valor: string) {
    const novo = [...meses];
    novo[i] = { ...novo[i], [campo]: Number(valor) || 0 };
    setMeses(novo);
    setRbt12(novo.reduce((s, m) => s + m.valor_interno + m.valor_externo, 0));
  }

  async function handleSalvar() {
    setBusy("save"); setError(null); setToast(null);
    try {
      await salvarReceitasMensais(empresaId, meses);
      setToast("Faturamento salvo. RBT12 atualizado para o cálculo do DAS.");
      if (onSalvo) onSalvo();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Falha ao salvar.");
    } finally { setBusy(null); }
  }

  async function handlePuxar() {
    setBusy("puxar"); setError(null); setToast(null);
    try {
      const r = await puxarReceitaDaReceita(empresaId, anoMes);
      // Funde os valores puxados na grade
      const mapa = new Map(r.meses.map((m) => [m.ano_mes, m]));
      const novo = meses.map((m) => {
        const p = mapa.get(m.ano_mes);
        return p && p.encontrado
          ? { ...m, valor_interno: p.valor_interno, valor_externo: p.valor_externo, origem: "receita" }
          : m;
      });
      setMeses(novo);
      setRbt12(novo.reduce((s, m) => s + m.valor_interno + m.valor_externo, 0));
      setToast(
        `Puxados ${r.encontrados}/${r.total_meses} meses da Receita.` +
        (r.aviso ? ` ${r.aviso}` : " Revise e clique Salvar."),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Falha ao puxar da Receita.");
    } finally { setBusy(null); }
  }

  return (
    <section className="panel" style={{ marginTop: 12 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ margin: 0 }}>Faturamento dos 12 meses anteriores (RBT12)</h3>
          <p className="muted" style={{ margin: "4px 0", fontSize: 13 }}>
            Necessário pro DAS bater com a Receita. Empresa migrada não tem o
            histórico — informe manualmente ou puxe da Receita.
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="muted" style={{ fontSize: 11 }}>RBT12 (soma)</div>
          <div style={{ fontSize: 22, fontWeight: 600, color: "rgb(34,197,94)" }}>{fmtBRL(rbt12)}</div>
        </div>
      </header>

      {toast ? <p className="toast toast-ok" style={{ fontSize: 13 }}>{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      <div style={{ display: "flex", gap: 8, margin: "8px 0", flexWrap: "wrap" }}>
        <button type="button" className="btn-secondary" onClick={handlePuxar} disabled={busy !== null}>
          {busy === "puxar" ? "Puxando..." : "📥 Puxar da Receita (Integra Contador)"}
        </button>
        <button type="button" className="btn-primary" onClick={handleSalvar} disabled={busy !== null}>
          {busy === "save" ? "Salvando..." : "💾 Salvar faturamento"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
        {meses.map((m, i) => (
          <div
            key={m.ano_mes}
            style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 8,
              padding: "8px 10px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong style={{ fontSize: 13 }}>{fmtMes(m.ano_mes)}</strong>
              {m.origem === "receita" ? (
                <span className="pill pill-ok" style={{ fontSize: 10 }}>Receita</span>
              ) : null}
            </div>
            <label style={{ display: "block", marginTop: 6 }}>
              <span className="muted" style={{ fontSize: 10 }}>Receita interna (R$)</span>
              <input
                type="number" step="0.01" min="0"
                value={m.valor_interno || ""}
                onChange={(e) => setValor(i, "valor_interno", e.target.value)}
                style={{ width: "100%", padding: "4px 6px", fontSize: 13 }}
              />
            </label>
            <label style={{ display: "block", marginTop: 4 }}>
              <span className="muted" style={{ fontSize: 10 }}>Exportação (R$)</span>
              <input
                type="number" step="0.01" min="0"
                value={m.valor_externo || ""}
                onChange={(e) => setValor(i, "valor_externo", e.target.value)}
                style={{ width: "100%", padding: "4px 6px", fontSize: 13 }}
              />
            </label>
          </div>
        ))}
      </div>
    </section>
  );
}
