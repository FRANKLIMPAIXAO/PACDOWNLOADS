"use client";

import { useCallback, useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import {
  Cobranca,
  CobrancasResumo,
  brl,
  dataBR,
  listarCobrancas,
  marcarCobrancaPaga,
} from "../../lib/cobrancas";

export default function CobrancasPage() {
  return (
    <ProtectedRoute>
      <CobrancasContent />
    </ProtectedRoute>
  );
}

type Filtro = "pendentes" | "pagas" | "todas";

function CobrancasContent() {
  const [cobrancas, setCobrancas] = useState<Cobranca[] | null>(null);
  const [resumo, setResumo] = useState<CobrancasResumo | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("pendentes");
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setBusy("carregar"); setErro(null);
    try {
      const paga = filtro === "pendentes" ? false : filtro === "pagas" ? true : undefined;
      const r = await listarCobrancas({ paga });
      setCobrancas(r.cobrancas);
      setResumo(r.resumo);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar cobranças.");
    } finally { setBusy(null); }
  }, [filtro]);

  useEffect(() => { carregar(); }, [carregar]);

  async function alternarPaga(c: Cobranca) {
    setBusy(`paga-${c.id}`); setErro(null);
    try {
      await marcarCobrancaPaga(c.id, !c.paga);
      setToast(!c.paga ? "Cobrança marcada como paga." : "Cobrança reaberta.");
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao atualizar a cobrança.");
    } finally { setBusy(null); }
  }

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Cobranças do portal</h1>
          <p className="muted">
            Recálculos de DAS que os clientes pediram no portal. O 1º de cada guia
            é grátis; do 2º em diante são R$ 5,00. Marque como paga ao faturar.
          </p>
        </div>
      </header>

      {toast ? <div className="toast" onClick={() => setToast(null)}>{toast}</div> : null}
      {erro ? <div className="toast toast-error" onClick={() => setErro(null)}>{erro}</div> : null}

      {/* Resumo */}
      <section className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))", marginBottom: 16 }}>
        <div className="metric metric--amber">
          <span>A receber</span>
          <strong>{resumo ? brl(resumo.a_receber) : "—"}</strong>
          <p>{resumo ? `${resumo.pendentes} cobrança(s) em aberto` : ""}</p>
        </div>
        <div className="metric metric--emerald">
          <span>Recebido</span>
          <strong>{resumo ? brl(resumo.recebido) : "—"}</strong>
          <p>já faturado</p>
        </div>
        <div className="metric metric--cyan">
          <span>Valor por recálculo extra</span>
          <strong>R$ 5,00</strong>
          <p>1º recálculo de cada guia é grátis</p>
        </div>
      </section>

      {/* Filtro */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {([
          { v: "pendentes", label: "Pendentes" },
          { v: "pagas", label: "Pagas" },
          { v: "todas", label: "Todas" },
        ] as { v: Filtro; label: string }[]).map((f) => (
          <button key={f.v} type="button" className={filtro === f.v ? "btn-primary" : "btn-ghost"} onClick={() => setFiltro(f.v)}>
            {f.label}
          </button>
        ))}
      </div>

      {cobrancas === null ? (
        <p className="muted">Carregando…</p>
      ) : cobrancas.length === 0 ? (
        <section className="table-card">
          <header><h2>Sem cobranças</h2></header>
          <p className="muted" style={{ padding: 16 }}>
            {filtro === "pendentes"
              ? "Nenhuma cobrança em aberto. 🎉"
              : "Nenhuma cobrança neste filtro."}
          </p>
        </section>
      ) : (
        <DataTable
          title={`Cobranças (${cobrancas.length})`}
          subtitle="Cada linha é um recálculo de DAS cobrado de um cliente no portal."
          headers={["Empresa", "Competência", "Descrição", "Valor", "Data", "Status", "Ação"]}
          rows={cobrancas.map((c) => [
            <span key={`emp-${c.id}`}>
              <strong>{c.empresa_razao_social ?? `#${c.empresa_id}`}</strong>
              <br /><small className="muted">{c.empresa_cnpj}</small>
            </span>,
            c.competencia ? `${c.competencia.slice(4)}/${c.competencia.slice(0, 4)}` : "—",
            c.descricao || "Recálculo DAS",
            <strong key={`v-${c.id}`}>{brl(c.valor)}</strong>,
            dataBR(c.criada_em),
            <span key={`s-${c.id}`} className={c.paga ? "pill pill-ok" : "pill pill-warn"}>
              {c.paga ? "Paga" : "Em aberto"}
            </span>,
            <button key={`a-${c.id}`} type="button" className="btn-ghost" onClick={() => alternarPaga(c)} disabled={busy !== null}>
              {busy === `paga-${c.id}` ? "..." : (c.paga ? "Reabrir" : "✓ Marcar paga")}
            </button>,
          ])}
        />
      )}
    </main>
  );
}
