"use client";

import { ReactNode, useState } from "react";

import { ApiError } from "../lib/api";
import {
  ResumoMotor,
  calcularESalvar,
  calcularPreview,
} from "../lib/apuracoes";

function fmt(v: string | null | undefined): string {
  if (!v) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function fmtPct(v: string | null | undefined): string {
  if (!v) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(4)}%`;
}

const NATUREZA_LABEL: Record<string, string> = {
  VENDA: "Venda",
  VENDA_ST: "Venda c/ ST",
  EXPORTACAO: "Exportação",
  DEVOLUCAO_VENDA: "Devolução de venda",
  DEVOLUCAO_COMPRA: "Devolução de compra",
  COMPRA: "Compra",
  REMESSA_NAO_RECEITA: "Remessa",
  TRANSFERENCIA: "Transferência",
  SERVICO: "Serviço",
  OUTRO: "Outro",
};

const TRIBUTACAO_PILL: Record<string, string> = {
  NORMAL: "pill pill-info",
  MONOFASICO: "pill pill-violet",
  ST: "pill pill-warn",
  MONOFASICO_ST: "pill pill-violet",
  ISENTA: "pill pill-muted",
  EXPORTACAO: "pill pill-ok",
};

const TRIBUTACAO_LABEL: Record<string, string> = {
  NORMAL: "Normal",
  MONOFASICO: "Monofásico",
  ST: "ICMS-ST",
  MONOFASICO_ST: "Mono+ST",
  ISENTA: "Isenta",
  EXPORTACAO: "Exportação",
};

const CATEGORIA_LABEL: Record<string, string> = {
  COMBUSTIVEL: "Combustíveis",
  MEDICAMENTO_COSMETICO: "Medicamentos / Cosméticos",
  VEICULO_AUTOPECA_PNEU: "Veículos / Autopeças / Pneus",
  BEBIDA_FRIA: "Bebidas frias",
  CIGARRO: "Cigarros / Fumo",
};


type Props = {
  empresaId: number;
  anoMes: string;
  onSalvar?: (apuracaoId: number) => void;
};


export function MotorCalculoCard({ empresaId, anoMes, onSalvar }: Props) {
  const [resumo, setResumo] = useState<ResumoMotor | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandido, setExpandido] = useState(false);

  async function handleCalcular() {
    setBusy("calc"); setError(null);
    try {
      const r = await calcularPreview(empresaId, anoMes);
      setResumo(r);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao calcular.");
    } finally { setBusy(null); }
  }

  async function handleSalvar() {
    setBusy("save"); setError(null);
    try {
      const apur = await calcularESalvar(empresaId, anoMes);
      if (onSalvar) onSalvar((apur as { id: number }).id);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao salvar.");
    } finally { setBusy(null); }
  }

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <div>
          <h3>Motor de cálculo Simples Nacional</h3>
          <p className="muted">
            Lê NFes do mês, classifica CFOP item-a-item, identifica monofásico/ST,
            aplica RBT12 e tabela do Anexo.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleCalcular}
            disabled={busy === "calc"}
          >
            {busy === "calc" ? "Calculando..." : "Calcular dos XMLs"}
          </button>
          {resumo && resumo.calculo ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={handleSalvar}
              disabled={busy === "save"}
              title="Salva a apuração e já roda o dry-run na Receita (compara RFB × PAC)."
            >
              {busy === "save" ? "Salvando..." : "Criar apuração + validar na Receita"}
            </button>
          ) : null}
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      {!resumo ? (
        <p className="muted">
          Clique em <strong>Calcular dos XMLs</strong> para o motor analisar todos
          os documentos da competência {anoMes.slice(4)}/{anoMes.slice(0, 4)} e
          devolver receita bruta líquida + DAS estimado.
        </p>
      ) : (
        <ResumoVisual resumo={resumo} expandido={expandido} setExpandido={setExpandido} />
      )}
    </section>
  );
}


function ResumoVisual({
  resumo, expandido, setExpandido,
}: {
  resumo: ResumoMotor;
  expandido: boolean;
  setExpandido: (v: boolean) => void;
}) {
  const c = resumo.calculo;
  return (
    <>
      {/* KPIs principais */}
      <section className="grid">
        <article className="metric metric--cyan">
          <span>Documentos</span>
          <strong>{resumo.total_docs}</strong>
          <p>{resumo.saidas} saídas · {resumo.entradas} entradas · {resumo.docs_ignorados} sem efeito fiscal</p>
        </article>
        <article className="metric metric--emerald">
          <span>Receita Bruta</span>
          <strong>{fmt(resumo.receita_bruta)}</strong>
          <p>liquida de {fmt(resumo.total_devolucoes_venda)} de devolução</p>
        </article>
        <article className="metric metric--violet">
          <span>Anexo {resumo.anexo}{c ? ` · faixa ${c.faixa}` : ""}</span>
          <strong>{c ? fmtPct(c.aliquota_efetiva) : "—"}</strong>
          <p>RBT12 {fmt(resumo.rbt12)}{resumo.primeira_apuracao ? " · 1ª apuração" : ""}</p>
        </article>
        <article className="metric metric--amber">
          <span>DAS estimado</span>
          <strong>{c ? fmt(c.valor_devido) : "—"}</strong>
          <p>{c?.teto_excedido ? "⚠ teto excedido" : "decomposto por tributo"}</p>
        </article>
      </section>

      {/* Segregacao por tipo de receita */}
      <div>
        <p className="section-divider">Segregação por tipo de tributação</p>
        <div className="cnd-grid">
          <SegmentoTile label="Normal"      valor={resumo.total_normal}        classe="cnd-tile--ok"   />
          <SegmentoTile label="Monofásico"  valor={resumo.total_monofasico}    classe="cnd-tile--warn" sub="PIS+COFINS zerados" />
          <SegmentoTile label="ICMS-ST"     valor={resumo.total_st}            classe="cnd-tile--warn" sub="ICMS já recolhido" />
          <SegmentoTile label="Mono+ST"     valor={resumo.total_monofasico_st} classe="cnd-tile--warn" sub="zera PIS/COFINS e ICMS" />
          <SegmentoTile label="Exportação"  valor={resumo.total_exportacao}    classe="cnd-tile--ok"   sub="zera PIS/COFINS/ICMS" />
          <SegmentoTile label="Serviços"    valor={resumo.total_servicos}      classe="" />
        </div>
      </div>

      {/* Monofasico por categoria */}
      {Object.keys(resumo.monofasico_por_categoria).length > 0 ? (
        <div>
          <p className="section-divider">Monofásico por categoria (NCM)</p>
          <dl className="kv-grid">
            {Object.entries(resumo.monofasico_por_categoria).map(([cat, v]) => (
              <ItemKv
                key={cat}
                k={CATEGORIA_LABEL[cat] || cat}
                v={fmt(v)}
              />
            ))}
          </dl>
        </div>
      ) : null}

      {/* Cálculo segregado por parcela */}
      {c ? (
        <div>
          <p className="section-divider">Cálculo do DAS por parcela</p>
          <dl className="kv-grid">
            <ItemKv k="Receita NORMAL"     v={`${fmt(c.receita_normal)} → DAS ${fmt(c.valor_normal)}`} />
            <ItemKv k="Receita MONOFÁSICA" v={`${fmt(c.receita_monofasica)} → DAS ${fmt(c.valor_monofasico)} (sem PIS/COFINS)`} />
            <ItemKv k="Receita ST"         v={`${fmt(c.receita_st)} → DAS ${fmt(c.valor_st)} (sem ICMS)`} />
            <ItemKv k="Receita MONO+ST"    v={`${fmt(c.receita_monofasica_st)} → DAS ${fmt(c.valor_monofasico_st)} (sem PIS/COFINS e ICMS)`} />
            <ItemKv k="Receita EXPORT"     v={`${fmt(c.receita_exportacao)} → DAS ${fmt(c.valor_exportacao)}`} />
            <ItemKv k="Receita TOTAL"      v={fmt(c.receita_total)} />
            <ItemKv k="DAS TOTAL"          v={<strong>{fmt(c.valor_devido)}</strong>} />
          </dl>

          <p className="section-divider" style={{ marginTop: 14 }}>
            Decomposição por tributo
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {Object.entries(c.decomposicao).map(([t, v]) => (
              <span key={t} className="pill pill-info" style={{ padding: "5px 11px" }}>
                {t}: {fmt(v)}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {/* Avisos */}
      {resumo.avisos.length > 0 ? (
        <div>
          <p className="section-divider">Avisos</p>
          <ul style={{ display: "grid", gap: 6, listStyle: "none", padding: 0, margin: 0 }}>
            {resumo.avisos.map((a, i) => (
              <li key={i} className="toast toast-error" style={{ fontSize: "0.86rem" }}>
                ⚠ {a}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Detalhamento item a item (auditoria) */}
      <div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setExpandido(!expandido)}
        >
          {expandido ? "Recolher" : "Ver auditoria item a item"} ({resumo.documentos.length} doc)
        </button>
      </div>
      {expandido ? <AuditoriaTabela docs={resumo.documentos} /> : null}
    </>
  );
}


function SegmentoTile({
  label, valor, classe = "", sub,
}: { label: string; valor: string; classe?: string; sub?: string }) {
  return (
    <div className={`cnd-tile ${classe}`}>
      <dt>{label}</dt>
      <strong>{fmt(valor)}</strong>
      {sub ? <small>{sub}</small> : null}
    </div>
  );
}


function ItemKv({ k, v }: { k: string; v: ReactNode }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}


function AuditoriaTabela({ docs }: { docs: ResumoMotor["documentos"] }) {
  return (
    <div style={{ overflow: "auto", maxHeight: 480, border: "1px solid var(--border)", borderRadius: 12 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
        <thead style={{ position: "sticky", top: 0, background: "var(--surface-strong)" }}>
          <tr>
            <th style={cellHead}>#</th>
            <th style={cellHead}>Emitente</th>
            <th style={cellHead}>Valor</th>
            <th style={cellHead}>Direção</th>
            <th style={cellHead}>Natureza</th>
            <th style={cellHead}>CFOPs</th>
            <th style={cellHead}>Itens</th>
            <th style={cellHead}>Tributação</th>
            <th style={cellHead}>Receita</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.documento_id} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={cell}>{d.documento_id}</td>
              <td style={cell}>{d.nome_emitente || "—"}</td>
              <td style={cell}>{fmt(d.valor_nota)}</td>
              <td style={cell}>
                <span className={d.direcao === "SAIDA" ? "pill pill-ok" : "pill pill-info"}>
                  {d.direcao}
                </span>
              </td>
              <td style={cell}>{NATUREZA_LABEL[d.natureza_predominante] || d.natureza_predominante}</td>
              <td style={cell}>{d.cfops.join(", ")}</td>
              <td style={cell}>{d.itens.length}</td>
              <td style={cell}>
                {d.itens.length > 0 ? (
                  <span className={TRIBUTACAO_PILL[d.itens[0].tipo_tributacao] || "pill"}>
                    {TRIBUTACAO_LABEL[d.itens[0].tipo_tributacao] || d.itens[0].tipo_tributacao}
                    {d.itens.length > 1 ? ` +${d.itens.length - 1}` : ""}
                  </span>
                ) : "—"}
              </td>
              <td style={cell}>
                {d.afeta_receita > 0 ? <span style={{ color: "#34d399" }}>+ {fmt(d.contribuicao_receita)}</span>
                  : d.afeta_receita < 0 ? <span style={{ color: "#fb7185" }}>{fmt(d.contribuicao_receita)}</span>
                  : <span className="muted">{d.motivo_zero || "—"}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const cellHead: React.CSSProperties = {
  padding: "8px 10px",
  textAlign: "left",
  fontSize: "0.72rem",
  color: "var(--muted)",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  borderBottom: "1px solid var(--border)",
};
const cell: React.CSSProperties = { padding: "8px 10px", fontSize: "0.86rem" };
