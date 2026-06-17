"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../lib/api";
import {
  getPortalToken,
  portalBaixarArquivo,
  portalBaixarZip,
  portalDashboard,
  portalDocumentos,
  portalLogout,
  portalManifestarDoc,
  portalManifestarLote,
  portalMe,
  portalResumo,
  type PortalDashboard,
  type PortalDocumento,
  type PortalMe,
  type PortalResumo,
  type RankItem,
} from "../../lib/portal";

function brl(v: number | string | null | undefined): string {
  const n = typeof v === "string" ? Number(v) : v ?? 0;
  return (n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function dataBR(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}
function hoje(): string { return new Date().toISOString().slice(0, 10); }
function trintaDiasAtras(): string {
  const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10);
}
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
function mesLabel(mes: string): string {
  const m = Number((mes || "").split("-")[1]); return MESES_ABREV[m - 1] || mes;
}

const VERDE = "rgb(16,185,129)";
const ROXO = "rgb(168,85,247)";
const AZUL = "rgb(59,130,246)";
const AMBAR = "rgb(234,179,8)";

const CINZA = "rgb(148,163,184)";
const MAX_LINHAS = 50; // não despejar 500 linhas — dashboard em cima + tabela enxuta

function diasDesde(iso: string | null): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? 0 : Math.floor((Date.now() - t) / 86400000);
}

type StatusNota = { label: string; cor: string; baixar: boolean; manifestar: boolean; aguardando: boolean };
function statusNota(doc: PortalDocumento): StatusNota {
  // Vendas (emitidas próprias) e compras já baixadas: XML disponível.
  if (doc.origem !== "recebida" || doc.status === "baixado") {
    return { label: "Disponível", cor: VERDE, baixar: true, manifestar: false, aguardando: false };
  }
  // Manifestação (Ciência da Operação) SÓ existe pra NF-e (modelo 55). NFS-e
  // (serviço, municipal) e CT-e NÃO manifestam — só ficam disponíveis.
  if (doc.tipo_documento !== "NFE") {
    return { label: "Disponível", cor: VERDE, baixar: true, manifestar: false, aguardando: false };
  }
  if (doc.status === "manifestado") {
    return { label: "Manifestada", cor: AZUL, baixar: false, manifestar: false, aguardando: true };
  }
  // resumo: dá pra manifestar se dentro da janela (~90 dias)
  if (diasDesde(doc.data_emissao) > 90) {
    return { label: "Fora do prazo", cor: CINZA, baixar: false, manifestar: false, aguardando: false };
  }
  return { label: "A manifestar", cor: AMBAR, baixar: false, manifestar: true, aguardando: false };
}

function Card({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <div className="card" style={accent ? { borderLeft: `3px solid ${accent}` } : undefined}>{children}</div>
  );
}

