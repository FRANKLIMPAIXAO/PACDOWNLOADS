"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { DataTable } from "../../components/data-table";
import { MotorCalculoCard } from "../../components/motor-calculo-card";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import {
  Apuracao,
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
  transmitir,
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

  async function handleTransmitir(id: number) {
    setBusy(`t-${id}`); setError(null);
    try { await transmitir(id); await reload(); }
    catch (err) { if (err instanceof ApiError) setError(err.message); }
    finally { setBusy(null); }
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
        onTransmitir={handleTransmitir}
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
          <button type="button" className="btn-primary" onClick={() => setShowNova((v) => !v)}>
            {showNova ? "Fechar" : "+ Nova apuração"}
          </button>
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      {showNova ? (
        <NovaApuracaoForm
          anoMes={anoMes}
          empresas={empresas}
          onCreated={async () => { setShowNova(false); await reload(); }}
          onCalcularAutomatico={async () => { setShowNova(false); await reload(); }}
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
  onTransmitir, onGerarDas, onPagar, onAbrirPdf,
}: {
  apuracao: Apuracao; busy: string | null;
  onTransmitir: (id: number) => void;
  onGerarDas: (id: number) => void;
  onPagar: (id: number) => void;
  onAbrirPdf: (id: number, am: string) => void;
}) {
  const id = apuracao.id;
  if (apuracao.status === "DRAFT") {
    return (
      <button
        type="button" className="btn-primary"
        style={{ padding: "5px 11px", fontSize: "0.82rem" }}
        onClick={() => onTransmitir(id)} disabled={busy === `t-${id}`}
      >
        {busy === `t-${id}` ? "..." : "Transmitir"}
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
  onCalcularAutomatico: () => void;
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
