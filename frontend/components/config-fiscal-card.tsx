"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "../lib/api";
import { Empresa, atualizarEmpresa } from "../lib/empresas";

const ANEXOS = [
  { value: "I",   label: "Anexo I — Comércio" },
  { value: "II",  label: "Anexo II — Indústria" },
  { value: "III", label: "Anexo III — Serviços (regra geral)" },
  { value: "IV",  label: "Anexo IV — Serviços (cessão de mão de obra)" },
  { value: "V",   label: "Anexo V — Serviços profissionais" },
];

const ATIVIDADES = [
  { value: "COMERCIO",  label: "Comércio" },
  { value: "INDUSTRIA", label: "Indústria" },
  { value: "SERVICO",   label: "Serviço" },
];

type Props = {
  empresa: Empresa;
  onSaved?: (empresa: Empresa) => void;
};

export function ConfigFiscalCard({ empresa, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [anexo, setAnexo] = useState(empresa.anexo_simples || "");
  const [anexoServico, setAnexoServico] = useState(empresa.anexo_servico || "");
  const [atividade, setAtividade] = useState(empresa.atividade || "");
  const [iss, setIss] = useState(empresa.iss_aliquota?.toString() || "");
  const [folha, setFolha] = useState(empresa.folha_12m?.toString() || "");
  const [soServico, setSoServico] = useState(empresa.so_servico ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const completo = !!empresa.anexo_simples && !!empresa.atividade;
  const precisaIss = ["III", "IV", "V"].includes(empresa.anexo_simples || "");
  const issOk = !precisaIss || empresa.iss_aliquota !== null;
  const precisaFolha = empresa.anexo_simples === "V";
  const folhaOk = !precisaFolha || (empresa.folha_12m && Number(empresa.folha_12m) > 0);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        anexo_simples: anexo || null,
        anexo_servico: anexoServico || null,
        atividade: atividade || null,
        so_servico: soServico,
      };
      if (iss !== "") {
        const v = Number(iss.replace(",", "."));
        if (!Number.isFinite(v) || v < 0) {
          setError("Alíquota ISS inválida"); setSaving(false); return;
        }
        payload.iss_aliquota = v;
      }
      if (folha !== "") {
        const v = Number(folha.replace(",", "."));
        if (!Number.isFinite(v) || v < 0) {
          setError("Folha 12m inválida"); setSaving(false); return;
        }
        payload.folha_12m = v;
      }
      const updated = await atualizarEmpresa(empresa.id, payload as never);
      setEditing(false);
      if (onSaved) onSaved(updated);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    const isSimples = (empresa.regime_tributario || "").toLowerCase().includes("simples");
    return (
      <section className="panel info-card">
        <header className="page-header" style={{ alignItems: "center" }}>
          <h3>Configuração fiscal</h3>
          <div className="page-actions">
            {isSimples ? (
              completo && issOk && folhaOk ? (
                <span className="pill pill-ok">Completa</span>
              ) : (
                <span className="pill pill-warn">Incompleta</span>
              )
            ) : (
              <span className="pill pill-muted">N/A — não é Simples</span>
            )}
            {empresa.so_servico ? (
              <span className="pill pill-info" title="Só serviço — o Robô SEFAZ não roda nela">
                🧾 Só serviço (robô pula)
              </span>
            ) : null}
            <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>
              Editar
            </button>
          </div>
        </header>

        <dl className="kv-grid">
          <dt>Regime</dt>
          <dd>{empresa.regime_tributario || "—"}</dd>
          <dt>Anexo Simples</dt>
          <dd>
            {empresa.anexo_simples ? (
              <>
                Anexo {empresa.anexo_simples}
                {empresa.anexo_simples === "V" ? " — pode migrar p/ III via Fator R" : null}
              </>
            ) : (
              <span className="muted">— (necessário p/ motor)</span>
            )}
          </dd>
          <dt>Atividade</dt>
          <dd>{empresa.atividade || <span className="muted">—</span>}</dd>
          <dt>ISS município</dt>
          <dd>
            {empresa.iss_aliquota !== null && empresa.iss_aliquota !== undefined ? (
              `${empresa.iss_aliquota}%`
            ) : precisaIss ? (
              <span className="muted">— (necessário p/ Anexo {empresa.anexo_simples})</span>
            ) : (
              <span className="muted">não aplicável</span>
            )}
          </dd>
          <dt>Folha 12 meses</dt>
          <dd>
            {empresa.folha_12m && Number(empresa.folha_12m) > 0 ? (
              Number(empresa.folha_12m).toLocaleString("pt-BR", {
                style: "currency", currency: "BRL",
              })
            ) : precisaFolha ? (
              <span className="muted">— (necessário p/ Fator R no Anexo V)</span>
            ) : (
              <span className="muted">não aplicável</span>
            )}
          </dd>
        </dl>

        {isSimples && (!completo || !issOk || !folhaOk) ? (
          <p className="toast toast-error">
            ⚠ Configuração incompleta. O motor de apuração precisa do anexo + atividade
            {precisaIss ? " + ISS" : ""}{precisaFolha ? " + folha 12m" : ""} para calcular o DAS corretamente.
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="panel form-card">
      <h3>Configuração fiscal</h3>
      <p className="muted">
        Estes dados alimentam o motor de apuração mensal. Anexo + atividade são
        obrigatórios; ISS para Anexos III/IV/V; folha 12m para Fator R no Anexo V.
      </p>
      <form onSubmit={handleSubmit} className="form-stack">
        <div className="form-grid">
          <label>
            <span>Anexo Simples Nacional</span>
            <select value={anexo} onChange={(e) => setAnexo(e.target.value)}>
              <option value="">— selecione —</option>
              {ANEXOS.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Atividade principal</span>
            <select value={atividade} onChange={(e) => setAtividade(e.target.value)}>
              <option value="">— selecione —</option>
              {ATIVIDADES.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Anexo do serviço (empresa mista)</span>
            <select value={anexoServico} onChange={(e) => setAnexoServico(e.target.value)}>
              <option value="">— não é mista —</option>
              <option value="III">III — serviços comuns</option>
              <option value="IV">IV — serviços c/ cessão de mão de obra</option>
              <option value="V">V — serviços profissionais</option>
            </select>
            <small className="muted">Use só se a empresa vende E presta serviço. O DAS soma comércio + serviço.</small>
          </label>
          <label>
            <span>Alíquota ISS do município (%)</span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="ex: 5.00"
              value={iss}
              onChange={(e) => setIss(e.target.value)}
            />
          </label>
          <label>
            <span>Folha de pagamento 12m (R$) — Fator R</span>
            <input
              type="text"
              inputMode="decimal"
              placeholder="ex: 120000.00"
              value={folha}
              onChange={(e) => setFolha(e.target.value)}
            />
          </label>
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 4 }}>
          <input
            type="checkbox"
            checked={soServico}
            onChange={(e) => setSoServico(e.target.checked)}
            style={{ marginTop: 3 }}
          />
          <span>
            <strong>Só serviço — não roda no Robô SEFAZ</strong>
            <br />
            <small className="muted">
              Marque se a empresa presta SÓ serviço (emite NFSe, não NF-e/NFC-e). O
              Robô SEFAZ pula ela (a nota vem pela NFSe/ADN) — economiza tempo e captcha.
            </small>
          </span>
        </label>
        {error ? <p className="toast toast-error">{error}</p> : null}
        <div className="form-actions">
          <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Salvando..." : "Salvar"}
          </button>
        </div>
      </form>
    </section>
  );
}
