"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ProtectedRoute } from "../../../components/protected-route";
import { ApiError } from "../../../lib/api";
import {
  LoteItem,
  calcularLote,
  previousAnoMes,
} from "../../../lib/apuracoes";
import { Empresa, listarEmpresas } from "../../../lib/empresas";

const CHUNK = 10; // empresas por requisição (cabe no timeout do Traefik)

function fmtBRL(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function ehSimples(e: Empresa): boolean {
  const r = (e.regime_tributario || "").toLowerCase();
  return r.includes("simples") || r === "sn";
}

export default function FechamentoLotePage() {
  return (
    <ProtectedRoute>
      <FechamentoLoteContent />
    </ProtectedRoute>
  );
}

function FechamentoLoteContent() {
  const [anoMes, setAnoMes] = useState(previousAnoMes());
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [resultados, setResultados] = useState<LoteItem[]>([]);
  const [processando, setProcessando] = useState(false);
  const [progresso, setProgresso] = useState({ feito: 0, total: 0 });
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setEmpresas(await listarEmpresas());
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar empresas.");
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  const empresasSN = useMemo(
    () => empresas.filter((e) => e.ativo && ehSimples(e)),
    [empresas],
  );

  async function fecharCompetencia() {
    setErro(null);
    setResultados([]);
    const ids = empresasSN.map((e) => e.id);
    if (ids.length === 0) { setErro("Nenhuma empresa Simples Nacional ativa."); return; }
    setProcessando(true);
    setProgresso({ feito: 0, total: ids.length });
    const nomePorId = new Map(empresasSN.map((e) => [e.id, e.razao_social]));
    const acc: LoteItem[] = [];
    for (let i = 0; i < ids.length; i += CHUNK) {
      const bloco = ids.slice(i, i + CHUNK);
      try {
        const r = await calcularLote(anoMes, bloco);
        acc.push(...r.resultados);
      } catch (e) {
        // Bloco inteiro caiu — registra cada empresa como erro e segue
        acc.push(...bloco.map((id) => ({
          empresa_id: id,
          razao_social: nomePorId.get(id) || `#${id}`,
          ok: false,
          avisos: [],
          erro: e instanceof ApiError ? e.message : "Falha no bloco",
        })));
      }
      setResultados([...acc]);
      setProgresso({ feito: Math.min(i + CHUNK, ids.length), total: ids.length });
    }
    setProcessando(false);
  }

  const tot = useMemo(() => {
    const ok = resultados.filter((r) => r.ok);
    const totalDas = ok.reduce((s, r) => s + (Number(r.valor_devido) || 0), 0);
    const totalReceita = ok.reduce((s, r) => s + (Number(r.receita_bruta) || 0), 0);
    return {
      processadas: resultados.length,
      comReceita: ok.filter((r) => (Number(r.receita_bruta) || 0) > 0).length,
      semNotas: ok.filter((r) => (Number(r.receita_bruta) || 0) === 0).length,
      comAviso: ok.filter((r) => r.avisos.length > 0).length,
      erros: resultados.filter((r) => !r.ok).length,
      totalDas,
      totalReceita,
    };
  }, [resultados]);

  const pct = progresso.total ? Math.round((progresso.feito / progresso.total) * 100) : 0;

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Fechamento mensal em lote</h1>
          <p className="muted">
            Calcula a apuração (receita + DAS) de TODAS as empresas Simples Nacional
            de uma vez. Revise os avisos antes de transmitir.
          </p>
        </div>
        <div className="page-actions" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Link href="/apuracoes" className="btn-ghost">← Apurações</Link>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="muted" style={{ fontSize: "0.82rem" }}>Competência</span>
            <input
              type="month"
              value={`${anoMes.slice(0, 4)}-${anoMes.slice(4)}`}
              onChange={(e) => { if (e.target.value) setAnoMes(e.target.value.replace("-", "")); }}
              disabled={processando}
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            onClick={fecharCompetencia}
            disabled={processando || empresasSN.length === 0}
          >
            {processando
              ? `Calculando ${progresso.feito}/${progresso.total}...`
              : `▶ Fechar ${empresasSN.length} empresas`}
          </button>
        </div>
      </header>

      {erro ? <p className="toast toast-error">{erro}</p> : null}

      {processando ? (
        <div style={{ margin: "8px 0" }}>
          <div style={{ height: 8, background: "rgba(255,255,255,0.08)", borderRadius: 999, overflow: "hidden" }}>
            <div style={{ width: `${pct}%`, height: "100%", background: "rgb(34,197,94)", transition: "width .3s" }} />
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            {progresso.feito} de {progresso.total} empresas · {pct}%
          </p>
        </div>
      ) : null}

      {resultados.length > 0 ? (
        <section className="grid" style={{ marginTop: 8 }}>
          <article className="metric metric--cyan">
            <span>Processadas</span><strong>{tot.processadas}</strong>
            <p>{tot.comReceita} com receita · {tot.semNotas} sem notas</p>
          </article>
          <article className="metric metric--emerald">
            <span>DAS total</span><strong>{fmtBRL(tot.totalDas)}</strong>
            <p>receita {fmtBRL(tot.totalReceita)}</p>
          </article>
          <article className="metric metric--amber">
            <span>Com aviso</span><strong>{tot.comAviso}</strong>
            <p>revisar antes de transmitir</p>
          </article>
          <article className={tot.erros > 0 ? "metric metric--rose" : "metric metric--violet"}>
            <span>Erros</span><strong>{tot.erros}</strong>
            <p>{tot.erros > 0 ? "ver coluna observação" : "nenhum"}</p>
          </article>
        </section>
      ) : (
        <section className="panel" style={{ marginTop: 8 }}>
          <p className="muted">
            {empresasSN.length} empresa(s) Simples Nacional ativa(s) pronta(s).
            Escolha a competência e clique em <strong>Fechar</strong> — o sistema
            lê as NFes de cada uma, classifica e calcula o DAS.
          </p>
        </section>
      )}

      {resultados.length > 0 ? (
        <div style={{ overflow: "auto", border: "1px solid var(--border)", borderRadius: 12, marginTop: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.86rem" }}>
            <thead style={{ position: "sticky", top: 0, background: "var(--surface-strong)" }}>
              <tr>
                <th style={th}>Empresa</th>
                <th style={th}>Notas</th>
                <th style={th}>Receita bruta</th>
                <th style={th}>Anexo·Faixa</th>
                <th style={th}>Alíq.</th>
                <th style={th}>DAS</th>
                <th style={th}>Observação</th>
              </tr>
            </thead>
            <tbody>
              {resultados.map((r) => (
                <tr key={r.empresa_id} style={{ borderTop: "1px solid var(--border)", background: !r.ok ? "rgba(248,113,113,0.06)" : undefined }}>
                  <td style={td}>
                    <Link href={`/empresas/${r.empresa_id}`} className="row-link">{r.razao_social}</Link>
                  </td>
                  <td style={td}>{r.ok ? `${r.saidas ?? 0}/${r.total_docs ?? 0}` : "—"}</td>
                  <td style={td}>{r.ok ? fmtBRL(r.receita_bruta) : "—"}</td>
                  <td style={td}>{r.ok && r.faixa ? `${r.anexo} · ${r.faixa}` : "—"}</td>
                  <td style={td}>{r.ok && r.aliquota_efetiva ? `${Number(r.aliquota_efetiva).toFixed(2)}%` : "—"}</td>
                  <td style={td}><strong>{r.ok ? fmtBRL(r.valor_devido) : "—"}</strong></td>
                  <td style={td}>
                    {!r.ok ? (
                      <span className="pill pill-err" title={r.erro || ""}>Erro: {r.erro}</span>
                    ) : r.primeira_apuracao ? (
                      <span className="pill pill-warn" title="RBT12=0: usa estimativa receita×12. Preencha os 12 meses se a empresa não for nova.">1ª apuração (RBT12=0)</span>
                    ) : r.avisos.length > 0 ? (
                      <span className="pill pill-warn" title={r.avisos.join(" | ")}>⚠ {r.avisos.length} aviso(s)</span>
                    ) : (
                      <span className="pill pill-ok">OK</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {resultados.length > 0 && !processando ? (
        <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          As apurações foram salvas como rascunho. Vá em <Link href="/apuracoes" className="row-link">Apurações</Link> pra
          validar (dry-run) e transmitir cada uma. Empresas "1ª apuração" sem histórico
          de 12 meses podem ter o RBT12 preenchido na tela da empresa.
        </p>
      ) : null}
    </main>
  );
}

const th: React.CSSProperties = {
  padding: "8px 10px", textAlign: "left", fontSize: "0.72rem", color: "var(--muted)",
  fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em",
  borderBottom: "1px solid var(--border)",
};
const td: React.CSSProperties = { padding: "8px 10px" };
