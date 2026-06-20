"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../lib/api";
import {
  PrevSituacaoFiscal,
  SitfisJob,
  atualizarSituacaoFiscal,
  situacaoFiscalCarteira,
  statusAtualizacaoSituacaoFiscal,
} from "../lib/prevencao";

function fmtBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type Filtro = "todos" | "pendencia" | "debito" | "parcelamento" | "ausencia";

function statusPill(s: string | null) {
  if (s === "regular") return <span className="pill pill-ok">Regular</span>;
  if (s === "pendencias") return <span className="pill pill-err">Irregular / pendência</span>;
  if (s === "verificar") return <span className="pill pill-warn">Verificar</span>;
  return <span className="pill pill-muted">Sem situação</span>;
}

/** Situação fiscal consolidada da carteira — a equipe tria por EXCEÇÃO. */
export function SituacaoFiscalCarteira() {
  const [data, setData] = useState<PrevSituacaoFiscal | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  // Default = já abre nos PROBLEMAS (o que a equipe precisa olhar).
  const [filtro, setFiltro] = useState<Filtro>("pendencia");
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<SitfisJob | null>(null);
  const [iniciando, setIniciando] = useState(false);

  function carregar() {
    situacaoFiscalCarteira()
      .then(setData)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Falha ao carregar a situação fiscal."));
  }

  useEffect(() => { carregar(); }, []);

  // Polling do job de atualização do SITFIS (a cada 5s) enquanto rodando.
  useEffect(() => {
    if (!jobId) return;
    let vivo = true;
    const tick = async () => {
      try {
        const s = await statusAtualizacaoSituacaoFiscal(jobId);
        if (!vivo) return;
        setJob(s);
        if (s.status === "rodando") {
          setTimeout(tick, 5000);
        } else {
          carregar(); // terminou → recarrega o painel já preenchido
        }
      } catch {
        if (vivo) setTimeout(tick, 8000);
      }
    };
    tick();
    return () => { vivo = false; };
  }, [jobId]);

  async function iniciarAtualizacao() {
    const total = data?.totais.empresas ?? 0;
    const ok = window.confirm(
      `Atualizar a situação fiscal de ${total} empresa(s) via Integra Contador?\n\n` +
      `• Custo ~R$ 0,03 por empresa (≈ R$ ${(total * 0.03).toFixed(2)}).\n` +
      `• Roda em segundo plano (~30-60s por empresa) — você pode sair da tela.\n\n` +
      `Continuar?`,
    );
    if (!ok) return;
    setIniciando(true);
    setErro(null);
    try {
      const r = await atualizarSituacaoFiscal();
      setJobId(r.job_id);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao iniciar a atualização.");
    } finally {
      setIniciando(false);
    }
  }

  const rodando = job?.status === "rodando";

  const lista = useMemo(() => {
    if (!data) return [];
    return data.empresas.filter((e) => {
      if (filtro === "pendencia") return e.situacao_fiscal === "pendencias" || e.situacao_fiscal === "verificar";
      if (filtro === "debito") return e.saldo_devedor > 0;
      if (filtro === "parcelamento") return e.tem_parcelamento;
      if (filtro === "ausencia") return e.ausencias.length > 0;
      return true;
    });
  }, [data, filtro]);

  if (erro) return <p className="toast toast-error">{erro}</p>;
  if (!data) return <section className="panel"><p className="muted">Carregando situação fiscal da carteira…</p></section>;

  const t = data.totais;

  return (
    <>
      <header className="page-header" style={{ marginTop: 4, alignItems: "center" }}>
        <div>
          <h3>Situação fiscal da carteira</h3>
          <p className="muted">
            Visão consolidada do e-CAC — olhe só quem tem pendência ou débito, sem abrir empresa por empresa.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={iniciarAtualizacao}
            disabled={iniciando || rodando}
            title="Puxa o SITFIS de todas as empresas via Integra Contador (background)."
          >
            {rodando ? "Atualizando…" : iniciando ? "Iniciando…" : "🔄 Atualizar situação fiscal da carteira"}
          </button>
        </div>
      </header>

      {job ? (
        <section
          className="panel"
          style={{
            marginBottom: 12,
            border: job.status === "erro"
              ? "1px solid rgba(248,113,113,0.5)"
              : job.status === "concluido"
                ? "1px solid rgba(34,197,94,0.4)"
                : "1px solid rgba(59,130,246,0.4)",
          }}
        >
          {job.status === "rodando" ? (
            <>
              <strong>🔄 Atualizando situação fiscal — {job.feitas}/{job.total || "…"}</strong>
              <div style={{ height: 8, borderRadius: 6, background: "var(--bg-1)", margin: "8px 0", overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${job.total ? Math.round((job.feitas / job.total) * 100) : 0}%`,
                  background: "rgb(59,130,246)",
                }} />
              </div>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                {job.sucesso} ok · {job.falhas} falha(s){job.atual ? ` · agora: ${job.atual}` : ""}. Pode sair da tela — roda em segundo plano.
              </p>
            </>
          ) : job.status === "concluido" ? (
            <strong style={{ color: "rgb(16,185,129)" }}>
              ✅ Atualização concluída — {job.sucesso} ok · {job.falhas} falha(s). Painel atualizado.
            </strong>
          ) : (
            <strong style={{ color: "rgb(248,113,113)" }}>⚠️ Falha na atualização: {job.erro_geral || "erro"}</strong>
          )}
        </section>
      ) : null}

      <section className="grid">
        <article className="metric metric--rose">
          <span>Com pendência</span>
          <strong>{t.com_pendencia}</strong>
          <p>{t.regular} regular · {t.a_verificar} verificar · {t.sem_dado} sem dado</p>
        </article>
        <article className="metric metric--amber">
          <span>Saldo devedor (DAS atrasado)</span>
          <strong>{fmtBRL(t.saldo_devedor)}</strong>
          <p>{t.guias_vencidas} guia(s) vencida(s) · {t.empresas_com_debito} empresa(s)</p>
        </article>
        <article className="metric metric--violet">
          <span>Com parcelamento</span>
          <strong>{t.empresas_com_parcelamento}</strong>
          <p>PGFN ativo</p>
        </article>
        <article className="metric metric--emerald">
          <span>Empresas monitoradas</span>
          <strong>{t.empresas}</strong>
          <p>ativas na carteira</p>
        </article>
      </section>

      {data.ausencias.total > 0 ? (
        <section className="panel" style={{ marginTop: 8 }}>
          <div className="page-header" style={{ alignItems: "center" }}>
            <div>
              <h3 style={{ margin: 0 }}>Ausência de declarações</h3>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                {data.ausencias.empresas} empresa(s) · {data.ausencias.total} declaração(ões) faltando (omissão no e-CAC).
              </p>
            </div>
            <button
              type="button"
              className="btn-secondary"
              style={{ padding: "5px 11px", fontSize: "0.82rem" }}
              onClick={() => setFiltro("ausencia")}
            >
              Ver empresas →
            </button>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
            {Object.entries(data.ausencias.por_tipo).map(([tipo, n]) => (
              <span key={tipo} className="pill pill-err" style={{ padding: "6px 12px" }}>
                {tipo}: <strong>{n}</strong>
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel" style={{ marginTop: 8 }}>
        <div className="page-header" style={{ alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Triagem ({lista.length})</h3>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {([
              ["pendencia", "⚠ Com pendência"],
              ["debito", "💰 Com débito"],
              ["ausencia", "📋 Sem declaração"],
              ["parcelamento", "📄 Parcelamento"],
              ["todos", "Todas"],
            ] as [Filtro, string][]).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={filtro === k ? "btn-primary" : "btn-secondary"}
                style={{ padding: "5px 11px", fontSize: "0.82rem" }}
                onClick={() => setFiltro(k)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {lista.length === 0 ? (
          <p className="muted" style={{ marginTop: 12 }}>
            {filtro === "pendencia" ? "🎉 Nenhuma empresa com pendência fiscal." : "Nenhuma empresa neste filtro."}
          </p>
        ) : (
          <div style={{ overflow: "auto", marginTop: 12 }}>
            <table className="data-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Empresa</th>
                  <th>Situação</th>
                  <th>Pendências</th>
                  <th style={{ textAlign: "right" }}>Débito (DAS)</th>
                  <th style={{ textAlign: "center" }}>Vencidas</th>
                  <th style={{ textAlign: "center" }}>Parcel.</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((e) => (
                  <tr key={e.empresa_id}>
                    <td>
                      <Link href={`/empresas/${e.empresa_id}`} className="row-link">{e.razao_social}</Link>
                      <div className="muted" style={{ fontSize: "0.76rem" }}>{e.cnpj}{e.regime ? ` · ${e.regime}` : ""}</div>
                    </td>
                    <td>{statusPill(e.situacao_fiscal)}</td>
                    <td style={{ fontSize: "0.82rem", maxWidth: 320 }}>
                      {e.pendencias.length ? e.pendencias.join(" · ") : <span className="muted">—</span>}
                    </td>
                    <td style={{ textAlign: "right", color: e.saldo_devedor > 0 ? "rgb(248,113,113)" : undefined }}>
                      {e.saldo_devedor > 0 ? fmtBRL(e.saldo_devedor) : <span className="muted">—</span>}
                    </td>
                    <td style={{ textAlign: "center" }}>{e.guias_vencidas || <span className="muted">—</span>}</td>
                    <td style={{ textAlign: "center" }}>{e.tem_parcelamento ? "✅" : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
