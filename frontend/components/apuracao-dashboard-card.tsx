"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import {
  ResumoMes,
  currentAnoMes,
  formatAnoMes,
  obterResumoMes,
  previousAnoMes,
} from "../lib/apuracoes";


function fmtBRL(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}


export function ApuracaoDashboardCard() {
  const [anoMes, setAnoMes] = useState<string>(previousAnoMes());
  const [resumo, setResumo] = useState<ResumoMes | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResumo(null); setError(null);
    obterResumoMes(anoMes)
      .then(setResumo)
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar resumo.");
      });
  }, [anoMes]);

  const pctConcluido = resumo && resumo.total_empresas_ativas > 0
    ? Math.round((resumo.das_gerados / resumo.total_empresas_ativas) * 100)
    : 0;

  const pctPago = resumo && resumo.valor_devido_total > 0
    ? Math.round((resumo.valor_pago / resumo.valor_devido_total) * 100)
    : 0;

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <div>
          <h3>Apurações Mensais</h3>
          <p className="muted">PGDAS-D Simples Nacional · controle do escritório</p>
        </div>
        <div className="page-actions">
          <input
            type="month"
            value={`${anoMes.slice(0, 4)}-${anoMes.slice(4)}`}
            onChange={(e) => {
              const v = e.target.value;
              if (v) setAnoMes(v.replace("-", ""));
            }}
            style={{
              padding: "6px 10px", fontSize: "0.86rem",
              background: "var(--bg-1)", border: "1px solid var(--border)",
              borderRadius: 8, color: "var(--text)",
            }}
          />
          <Link href="/apuracoes" className="btn-secondary" style={{ padding: "8px 12px", fontSize: "0.86rem" }}>
            Abrir →
          </Link>
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      {!resumo ? (
        <p className="muted">Carregando...</p>
      ) : (
        <>
          <p style={{ margin: 0, color: "var(--muted-strong)", fontSize: "0.92rem" }}>
            <strong style={{ color: "var(--text-strong)" }}>{formatAnoMes(anoMes)}</strong>
            {" · "}
            {resumo.apuracoes_geradas} de {resumo.total_empresas_ativas} empresas com apuração
          </p>

          {/* Barra de progresso "concluído" */}
          <div>
            <div style={{
              display: "flex", justifyContent: "space-between",
              fontSize: "0.78rem", color: "var(--muted)",
              marginBottom: 4,
            }}>
              <span>Apurações concluídas (DAS gerado)</span>
              <span>{pctConcluido}%</span>
            </div>
            <div className="score-bar">
              <div className="score-bar-fill" style={{ width: `${pctConcluido}%` }} />
            </div>
          </div>

          {/* Barra de progresso "pago" */}
          {resumo.valor_devido_total > 0 ? (
            <div>
              <div style={{
                display: "flex", justifyContent: "space-between",
                fontSize: "0.78rem", color: "var(--muted)",
                marginBottom: 4,
              }}>
                <span>Valor pago / devido</span>
                <span>{pctPago}%</span>
              </div>
              <div className={`score-bar ${pctPago < 50 ? "score-bar--low" : pctPago < 90 ? "score-bar--med" : ""}`}>
                <div className="score-bar-fill" style={{ width: `${pctPago}%` }} />
              </div>
            </div>
          ) : null}

          <dl className="kv-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <div>
              <dt style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Pendentes</dt>
              <dd>
                <span className={resumo.pendentes > 0 ? "pill pill-warn" : "pill pill-ok"}>
                  {resumo.pendentes}
                </span>
              </dd>
            </div>
            <div>
              <dt style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>DAS gerados</dt>
              <dd>
                <span className="pill pill-info">{resumo.das_gerados}</span>
              </dd>
            </div>
            <div>
              <dt style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Pagos</dt>
              <dd>
                <span className="pill pill-ok">{resumo.pagos}</span>
              </dd>
            </div>
          </dl>

          <dl className="kv-grid">
            <dt>Devido total</dt>
            <dd><strong>{fmtBRL(resumo.valor_devido_total)}</strong></dd>
            <dt>Pago</dt>
            <dd>{fmtBRL(resumo.valor_pago)}</dd>
            <dt>A pagar</dt>
            <dd>
              <strong style={{
                color: (resumo.valor_devido_total - resumo.valor_pago) > 0 ? "#fb7185" : "var(--text)",
              }}>
                {fmtBRL(resumo.valor_devido_total - resumo.valor_pago)}
              </strong>
            </dd>
          </dl>

          {resumo.empresas_pendentes.length > 0 ? (
            <>
              <p className="section-divider">Empresas pendentes</p>
              <ul style={{
                listStyle: "none", padding: 0, margin: 0,
                display: "grid", gap: 6,
              }}>
                {resumo.empresas_pendentes.slice(0, 4).map((e) => (
                  <li
                    key={e.id}
                    style={{
                      padding: "8px 12px",
                      border: "1px solid var(--border)",
                      borderRadius: 10,
                      background: "var(--bg-1)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "0.86rem",
                    }}
                  >
                    <Link href={`/empresas/${e.id}`} className="row-link">
                      {e.razao_social}
                    </Link>
                    <span className="muted" style={{ fontSize: "0.78rem" }}>{e.cnpj}</span>
                  </li>
                ))}
                {resumo.empresas_pendentes.length > 4 ? (
                  <li className="muted" style={{ textAlign: "center", fontSize: "0.82rem" }}>
                    + {resumo.empresas_pendentes.length - 4} outras pendentes
                  </li>
                ) : null}
              </ul>
            </>
          ) : (
            <p className="toast" style={{ fontSize: "0.86rem" }}>
              ✓ Todas as empresas ativas com apuração no mês.
            </p>
          )}
        </>
      )}
    </section>
  );
}
