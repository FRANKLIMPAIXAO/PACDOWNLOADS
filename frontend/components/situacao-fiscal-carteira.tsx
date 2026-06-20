"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../lib/api";
import { PrevSituacaoFiscal, situacaoFiscalCarteira } from "../lib/prevencao";

function fmtBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type Filtro = "todos" | "pendencia" | "debito" | "parcelamento";

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

  useEffect(() => {
    situacaoFiscalCarteira()
      .then(setData)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Falha ao carregar a situação fiscal."));
  }, []);

  const lista = useMemo(() => {
    if (!data) return [];
    return data.empresas.filter((e) => {
      if (filtro === "pendencia") return e.situacao_fiscal === "pendencias" || e.situacao_fiscal === "verificar";
      if (filtro === "debito") return e.saldo_devedor > 0;
      if (filtro === "parcelamento") return e.tem_parcelamento;
      return true;
    });
  }, [data, filtro]);

  if (erro) return <p className="toast toast-error">{erro}</p>;
  if (!data) return <section className="panel"><p className="muted">Carregando situação fiscal da carteira…</p></section>;

  const t = data.totais;

  return (
    <>
      <header className="page-header" style={{ marginTop: 4 }}>
        <div>
          <h3>Situação fiscal da carteira</h3>
          <p className="muted">
            Visão consolidada do e-CAC — olhe só quem tem pendência ou débito, sem abrir empresa por empresa.
          </p>
        </div>
      </header>

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

      <section className="panel" style={{ marginTop: 8 }}>
        <div className="page-header" style={{ alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Triagem ({lista.length})</h3>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {([
              ["pendencia", "⚠ Com pendência"],
              ["debito", "💰 Com débito"],
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
