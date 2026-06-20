"use client";

import Link from "next/link";
import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { SituacaoFiscalCarteira } from "../../components/situacao-fiscal-carteira";
import { ApiError } from "../../lib/api";
import {
  CndDashboardLinha,
  StatusCertidao,
  TIPOS_CND,
  dashboardCnds,
  efetivoLabel,
  efetivoPillClass,
  renovarVencendo,
} from "../../lib/cnds";

export default function PrevencaoPage() {
  return (
    <ProtectedRoute>
      <PrevencaoContent />
    </ProtectedRoute>
  );
}

function PrevencaoContent() {
  const [cnds, setCnds] = useState<CndDashboardLinha[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [renovandoTodas, setRenovandoTodas] = useState(false);

  // Carrega SÓ o dashboard de CNDs (1 chamada, lê do banco). NÃO dispara mais
  // caixa-postal/procuração/DTE por empresa (eram 100+ chamadas Integra ao vivo
  // que estouravam o Traefik e travavam a tela em "Carregando").
  const carregarCnds = useCallback(async () => {
    setError(null);
    try {
      setCnds(await dashboardCnds());
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao carregar CNDs.");
    }
  }, []);

  useEffect(() => { carregarCnds(); }, [carregarCnds]);

  async function handleRenovarTodas() {
    setRenovandoTodas(true);
    setToast(null); setError(null);
    try {
      const r = await renovarVencendo(7);
      setToast(`Robô SEFAZ: ${r.sucesso} renovadas · ${r.falhas} falhas · ${r.pulados} ainda válidas.`);
      await carregarCnds();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao renovar.");
    } finally {
      setRenovandoTodas(false);
    }
  }

  const totais = useMemo(() => {
    if (!cnds) return null;
    let validas = 0, aVencer = 0, vencidas = 0, pendencia = 0;
    for (const c of cnds) {
      for (const tipo of TIPOS_CND) {
        const cert = c[tipo.tipo.toLowerCase() as keyof CndDashboardLinha] as
          | { status: StatusCertidao; situacao_fiscal?: string | null } | null;
        if (!cert) continue;
        if (cert.situacao_fiscal === "pendencias") pendencia++;
        else if (cert.status === "VALIDA" && cert.situacao_fiscal !== "verificar") validas++;
        else if (cert.status === "A_VENCER") aVencer++;
        else if (cert.status === "VENCIDA") vencidas++;
      }
    }
    return { validas, aVencer, vencidas, pendencia };
  }, [cnds]);

  const tiposTabela = TIPOS_CND.filter((t) => !t.sob_demanda);
  const cndRows: ReactNode[][] = (cnds ?? []).map((c) => [
    <Link key={`ce-${c.empresa_id}`} href={`/empresas/${c.empresa_id}`} className="row-link">
      {c.empresa_razao_social}
    </Link>,
    ...tiposTabela.map((t) => {
      const cert = c[t.tipo.toLowerCase() as keyof CndDashboardLinha] as
        | { status: StatusCertidao; situacao_fiscal?: string | null; pendencias?: string[]; data_validade: string } | null;
      if (!cert) return <span key={`${c.empresa_id}-${t.tipo}`} className="pill pill-muted">—</span>;
      const pend = cert.pendencias && cert.pendencias.length ? ` · ${cert.pendencias.join(" · ")}` : "";
      return (
        <span key={`${c.empresa_id}-${t.tipo}`} className={efetivoPillClass(cert)} title={`${t.fonte} · validade ${cert.data_validade}${pend}`}>
          {efetivoLabel(cert)}
        </span>
      );
    }),
    <ScoreBar key={`sc-${c.empresa_id}`} score={c.score} />,
  ]);

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Prevenção</h2>
          <p className="muted">Saúde fiscal da carteira — triagem por exceção + controle de CNDs.</p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn-primary" onClick={handleRenovarTodas} disabled={renovandoTodas}>
            {renovandoTodas ? "Renovando..." : "🤖 Robô SEFAZ — renovar CNDs vencendo"}
          </button>
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}
      {toast ? <p className="toast">{toast}</p> : null}

      {/* Situação fiscal consolidada da carteira — triagem por exceção (estilo Jettax). */}
      <SituacaoFiscalCarteira />

      <header className="page-header" style={{ marginTop: 8 }}>
        <div>
          <h3>Controle de CNDs</h3>
          <p className="muted">
            Federal · FGTS · Trabalhista · Estadual · Municipal — clique numa empresa para gerenciar.
          </p>
        </div>
      </header>
      {totais ? (
        <p className="muted" style={{ marginTop: -6, marginBottom: 8, fontSize: "0.86rem" }}>
          {totais.pendencia} com pendência · {totais.vencidas} vencidas · {totais.aVencer} a vencer · {totais.validas} válidas
        </p>
      ) : null}
      {cnds === null ? (
        <section className="panel"><p className="muted">Carregando CNDs…</p></section>
      ) : (
        <DataTable
          headers={["Empresa", ...tiposTabela.map((t) => t.label), "Score"]}
          rows={cndRows}
          subtitle={`${cnds.length} empresa(s).`}
        />
      )}
    </>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const cls = score >= 0.8 ? "" : score >= 0.5 ? "score-bar--med" : "score-bar--low";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 120 }}>
      <div className={`score-bar ${cls}`}>
        <div className="score-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: "0.85rem", color: "var(--muted-strong)", minWidth: 32 }}>{pct}%</span>
    </div>
  );
}
