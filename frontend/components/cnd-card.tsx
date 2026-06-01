"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import {
  Certidao,
  CertidaoCreate,
  TIPOS_CND,
  TipoCertidao,
  TipoCndRenovavel,
  criarCnd,
  listarCnds,
  removerCnd,
  renovarCndAutomatica,
  statusLabel,
  statusPillClass,
  uploadCndPdf,
} from "../lib/cnds";

type Props = { empresaId: number };

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoIn(months: number): string {
  const d = new Date();
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}

export function CndCard({ empresaId }: Props) {
  const [certs, setCerts] = useState<Certidao[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      setCerts(await listarCnds(empresaId));
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }, [empresaId]);

  useEffect(() => { reload(); }, [reload]);

  // mostra a CND mais recente de cada tipo
  const porTipo = new Map<TipoCertidao, Certidao>();
  for (const c of certs ?? []) {
    const existente = porTipo.get(c.tipo);
    if (!existente || new Date(c.data_validade) > new Date(existente.data_validade)) {
      porTipo.set(c.tipo, c);
    }
  }

  async function handleRemover(id: number) {
    if (!confirm("Remover esta certidao?")) return;
    setBusy(`del-${id}`);
    try {
      await removerCnd(id);
      await reload();
    } finally {
      setBusy(null);
    }
  }

  async function handleUpload(certId: number, file: File) {
    setBusy(`up-${certId}`);
    try {
      await uploadCndPdf(certId, file);
      await reload();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleRenovar(tipo: TipoCndRenovavel) {
    setBusy(`renov-${tipo}`);
    setError(null);
    try {
      await renovarCndAutomatica(empresaId, tipo);
      await reload();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao renovar.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Controle de Regularidade Fiscal</h3>
        <div className="page-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancelar" : "+ Nova certidao"}
          </button>
        </div>
      </header>

      <p className="muted" style={{ margin: 0, fontSize: "0.86rem" }}>
        <strong>Federal RFB+PGFN</strong> via Integra Contador (SITFIS interno){" "}
        + emissão da CND oficial sob demanda (licitação/banco).{" "}
        <strong>Trabalhista (CNDT)</strong> e <strong>FGTS (CRF)</strong>:{" "}
        scrapers pendentes — anexar PDF manualmente até implementação.
      </p>

      <div className="cnd-grid">
        {/* Tile unificado FEDERAL (SITFIS + CND oficial) */}
        <FederalUnificadoTile
          empresaId={empresaId}
          sitfis={porTipo.get("FEDERAL") || null}
          oficial={porTipo.get("FEDERAL_OFICIAL") || null}
          busy={busy}
          onRenovar={handleRenovar}
        />

        {/* FGTS + TRABALHISTA + ESTADUAL + MUNICIPAL */}
        {TIPOS_CND
          .filter((t) => !t.sob_demanda && t.tipo !== "FEDERAL")
          .map((t) => {
            const cert = porTipo.get(t.tipo);
            const fonteLabel = (
              <small style={{ color: "var(--muted)", fontSize: "0.7rem" }}>
                {t.fonte}
              </small>
            );

            if (!cert) {
              return (
                <div key={t.tipo} className="cnd-tile cnd-tile--miss">
                  <dt>{t.label}</dt>
                  <strong>—</strong>
                  <small>Nao cadastrada</small>
                  {fonteLabel}
                </div>
              );
            }
            const cls =
              cert.status === "VALIDA" ? "cnd-tile--ok"
              : cert.status === "A_VENCER" ? "cnd-tile--warn"
              : cert.status === "VENCIDA" ? "cnd-tile--err"
              : "";
            return (
              <div key={t.tipo} className={`cnd-tile ${cls}`}>
                <dt>{t.label}</dt>
                <strong>{statusLabel(cert.status)}</strong>
                <small>
                  Vence {cert.data_validade}
                  {cert.dias_para_vencer !== null
                    ? cert.dias_para_vencer < 0
                      ? ` · ha ${Math.abs(cert.dias_para_vencer)}d`
                      : ` · em ${cert.dias_para_vencer}d`
                    : ""}
                </small>
                {fonteLabel}
              </div>
            );
          })}
      </div>

      {showForm ? (
        <NovaCndForm
          empresaId={empresaId}
          onCreated={async () => { setShowForm(false); await reload(); }}
        />
      ) : null}

      {certs && certs.length > 0 ? (
        <>
          <p className="section-divider">Historico</p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {certs.map((c) => (
              <li
                key={c.id}
                style={{
                  padding: "10px 14px",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  background: "var(--bg-1)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <strong>
                    {TIPOS_CND.find((t) => t.tipo === c.tipo)?.label}{" "}
                    <span className={statusPillClass(c.status)} style={{ marginLeft: 8 }}>
                      {statusLabel(c.status)}
                    </span>
                  </strong>
                  <small className="muted">
                    {c.numero ? `Nº ${c.numero} · ` : ""}
                    Emissao {c.data_emissao || "—"} · Validade {c.data_validade}
                  </small>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <label className="btn-secondary" style={{ padding: "5px 10px", fontSize: "0.8rem", cursor: "pointer" }}>
                    {c.pdf_path ? "Trocar PDF" : "Anexar PDF"}
                    <input
                      type="file"
                      accept=".pdf"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleUpload(c.id, f);
                      }}
                      disabled={busy === `up-${c.id}`}
                    />
                  </label>
                  {c.pdf_path ? (
                    <a
                      href="#"
                      onClick={async (e) => {
                        e.preventDefault();
                        const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
                        const token = localStorage.getItem("pac_xml_token");
                        const r = await fetch(`${base}/api/v1/cnds/${c.id}/pdf`, {
                          headers: token ? { Authorization: `Bearer ${token}` } : {},
                        });
                        if (!r.ok) return;
                        const blob = await r.blob();
                        window.open(URL.createObjectURL(blob), "_blank");
                      }}
                      className="btn-secondary"
                      style={{ padding: "5px 10px", fontSize: "0.8rem" }}
                    >
                      Abrir
                    </a>
                  ) : null}
                  <button
                    type="button"
                    className="btn-danger"
                    style={{ padding: "5px 10px", fontSize: "0.8rem" }}
                    onClick={() => handleRemover(c.id)}
                    disabled={busy === `del-${c.id}`}
                  >
                    Remover
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {error ? <p className="toast toast-error">{error}</p> : null}
    </section>
  );
}

function NovaCndForm({
  empresaId,
  onCreated,
}: {
  empresaId: number;
  onCreated: () => void;
}) {
  const [tipo, setTipo] = useState<TipoCertidao>("FEDERAL");
  const [numero, setNumero] = useState("");
  const [emissao, setEmissao] = useState(isoToday());
  const [validade, setValidade] = useState(isoIn(6));
  const [obs, setObs] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const payload: CertidaoCreate = {
      tipo,
      numero: numero || undefined,
      data_emissao: emissao || undefined,
      data_validade: validade,
      observacoes: obs || undefined,
    };
    try {
      await criarCnd(empresaId, payload);
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) setErr(err.message);
      else setErr("Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form-stack" style={{ marginTop: 8 }}>
      <p className="section-divider">Nova certidao</p>
      <div className="form-grid">
        <label>
          <span>Tipo</span>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoCertidao)}>
            {TIPOS_CND.map((t) => (
              <option key={t.tipo} value={t.tipo}>{t.full}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Numero (opcional)</span>
          <input value={numero} onChange={(e) => setNumero(e.target.value)} />
        </label>
        <label>
          <span>Data emissao</span>
          <input type="date" value={emissao} onChange={(e) => setEmissao(e.target.value)} />
        </label>
        <label>
          <span>Data validade</span>
          <input type="date" value={validade} onChange={(e) => setValidade(e.target.value)} required />
        </label>
        <label style={{ gridColumn: "1 / -1" }}>
          <span>Observacoes</span>
          <input value={obs} onChange={(e) => setObs(e.target.value)} />
        </label>
      </div>
      {err ? <p className="toast toast-error">{err}</p> : null}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Salvando..." : "Salvar certidao"}
        </button>
      </div>
    </form>
  );
}

/**
 * Tile unificado para a regularidade Federal RFB+PGFN.
 *
 * - SITFIS (Integra Contador): relatório interno de pendências fiscais (60d).
 * - CND Conjunta RFB+PGFN: documento entregável a banco/licitação (180d).
 *
 * Ambos vêm da mesma base (RFB + PGFN), então faz sentido visualizar juntos:
 * o SITFIS dá o "termômetro" interno e o botão "Emitir CND oficial" gera o
 * documento quando o cliente precisa entregar.
 */
function FederalUnificadoTile({
  empresaId,
  sitfis,
  oficial,
  busy,
  onRenovar,
}: {
  empresaId: number;
  sitfis: Certidao | null;
  oficial: Certidao | null;
  busy: string | null;
  onRenovar: (tipo: TipoCndRenovavel) => Promise<void>;
}) {
  const sitfisBusy = busy === `renov-FEDERAL`;
  const oficialBusy = busy === `renov-FEDERAL_OFICIAL`;
  const status = sitfis?.status ?? "DESCONHECIDO";
  const cls =
    status === "VALIDA" ? "cnd-tile--ok"
    : status === "A_VENCER" ? "cnd-tile--warn"
    : status === "VENCIDA" ? "cnd-tile--err"
    : "";

  return (
    <div
      className={`cnd-tile ${cls}`}
      style={{ gridColumn: "span 2", textAlign: "left", padding: "12px 14px" }}
    >
      <dt>Federal RFB+PGFN</dt>
      <strong>{sitfis ? statusLabel(status) : "—"}</strong>
      {sitfis ? (
        <small>
          SITFIS vence {sitfis.data_validade}
          {sitfis.dias_para_vencer !== null
            ? sitfis.dias_para_vencer < 0
              ? ` · ha ${Math.abs(sitfis.dias_para_vencer)}d`
              : ` · em ${sitfis.dias_para_vencer}d`
            : ""}
        </small>
      ) : (
        <small>SITFIS não consultada</small>
      )}
      <small style={{ color: "var(--muted)", fontSize: "0.7rem" }}>
        Integra Contador (uso interno) + CND oficial sob demanda
      </small>

      <div
        style={{
          display: "flex",
          gap: 6,
          marginTop: 10,
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          className="btn-primary"
          style={{ padding: "5px 10px", fontSize: "0.78rem" }}
          onClick={() => onRenovar("FEDERAL")}
          disabled={sitfisBusy}
        >
          {sitfisBusy ? "Consultando..." : "Atualizar SITFIS"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          style={{ padding: "5px 10px", fontSize: "0.78rem" }}
          onClick={() => onRenovar("FEDERAL_OFICIAL")}
          disabled={oficialBusy}
          title="Emite a CND Conjunta RFB+PGFN no portal RFB (uso externo)"
        >
          {oficialBusy ? "Emitindo..." : "Emitir CND oficial"}
        </button>
      </div>
      {oficial ? (
        <small style={{ marginTop: 8, display: "block", color: "var(--muted)" }}>
          ↳ CND oficial emitida {oficial.data_emissao || "?"} · vence {oficial.data_validade}
        </small>
      ) : null}
    </div>
  );
}