/** Ranking horizontal (clientes / fornecedores). */
function Ranking({ items, cor }: { items: RankItem[]; cor: string }) {
  if (!items.length) return <p className="muted" style={{ margin: 0 }}>Sem dados no período.</p>;
  const max = Math.max(...items.map((i) => i.valor), 1);
  return (
    <div>
      {items.map((i, idx) => (
        <div key={`${i.nome}-${idx}`} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, marginBottom: 4 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.nome}</span>
            <strong style={{ flexShrink: 0, fontWeight: 500 }}>{brl(i.valor)}</strong>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "rgba(148,163,184,0.18)" }}>
            <div style={{ height: 6, borderRadius: 3, width: `${Math.round((i.valor / max) * 100)}%`, background: cor }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PortalNotasPage() {
  const router = useRouter();
  const [me, setMe] = useState<PortalMe | null>(null);
  const [resumo, setResumo] = useState<PortalResumo | null>(null);
  const [dash, setDash] = useState<PortalDashboard | null>(null);
  const [docs, setDocs] = useState<PortalDocumento[]>([]);
  const [tipo, setTipo] = useState("");
  const [origem, setOrigem] = useState(""); // "" | "emitida" | "recebida"
  const [dataInicio, setDataInicio] = useState(trintaDiasAtras());
  const [dataFim, setDataFim] = useState(hoje());
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [baixando, setBaixando] = useState<string | null>(null);
  const [zipBusy, setZipBusy] = useState(false);
  const [manifBusy, setManifBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!getPortalToken()) { router.replace("/portal/login"); return; }
    portalMe().then(setMe).catch(() => { portalLogout(); router.replace("/portal/login"); });
  }, [router]);

  const carregar = useCallback(async () => {
    setLoading(true); setErro(null);
    try {
      const params = { data_inicio: dataInicio, data_fim: dataFim };
      const [r, d, lst] = await Promise.all([
        portalResumo(params),
        portalDashboard({ meses: 6, data_inicio: dataInicio, data_fim: dataFim }).catch(() => null), // painel é bônus
        portalDocumentos({ ...params, tipo_documento: tipo || undefined, origem: origem || undefined, cancelada: false }),
      ]);
      setResumo(r);
      if (d) setDash(d);
      setDocs(lst);
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao carregar.");
    } finally {
      setLoading(false);
    }
  }, [dataInicio, dataFim, tipo, origem]);

  useEffect(() => { if (getPortalToken()) carregar(); }, [carregar]);

  async function baixar(doc: PortalDocumento, t: "xml" | "pdf") {
    setBaixando(`${doc.id}-${t}`); setErro(null);
    try { await portalBaixarArquivo(doc.id, t); }
    catch (err) { setErro(err instanceof ApiError ? err.message : `Falha ao baixar ${t.toUpperCase()}.`); }
    finally { setBaixando(null); }
  }

  async function baixarZip(arquivo: "xml" | "pdf") {
    setZipBusy(true); setErro(null);
    try {
      await portalBaixarZip({ tipo_documento: tipo || undefined, origem: origem || undefined, data_inicio: dataInicio, data_fim: dataFim, arquivo });
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao baixar o ZIP.");
    } finally { setZipBusy(false); }
  }

  async function manifestarDoc(doc: PortalDocumento) {
    setManifBusy(`${doc.id}`); setErro(null); setAviso(null);
    try {
      const r = await portalManifestarDoc(doc.id);
      setAviso(r.ok ? (r.aviso || "Ciência registrada! O XML completo será liberado em breve.") : `Não deu: ${r.cstat} ${r.motivo}`);
      await carregar();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao manifestar.");
    } finally { setManifBusy(null); }
  }

  async function manifestarTodas() {
    setManifBusy("lote"); setErro(null); setAviso(null);
    try {
      const r = await portalManifestarLote(20);
      setAviso(`${(r.manifestadas || 0) + (r.ja_cientes || 0)} nota(s) com Ciência. ${r.aviso || ""}`.trim());
      await carregar();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao manifestar em lote.");
    } finally { setManifBusy(null); }
  }

  function sair() { portalLogout(); router.replace("/portal/login"); }

  const docsVisiveis = docs.slice(0, MAX_LINHAS);
  const fatMax = Math.max(...(dash?.faturamento_mensal.map((f) => f.valor) || [1]), 1);

  return (
    <div className="frame" style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      {/* Cabeçalho */}
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", paddingBottom: 16, borderBottom: "1px solid rgba(148,163,184,0.2)", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <img src="/logo.svg" alt="PAC" style={{ height: 38 }} />
          <div>
            <h2 style={{ margin: 0 }}>{me?.empresa?.razao_social || "Minhas Notas"}</h2>
            <p className="muted" style={{ margin: 0 }}>{me?.empresa?.cnpj ? `CNPJ ${me.empresa.cnpj}` : "Portal do Cliente"}</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="muted">{me?.nome}</span>
          <button type="button" className="btn-ghost" onClick={sair}>Sair</button>
        </div>
      </header>

      {/* Filtros */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="form-grid" style={{ gridTemplateColumns: "150px 150px 150px auto", gap: 12, alignItems: "end" }}>
          <label><span>Tipo</span>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos</option>
              <option value="NFE">NF-e / NFC-e</option>
              <option value="CTE">CT-e</option>
              <option value="NFSE">NFS-e</option>
            </select>
          </label>
          <label><span>Emissão de</span><input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></label>
          <label><span>Emissão até</span><input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></label>
          <button type="button" className="btn-primary" onClick={carregar} disabled={loading}>{loading ? "Buscando..." : "Atualizar"}</button>
        </div>
      </div>

      {/* KPIs */}
      {resumo ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, marginBottom: 16 }}>
          <Card accent={VERDE}>
            <p className="muted" style={{ margin: 0 }}>Faturamento (vendas)</p>
            <strong style={{ fontSize: 22, color: VERDE }}>{brl(resumo.faturamento)}</strong>
            <p className="muted" style={{ margin: 0 }}>{resumo.emitidas.ativas} notas de saída</p>
          </Card>
          <Card accent={ROXO}>
            <p className="muted" style={{ margin: 0 }}>Compras (entradas)</p>
            <strong style={{ fontSize: 22, color: ROXO }}>{brl(resumo.recebidas.valor_ativas)}</strong>
            <p className="muted" style={{ margin: 0 }}>{resumo.recebidas.total} notas de entrada</p>
          </Card>
          <Card accent={AZUL}>
            <p className="muted" style={{ margin: 0 }}>Total de notas</p>
            <strong style={{ fontSize: 22 }}>{resumo.total_geral}</strong>
            <p className="muted" style={{ margin: 0 }}>no período</p>
          </Card>
          <Card accent={AMBAR}>
            <p className="muted" style={{ margin: 0 }}>A manifestar</p>
            <strong style={{ fontSize: 22, color: AMBAR }}>{dash?.a_manifestar ?? 0}</strong>
            <p className="muted" style={{ margin: 0 }}>compras em resumo</p>
          </Card>
        </div>
      ) : null}

      {/* Faturamento por mês */}
      {dash && dash.faturamento_mensal.length > 0 ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>Faturamento por mês <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>(tendência — últimos 6 meses)</span></h3>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 150, padding: "8px 4px 0" }}>
            {dash.faturamento_mensal.map((f) => (
              <div key={f.mes} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }} title={brl(f.valor)}>
                <span style={{ fontSize: 11 }} className="muted">{(f.valor / 1000).toFixed(0)}k</span>
                <div style={{ width: "100%", maxWidth: 48, height: `${Math.max(4, Math.round((f.valor / fatMax) * 110))}px`, background: VERDE, borderRadius: "4px 4px 0 0" }} />
                <span style={{ fontSize: 12 }} className="muted">{mesLabel(f.mes)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Painéis: melhores clientes + maiores fornecedores */}
      {dash ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 16 }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>👥 Melhores clientes</h3>
            <Ranking items={dash.top_clientes} cor={AZUL} />
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>🚚 Maiores fornecedores</h3>
            <Ranking items={dash.top_fornecedores} cor={ROXO} />
          </div>
        </div>
      ) : null}

      {aviso ? <p style={{ color: VERDE }}>{aviso}</p> : null}
      {erro ? <p style={{ color: "rgb(248,113,113)" }}>{erro}</p> : null}

      {/* Documentos */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[{ v: "", label: "Todas" }, { v: "emitida", label: "Vendas (saída)" }, { v: "recebida", label: "Compras (entrada)" }].map((t) => (
              <button key={t.v} type="button" className={origem === t.v ? "btn-primary" : "btn-ghost"} onClick={() => setOrigem(t.v)}>{t.label}</button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {dash && dash.a_manifestar > 0 ? (
              <button type="button" className="btn-ghost" onClick={manifestarTodas} disabled={manifBusy === "lote"} title="Dar Ciência da Operação nas compras em resumo — libera o XML completo">
                {manifBusy === "lote" ? "Manifestando..." : `✍ Manifestar ${dash.a_manifestar} pendente(s)`}
              </button>
            ) : null}
            <button type="button" className="btn-ghost" onClick={() => baixarZip("xml")} disabled={zipBusy}>{zipBusy ? "Gerando ZIP..." : "⬇ ZIP de XMLs"}</button>
            <button type="button" className="btn-ghost" onClick={() => baixarZip("pdf")} disabled={zipBusy}>⬇ ZIP de PDFs</button>
          </div>
        </div>

        <p className="muted" style={{ marginTop: 0, marginBottom: 4 }}>
          {loading ? "Carregando..." : `${docs.length} nota(s) no período${docs.length > MAX_LINHAS ? ` — mostrando as ${MAX_LINHAS} mais recentes (use os filtros ou baixe o ZIP)` : ""}.`}
        </p>
        {(origem === "recebida" || origem === "") && (dash?.a_manifestar ?? 0) > 0 ? (
          <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
            <i>Manifestação de compras — prazos: Ciência até 10 dias após a emissão · Confirmação até 90 dias. Notas mais antigas que 90 dias ficam fora do prazo.</i>
          </p>
        ) : null}
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Tipo</th><th>Emissão</th><th>Emitente / Destinatário</th>
                <th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "center" }}>Situação</th><th style={{ textAlign: "center" }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {docsVisiveis.map((doc) => {
                const s = statusNota(doc);
                return (
                  <tr key={doc.id}>
                    <td>{doc.tipo_documento}</td>
                    <td>{dataBR(doc.data_emissao)}</td>
                    <td>{doc.origem === "emitida" ? (doc.nome_destinatario || "Consumidor (balcão)") : (doc.nome_emitente || "—")}</td>
                    <td style={{ textAlign: "right" }}>{brl(doc.valor_total)}</td>
                    <td style={{ textAlign: "center" }}>
                      <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 6, border: `1px solid ${s.cor}`, color: s.cor, whiteSpace: "nowrap" }}>{s.label}</span>
                    </td>
                    <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                      {s.manifestar ? (
                        <button type="button" className="btn-ghost" onClick={() => manifestarDoc(doc)} disabled={manifBusy === `${doc.id}`} title="Dar Ciência da Operação — libera o XML/PDF">
                          {manifBusy === `${doc.id}` ? "..." : "✍ Manifestar"}
                        </button>
                      ) : s.aguardando ? (
                        <span className="muted" style={{ fontSize: 12 }}>aguardando XML</span>
                      ) : s.baixar ? (
                        <>
                          <button type="button" className="btn-ghost" onClick={() => baixar(doc, "xml")} disabled={baixando === `${doc.id}-xml`}>
                            {baixando === `${doc.id}-xml` ? "..." : "XML"}
                          </button>
                          <button type="button" className="btn-ghost" onClick={() => baixar(doc, "pdf")} disabled={baixando === `${doc.id}-pdf`}>
                            {baixando === `${doc.id}-pdf` ? "..." : "PDF"}
                          </button>
                        </>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {!loading && docs.length === 0 ? (
                <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 20 }}>Nenhuma nota no período.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
