"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { DataTable } from "../../components/data-table";
import { MotorCalculoCard } from "../../components/motor-calculo-card";
import { ProtectedRoute } from "../../components/protected-route";
import { Rbt12Card } from "../../components/rbt12-card";
import { ApiError } from "../../lib/api";
import {
  Apuracao,
  ResultadoTransmissao,
  ResumoMes,
  ResumoMotor,
  abrirDasPdf,
  calcularESalvar,
  calcularPreview,
  criarApuracao,
  currentAnoMes,
  formatAnoMes,
  gerarDas,
  listarApuracoes,
  marcarPago,
  obterResumoMes,
  previousAnoMes,
  statusLabel,
  statusPillClass,
  transmitirComPolling,
} from "../../lib/apuracoes";
import { Empresa, listarEmpresas } from "../../lib/empresas";

function fmtBRL(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function ApuracoesPage() {
  return (
    <ProtectedRoute>
      <ApuracoesContent />
    </ProtectedRoute>
  );
}

function ApuracoesContent() {
  const [anoMes, setAnoMes] = useState<string>(previousAnoMes());
  const [resumo, setResumo] = useState<ResumoMes | null>(null);
  const [apuracoes, setApuracoes] = useState<Apuracao[] | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showNova, setShowNova] = useState(false);
  // Resultado do dry-run (validação) — mostra comparação RFB × PAC antes de transmitir
  const [dryRun, setDryRun] = useState<ResultadoTransmissao | null>(null);
  // true enquanto o dry-run roda (mostra indicador no topo, sobretudo no auto pós-apuração)
  const [validando, setValidando] = useState(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [r, a, e] = await Promise.all([
        obterResumoMes(anoMes),
        listarApuracoes({ anoMes }),
        listarEmpresas(),
      ]);
      setResumo(r); setApuracoes(a); setEmpresas(e);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao carregar.");
    }
  }, [anoMes]);

  useEffect(() => { reload(); }, [reload]);

  // PASSO 1: dry-run — RFB calcula sem entregar, mostra comparação RFB × PAC
  async function handleValidar(id: number) {
    setBusy(`t-${id}`); setError(null); setDryRun(null); setValidando(true);
    try {
      const r = await transmitirComPolling(id, true); // dry-run em background + polling
      setDryRun(r);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao validar declaração.");
    } finally {
      setBusy(null); setValidando(false);
      // O banner/erro renderiza no TOPO (acima da tabela) — sobe pra ele ficar
      // visível, senão parece que "nada aconteceu" quando se clica numa linha lá embaixo.
      if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  // PASSO 2: transmissão REAL — só após confirmar a comparação
  async function handleTransmitirReal(id: number) {
    const ok = confirm(
      "⚠️ TRANSMITIR DE VERDADE pra Receita Federal?\n\n" +
      "Isso entrega a declaração PGDAS-D oficialmente (gera recibo). " +
      "Confirme que o valor apurado pela RFB no dry-run está correto antes de prosseguir.\n\n" +
      "Continuar?",
    );
    if (!ok) return;
    setBusy(`t-${id}`); setError(null);
    try {
      await transmitirComPolling(id, false); // real, em background + polling
      setDryRun(null);
      await reload();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao transmitir.");
    } finally { setBusy(null); }
  }

  async function handleGerarDas(id: number) {
    setBusy(`d-${id}`); setError(null);
    try { await gerarDas(id); await reload(); }
    catch (err) { if (err instanceof ApiError) setError(err.message); }
    finally { setBusy(null); }
  }

  async function handlePagar(id: number) {
    setBusy(`p-${id}`); setError(null);
    try { await marcarPago(id); await reload(); }
    catch (err) { if (err instanceof ApiError) setError(err.message); }
    finally { setBusy(null); }
  }

  async function handleAbrirPdf(id: number, am: string) {
    setBusy(`pdf-${id}`); setError(null);
    try { await abrirDasPdf(id, am); }
    catch (err) { setError(err instanceof Error ? err.message : "Falha ao abrir."); }
    finally { setBusy(null); }
  }

  const empresaPorId = useMemo(() => {
    const m = new Map<number, Empresa>();
    for (const e of empresas) m.set(e.id, e);
    return m;
  }, [empresas]);

  const linhas: ReactNode[][] = useMemo(() => {
    return (apuracoes ?? []).map((a) => [
      <Link key={`emp-${a.id}`} href={`/empresas/${a.empresa_id}`} className="row-link">
        {empresaPorId.get(a.empresa_id)?.razao_social || `#${a.empresa_id}`}
      </Link>,
      a.regime.replace(/_/g, " "),
      <span key={`s-${a.id}`} className={statusPillClass(a.status)}>{statusLabel(a.status)}</span>,
      fmtBRL(a.receita_bruta),
      fmtBRL(a.valor_devido),
      a.das_data_vencimento || "—",
      <ApuracaoActions
        key={`act-${a.id}`}
        apuracao={a}
        busy={busy}
        onValidar={handleValidar}
        onGerarDas={handleGerarDas}
        onPagar={handlePagar}
        onAbrirPdf={handleAbrirPdf}
      />,
    ]);
  }, [apuracoes, empresaPorId, busy]);

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Apurações Mensais</h2>
          <p className="muted">
            PGDAS-D Simples Nacional · transmissão, geração de DAS e controle de pagamentos.
          </p>
        </div>
        <div className="page-actions">
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="muted" style={{ fontSize: "0.82rem" }}>Competência</span>
            <input
              type="month"
              value={`${anoMes.slice(0, 4)}-${anoMes.slice(4)}`}
              onChange={(e) => {
                const v = e.target.value; // YYYY-MM
                if (!v) return;
                setAnoMes(v.replace("-", ""));
              }}
            />
          </label>
          <Link href="/apuracoes/lote" className="btn-secondary" style={{ textDecoration: "none" }}>
            ▶ Fechar em lote
          </Link>
          <button type="button" className="btn-primary" onClick={() => setShowNova((v) => !v)}>
            {showNova ? "Fechar" : "+ Nova apuração"}
          </button>
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      {/* Enquanto o dry-run roda (sobretudo o automático logo após apurar) */}
      {validando && !dryRun ? (
        <section
          className="panel"
          style={{ border: "1px solid rgba(59,130,246,0.4)", marginBottom: 16 }}
        >
          <h3 style={{ margin: 0 }}>🔍 Validando na Receita (dry-run)…</h3>
          <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
            A Receita está recalculando a declaração pra comparar com o PAC. Não
            transmite nada — só valida. Leva alguns segundos.
          </p>
        </section>
      ) : null}

      {/* Banner de comparação do dry-run (RFB × PAC) — passo antes de transmitir real */}
      {dryRun ? (
        <section
          className="panel"
          style={{
            border: dryRun.valor_devido_rfb !== null && dryRun.divergencia !== null && Math.abs(dryRun.divergencia) <= 0.01
              ? "1px solid rgba(34,197,94,0.4)"
              : "1px solid rgba(245,158,11,0.4)",
            marginBottom: 16,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <div>
              <h3 style={{ margin: 0 }}>
                🔍 Dry-run da declaração (RFB calculou, NÃO transmitiu)
              </h3>
              <p className="muted" style={{ margin: "6px 0", fontSize: 13 }}>
                A Receita validou o payload e devolveu o valor apurado.
                Compare com o cálculo do PAC antes de transmitir de verdade.
              </p>
              <div style={{ display: "flex", gap: 24, marginTop: 8, flexWrap: "wrap" }}>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Valor RFB (dry-run)</div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: "rgb(59,130,246)" }}>
                    {fmtBRL(dryRun.valor_devido_rfb)}
                  </div>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Valor calculado pelo PAC</div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: "rgb(148,163,184)" }}>
                    {fmtBRL(dryRun.valor_devido_pac)}
                  </div>
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>Divergência</div>
                  <div style={{
                    fontSize: 20, fontWeight: 600,
                    color: dryRun.valor_devido_rfb !== null && dryRun.divergencia !== null && Math.abs(dryRun.divergencia) <= 0.01
                      ? "rgb(34,197,94)" : "rgb(245,158,11)",
                  }}>
                    {dryRun.divergencia === null ? "—" : fmtBRL(dryRun.divergencia)}
                  </div>
                </div>
              </div>
              {dryRun.valor_devido_rfb === null || dryRun.divergencia === null ? (
                <p className="toast toast-warn" style={{ marginTop: 10, fontSize: 13 }}>
                  ⚠️ A RFB validou o payload (sem erro), mas NÃO retornou o valor apurado
                  pra comparar. Não dá pra afirmar que bate — confira o valor do PAC
                  manualmente antes de transmitir.
                </p>
              ) : Math.abs(dryRun.divergencia) > 0.01 ? (
                Math.abs(dryRun.divergencia) / Math.abs(dryRun.valor_devido_rfb || 1) < 0.05 ? (
                  <p className="toast toast-warn" style={{ marginTop: 10, fontSize: 13 }}>
                    ⚠️ Pequena diferença ({fmtBRL(dryRun.divergencia)}). Provável causa:
                    RBT12 (faturamento dos últimos 12 meses) incompleto ou arredondamento —
                    confira o histórico de receita dessa empresa. NÃO é monofásico/ST.
                  </p>
                ) : (
                  <p className="toast toast-warn" style={{ marginTop: 10, fontSize: 13 }}>
                    ⚠️ Diferença grande. Provável causa: receita monofásica/ST não está
                    sendo segregada no payload (a RFB taxou PIS/COFINS sobre o monofásico).
                    NÃO transmita até ajustar — revise manualmente.
                  </p>
                )
              ) : (
                <p className="toast toast-ok" style={{ marginTop: 10, fontSize: 13 }}>
                  ✅ Valores batem. Pode transmitir com segurança.
                </p>
              )}
              {dryRun.avisos && dryRun.avisos.length > 0 ? (
                <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                  {dryRun.avisos.map((a, i) => (
                    <p key={i} className="toast toast-error" style={{ fontSize: 13 }}>
                      🏢 {a}
                    </p>
                  ))}
                </div>
              ) : null}
              <details style={{ marginTop: 10 }}>
                <summary className="muted" style={{ fontSize: 12, cursor: "pointer" }}>Ver resposta da Receita (raw)</summary>
                <pre style={{ fontSize: 11, maxHeight: 220, overflow: "auto", background: "var(--bg-1)", padding: 8, borderRadius: 6, marginTop: 6, whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(dryRun.raw, null, 2)}
                </pre>
              </details>
            </div>
            <button type="button" className="btn-ghost" onClick={() => setDryRun(null)}>✕</button>
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
            <button type="button" className="btn-ghost" onClick={() => setDryRun(null)}>
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => handleTransmitirReal(dryRun.apuracao_id)}
              disabled={busy === `t-${dryRun.apuracao_id}`}
              style={{
                background: dryRun.divergencia && Math.abs(dryRun.divergencia) > 0.01
                  ? "rgb(245,158,11)" : undefined,
              }}
            >
              {busy === `t-${dryRun.apuracao_id}`
                ? "Transmitindo..."
                : "▶ Transmitir de verdade pra Receita"}
            </button>
          </div>
        </section>
      ) : null}

      {showNova ? (
        <NovaApuracaoForm
          anoMes={anoMes}
          empresas={empresas}
          onCreated={async () => { setShowNova(false); await reload(); }}
          onCalcularAutomatico={async (apuracaoId: number) => {
            setShowNova(false);
            await reload();
            // Dry-run automático logo após apurar: a Receita recalcula e o banner
            // RFB × PAC aparece no topo, sem o usuário ter que clicar "Validar" de novo.
            await handleValidar(apuracaoId);
          }}
        />
      ) : null}

      {resumo ? (
        <section className="grid">
          <article className="metric metric--cyan">
            <span>Empresas ativas</span>
            <strong>{resumo.total_empresas_ativas}</strong>
            <p>cadastradas no sistema</p>
          </article>
          <article className="metric metric--violet">
            <span>Apurações</span>
            <strong>{resumo.apuracoes_geradas}</strong>
            <p>{resumo.pendentes} pendentes</p>
          </article>
          <article className="metric metric--emerald">
            <span>DAS gerados</span>
            <strong>{resumo.das_gerados}</strong>
            <p>{resumo.pagos} pagos</p>
          </article>
          <article className="metric metric--amber">
            <span>Valor devido</span>
            <strong>{fmtBRL(resumo.valor_devido_total)}</strong>
            <p>{fmtBRL(resumo.valor_pago)} pago</p>
          </article>
        </section>
      ) : null}

      <header className="page-header" style={{ marginTop: 8 }}>
        <div>
          <h3>Competência {formatAnoMes(anoMes)}</h3>
          <p className="muted">
            {(apuracoes?.length ?? 0)} apuração(es) · {resumo?.pendentes ?? 0} empresa(s) pendente(s)
          </p>
        </div>
      </header>

      {apuracoes === null ? (
        <section className="panel"><p className="muted">Carregando...</p></section>
      ) : apuracoes.length === 0 ? (
        <section className="panel">
          <div className="empty-state">
            Nenhuma apuração para esta competência. Clique em <strong>+ Nova apuração</strong> para começar.
          </div>
        </section>
      ) : (
        <DataTable
          headers={["Empresa", "Regime", "Status", "Receita bruta", "Valor devido", "Vencto", "Ações"]}
          rows={linhas}
        />
      )}

      {resumo && resumo.empresas_pendentes.length > 0 ? (
        <section className="panel info-card">
          <h3>Empresas pendentes</h3>
          <p className="muted">Sem apuração para {formatAnoMes(anoMes)}.</p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
            {resumo.empresas_pendentes.map((e) => (
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
                }}
              >
                <span>
                  <Link href={`/empresas/${e.id}`} className="row-link">
                    {e.razao_social}
                  </Link>
                  {" "}<span className="muted" style={{ fontSize: "0.85rem" }}>· {e.cnpj}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function ApuracaoActions({
  apuracao, busy,
  onValidar, onGerarDas, onPagar, onAbrirPdf,
}: {
  apuracao: Apuracao; busy: string | null;
  onValidar: (id: number) => void;
  onGerarDas: (id: number) => void;
  onPagar: (id: number) => void;
  onAbrirPdf: (id: number, am: string) => void;
}) {
  const id = apuracao.id;
  if (apuracao.status === "DRAFT") {
    return (
      <button
        type="button" className="btn-secondary"
        style={{ padding: "5px 11px", fontSize: "0.82rem" }}
        onClick={() => onValidar(id)} disabled={busy === `t-${id}`}
        title="Dry-run: a RFB calcula sem entregar. Mostra comparação antes de transmitir."
      >
        {busy === `t-${id}` ? "⏳ Validando..." : "🔍 Validar (dry-run)"}
      </button>
    );
  }
  if (apuracao.status === "TRANSMITIDA") {
    return (
      <button
        type="button" className="btn-primary"
        style={{ padding: "5px 11px", fontSize: "0.82rem" }}
        onClick={() => onGerarDas(id)} disabled={busy === `d-${id}`}
      >
        {busy === `d-${id}` ? "..." : "Gerar DAS"}
      </button>
    );
  }
  if (apuracao.status === "DAS_GERADO") {
    return (
      <span style={{ display: "inline-flex", gap: 6 }}>
        <button
          type="button" className="btn-secondary"
          style={{ padding: "5px 10px", fontSize: "0.82rem" }}
          onClick={() => onAbrirPdf(id, apuracao.ano_mes)} disabled={busy === `pdf-${id}`}
        >
          {busy === `pdf-${id}` ? "..." : "PDF"}
        </button>
        <button
          type="button" className="btn-primary"
          style={{ padding: "5px 10px", fontSize: "0.82rem" }}
          onClick={() => onPagar(id)} disabled={busy === `p-${id}`}
        >
          {busy === `p-${id}` ? "..." : "Marcar pago"}
        </button>
      </span>
    );
  }
  if (apuracao.status === "PAGO") {
    return (
      <button
        type="button" className="btn-secondary"
        style={{ padding: "5px 11px", fontSize: "0.82rem" }}
        onClick={() => onAbrirPdf(id, apuracao.ano_mes)} disabled={busy === `pdf-${id}`}
      >
        Baixar PDF
      </button>
    );
  }
  return <span className="muted">—</span>;
}

function NovaApuracaoForm({
  anoMes, empresas, onCreated, onCalcularAutomatico,
}: {
  anoMes: string;
  empresas: Empresa[];
  onCreated: () => void;
  onCalcularAutomatico: (apuracaoId: number) => void;
}) {
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [receita, setReceita] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [modo, setModo] = useState<"auto" | "manual">("auto");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!empresaId) { setErr("Selecione uma empresa."); return; }
    const valor = Number(receita.replace(",", "."));
    if (!Number.isFinite(valor) || valor <= 0) { setErr("Receita bruta inválida."); return; }
    setSaving(true);
    try {
      await criarApuracao({
        empresa_id: empresaId, ano_mes: anoMes, receita_bruta: valor,
      });
      onCreated();
    } catch (e) {
      if (e instanceof ApiError) setErr(e.message);
      else setErr("Falha ao criar apuração.");
    } finally { setSaving(false); }
  }

  return (
    <>
      <section className="panel form-card">
        <h3>Nova apuração — {formatAnoMes(anoMes)}</h3>
        <p className="muted">
          Modo <strong>automático</strong>: o sistema lê NFes recebidas/emitidas, classifica
          CFOPs item-a-item, identifica monofásicos e ST, calcula RBT12 e aplica a tabela do
          Anexo. Modo <strong>manual</strong>: você informa a receita bruta direto.
        </p>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            className={modo === "auto" ? "btn-primary" : "btn-secondary"}
            onClick={() => setModo("auto")}
          >
            Automático (motor)
          </button>
          <button
            type="button"
            className={modo === "manual" ? "btn-primary" : "btn-secondary"}
            onClick={() => setModo("manual")}
          >
            Manual
          </button>
        </div>

        <div className="form-grid">
          <label>
            <span>Empresa</span>
            <select value={empresaId} onChange={(e) => setEmpresaId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Selecione</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} ({e.regime_tributario || "—"})
                </option>
              ))}
            </select>
          </label>
          {modo === "manual" ? (
            <label>
              <span>Receita bruta do mês (R$)</span>
              <input
                type="text"
                inputMode="decimal"
                placeholder="0,00"
                value={receita}
                onChange={(e) => setReceita(e.target.value)}
              />
            </label>
          ) : null}
        </div>

        {err ? <p className="toast toast-error">{err}</p> : null}

        {modo === "manual" ? (
          <div className="form-actions">
            <button type="button" className="btn-primary" disabled={saving} onClick={handleSubmit as any}>
              {saving ? "Salvando..." : "Criar rascunho manual"}
            </button>
          </div>
        ) : null}
      </section>

      {empresaId ? (
        <Rbt12Card empresaId={empresaId as number} anoMes={anoMes} />
      ) : null}

      {modo === "auto" && empresaId ? (
        <MotorCalculoCard
          empresaId={empresaId as number}
          anoMes={anoMes}
          onSalvar={onCalcularAutomatico}
        />
      ) : null}
    </>
  );
}
