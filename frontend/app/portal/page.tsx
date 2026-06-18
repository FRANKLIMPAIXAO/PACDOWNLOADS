"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../lib/api";
import {
  getPortalToken,
  portalBaixarArquivo,
  portalBaixarDocEscritorio,
  portalBaixarZip,
  portalDashboard,
  portalDocumentos,
  portalDocumentosEscritorio,
  portalLogout,
  portalManifestarDoc,
  portalManifestarLote,
  portalMe,
  portalResumo,
  type DocEscritorio,
  type DocsEscritorio,
  type PortalDashboard,
  type PortalDocumento,
  type PortalMe,
  type PortalResumo,
  type RankItem,
} from "../../lib/portal";

// ---- Marca PAC ----
const NAVY = "#16294d";
const NAVY_2 = "#1f3563";
const ORANGE = "#ec8b1c";
const ORANGE_TX = "#b96a0c"; // laranja legível sobre branco
const GREEN = "#1d9e75";
const BLUE = "#2b6cb0";
const GRAY = "#6b7488";

const MAX_LINHAS = 50; // tabela enxuta dentro de "Minhas notas"

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

function tipoEscritorio(tipo: string): { label: string; cor: string } {
  switch (tipo) {
    case "guia": return { label: "Guia / imposto", cor: ORANGE_TX };
    case "relatorio": return { label: "Relatório", cor: BLUE };
    case "comunicado": return { label: "Comunicado", cor: NAVY };
    default: return { label: "Documento", cor: GRAY };
  }
}

function diasDesde(iso: string | null): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? 0 : Math.floor((Date.now() - t) / 86400000);
}

type StatusNota = { label: string; cor: string; baixar: boolean; manifestar: boolean; aguardando: boolean };
function statusNota(doc: PortalDocumento): StatusNota {
  if (doc.origem !== "recebida" || doc.status === "baixado") {
    return { label: "Disponível", cor: GREEN, baixar: true, manifestar: false, aguardando: false };
  }
  // Manifestação (Ciência da Operação) SÓ existe pra NF-e (modelo 55). NFS-e e CT-e não manifestam.
  if (doc.tipo_documento !== "NFE") {
    return { label: "Disponível", cor: GREEN, baixar: true, manifestar: false, aguardando: false };
  }
  if (doc.status === "manifestado") {
    return { label: "Manifestada", cor: BLUE, baixar: false, manifestar: false, aguardando: true };
  }
  if (diasDesde(doc.data_emissao) > 90) {
    return { label: "Fora do prazo", cor: GRAY, baixar: false, manifestar: false, aguardando: false };
  }
  return { label: "A manifestar", cor: ORANGE_TX, baixar: false, manifestar: true, aguardando: false };
}

// ---- Ícones (SVG inline, estilo linha — herdam cor/tamanho) ----
const ICONS: Record<string, React.ReactNode> = {
  home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></>,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M9 13h6M9 17h4" /></>,
  chart: <><path d="M4 20V10M10 20V4M16 20v-7" /><path d="M2 20h20" /></>,
  folder: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></>,
  check: <><path d="M9 11l3 3 9-9" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>,
  logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></>,
  bell: <><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>,
  users: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
  truck: <><path d="M1 3h15v13H1zM16 8h4l3 3v5h-7z" /><circle cx="5.5" cy="18.5" r="2" /><circle cx="18.5" cy="18.5" r="2" /></>,
};
function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }} aria-hidden="true">{ICONS[name]}</svg>
  );
}

function pill(label: string, cor: string) {
  return <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 6, border: `1px solid ${cor}`, color: cor, whiteSpace: "nowrap" }}>{label}</span>;
}

/** Ranking horizontal (clientes / fornecedores). */
function Ranking({ items, cor }: { items: RankItem[]; cor: string }) {
  if (!items.length) return <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>Sem dados no período.</p>;
  const max = Math.max(...items.map((i) => i.valor), 1);
  return (
    <div>
      {items.map((i, idx) => (
        <div key={`${i.nome}-${idx}`} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, marginBottom: 4 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.nome}</span>
            <strong style={{ flexShrink: 0, fontWeight: 500 }}>{brl(i.valor)}</strong>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "#eef1f5" }}>
            <div style={{ height: 6, borderRadius: 3, width: `${Math.round((i.valor / max) * 100)}%`, background: cor }} />
          </div>
        </div>
      ))}
    </div>
  );
}

type View = "home" | "notas" | "documentos" | "indicadores" | "manifestar";

export default function PortalPage() {
  const router = useRouter();
  const [view, setView] = useState<View>("home");
  const [me, setMe] = useState<PortalMe | null>(null);
  const [resumo, setResumo] = useState<PortalResumo | null>(null);
  const [dash, setDash] = useState<PortalDashboard | null>(null);
  const [escritorio, setEscritorio] = useState<DocsEscritorio | null>(null);
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

  const carregarEscritorio = useCallback(() => {
    portalDocumentosEscritorio().then(setEscritorio).catch(() => { /* seção é opcional */ });
  }, []);

  useEffect(() => {
    if (!getPortalToken()) { router.replace("/portal/login"); return; }
    portalMe().then(setMe).catch(() => { portalLogout(); router.replace("/portal/login"); });
    carregarEscritorio();
  }, [router, carregarEscritorio]);

  async function baixarDocEscritorio(d: DocEscritorio) {
    setBaixando(`esc-${d.id}`); setErro(null);
    try {
      await portalBaixarDocEscritorio(d.id, d.nome_arquivo || undefined);
      carregarEscritorio();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao baixar o documento.");
    } finally { setBaixando(null); }
  }

  const carregar = useCallback(async () => {
    setLoading(true); setErro(null);
    try {
      const params = { data_inicio: dataInicio, data_fim: dataFim };
      const [r, d, lst] = await Promise.all([
        portalResumo(params),
        portalDashboard({ meses: 6, data_inicio: dataInicio, data_fim: dataFim }).catch(() => null),
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

  function irPara(v: View) {
    if (v === "manifestar" && origem === "emitida") setOrigem("");
    setErro(null); setAviso(null);
    setView(v);
  }

  const docsVisiveis = docs.slice(0, MAX_LINHAS);
  const manifestaveis = docs.filter((d) => { const s = statusNota(d); return s.manifestar || s.aguardando; });
  const fatMax = Math.max(...(dash?.faturamento_mensal.map((f) => f.valor) || [1]), 1);
  const aManifestar = dash?.a_manifestar ?? 0;

  const navGroups = [
    { grupo: "Empresa", itens: [
      { id: "home" as View, label: "Início", icon: "home" },
      { id: "notas" as View, label: "Minhas notas", icon: "file" },
      { id: "indicadores" as View, label: "Faturamento", icon: "chart" },
    ] },
    { grupo: "Documentos", itens: [
      { id: "documentos" as View, label: "Do escritório", icon: "folder", badge: escritorio?.nao_lidos || 0 },
      { id: "manifestar" as View, label: "Manifestações", icon: "check", badge: aManifestar },
    ] },
  ];

  // ---- pedaços reutilizáveis ----
  const filtroPeriodo = (comTipo: boolean) => (
    <div className="pac-card" style={{ marginBottom: 16 }}>
      <div className="pac-filtros">
        {comTipo ? (
          <label>Tipo
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos</option>
              <option value="NFE">NF-e / NFC-e</option>
              <option value="CTE">CT-e</option>
              <option value="NFSE">NFS-e</option>
            </select>
          </label>
        ) : null}
        <label>Emissão de<input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></label>
        <label>Emissão até<input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></label>
        <button type="button" className="pac-btn pac-btn-primary" onClick={carregar} disabled={loading}>{loading ? "Buscando..." : "Atualizar"}</button>
      </div>
    </div>
  );

  const tabelaNotas = (lista: PortalDocumento[]) => (
    <div style={{ overflowX: "auto" }}>
      <table className="pac-table">
        <thead>
          <tr>
            <th>Tipo</th><th>Emissão</th><th>Emitente / Destinatário</th>
            <th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "center" }}>Situação</th><th style={{ textAlign: "center" }}>Ações</th>
          </tr>
        </thead>
        <tbody>
          {lista.map((doc) => {
            const s = statusNota(doc);
            return (
              <tr key={doc.id}>
                <td>{doc.tipo_documento}</td>
                <td>{dataBR(doc.data_emissao)}</td>
                <td>{doc.origem === "emitida" ? (doc.nome_destinatario || "Consumidor (balcão)") : (doc.nome_emitente || "—")}</td>
                <td style={{ textAlign: "right" }}>{brl(doc.valor_total)}</td>
                <td style={{ textAlign: "center" }}>{pill(s.label, s.cor)}</td>
                <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                  {s.manifestar ? (
                    <button type="button" className="pac-btn pac-btn-ghost" onClick={() => manifestarDoc(doc)} disabled={manifBusy === `${doc.id}`} title="Dar Ciência da Operação — libera o XML/PDF">
                      {manifBusy === `${doc.id}` ? "..." : "✍ Manifestar"}
                    </button>
                  ) : s.aguardando ? (
                    <span style={{ fontSize: 12, color: GRAY }}>aguardando XML</span>
                  ) : s.baixar ? (
                    <span style={{ display: "inline-flex", gap: 6 }}>
                      <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixar(doc, "xml")} disabled={baixando === `${doc.id}-xml`}>
                        {baixando === `${doc.id}-xml` ? "..." : "XML"}
                      </button>
                      <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixar(doc, "pdf")} disabled={baixando === `${doc.id}-pdf`}>
                        {baixando === `${doc.id}-pdf` ? "..." : "PDF"}
                      </button>
                    </span>
                  ) : (
                    <span style={{ color: GRAY }}>—</span>
                  )}
                </td>
              </tr>
            );
          })}
          {!loading && lista.length === 0 ? (
            <tr><td colSpan={6} style={{ textAlign: "center", padding: 20, color: GRAY }}>Nenhuma nota.</td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );

  const tituloSecao = (icon: string, txt: string, extra?: React.ReactNode) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 14px" }}>
      <span style={{ color: NAVY }}><Icon name={icon} size={22} /></span>
      <h2 style={{ margin: 0, fontSize: 19, color: NAVY }}>{txt}</h2>
      {extra}
    </div>
  );

  return (
    <div className="pac-portal">
      <aside className="pac-sidebar">
        <div className="pac-logo" onClick={() => irPara("home")} title="Início">
          <img src="/pac-logo-branco.svg" alt="PAC Inteligência Tributária" />
        </div>

        <nav className="pac-nav">
          {navGroups.map((g) => (
            <div key={g.grupo} className="pac-navgroup">
              <div className="pac-navgroup-label">{g.grupo}</div>
              {g.itens.map((it) => (
                <button key={it.id} type="button" className={`pac-navitem${view === it.id ? " active" : ""}`} onClick={() => irPara(it.id)} title={it.label}>
                  <Icon name={it.icon} size={18} />
                  <span className="pac-navlabel">{it.label}</span>
                  {"badge" in it && (it as { badge: number }).badge > 0 ? (
                    <span className="pac-badge">{(it as { badge: number }).badge}</span>
                  ) : null}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="pac-sidebar-foot">
          <div className="pac-user-name">{me?.nome || ""}</div>
          <button type="button" className="pac-navitem" onClick={sair} title="Sair">
            <Icon name="logout" size={18} /><span className="pac-navlabel">Sair</span>
          </button>
        </div>
      </aside>

      <div className="pac-main">
        <header className="pac-topbar">
          <div>
            <div className="pac-topbar-empresa">{me?.empresa?.razao_social || "Portal do Cliente"}</div>
            <div className="pac-topbar-cnpj">{me?.empresa?.cnpj ? `CNPJ ${me.empresa.cnpj}` : ""}</div>
          </div>
          <span style={{ color: GRAY }}><Icon name="bell" size={20} /></span>
        </header>

        <div className="pac-content">
          {aviso ? <div className="pac-toast pac-toast-ok">{aviso}</div> : null}
          {erro ? <div className="pac-toast pac-toast-err">{erro}</div> : null}

          {/* ===================== HOME ===================== */}
          {view === "home" ? (
            <>
              {filtroPeriodo(false)}
              {resumo ? (
                <div className="pac-kpis">
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">Faturamento (vendas)</div>
                    <div className="pac-kpi-value" style={{ color: GREEN }}>{brl(resumo.faturamento)}</div>
                    <div className="pac-kpi-sub">{resumo.emitidas.ativas} notas de saída</div>
                  </div>
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">Compras (entradas)</div>
                    <div className="pac-kpi-value" style={{ color: NAVY }}>{brl(resumo.recebidas.valor_ativas)}</div>
                    <div className="pac-kpi-sub">{resumo.recebidas.total} notas de entrada</div>
                  </div>
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">Total de notas</div>
                    <div className="pac-kpi-value" style={{ color: BLUE }}>{resumo.total_geral}</div>
                    <div className="pac-kpi-sub">no período</div>
                  </div>
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">A manifestar</div>
                    <div className="pac-kpi-value" style={{ color: ORANGE_TX }}>{aManifestar}</div>
                    <div className="pac-kpi-sub">compras em resumo</div>
                  </div>
                </div>
              ) : null}

              <h3 style={{ margin: "4px 0 12px", color: GRAY, fontWeight: 500, fontSize: 14 }}>Atalhos</h3>
              <div className="pac-atalhos">
                <button type="button" className="pac-atalho pac-atalho-hero" onClick={() => irPara("notas")}>
                  <Icon name="file" size={22} />
                  <div className="pac-atalho-tit">Minhas notas fiscais</div>
                  <div className="pac-atalho-sub">{resumo ? `${resumo.total_geral} notas · baixar XML/PDF/ZIP` : "Carregando..."}</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("documentos")}>
                  <span style={{ color: NAVY }}><Icon name="folder" size={22} /></span>
                  <div className="pac-atalho-tit">Documentos do escritório{escritorio && escritorio.nao_lidos > 0 ? <span className="pac-tag">{escritorio.nao_lidos} novos</span> : null}</div>
                  <div className="pac-atalho-sub">Guias, relatórios e comunicados</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("indicadores")}>
                  <span style={{ color: GREEN }}><Icon name="chart" size={22} /></span>
                  <div className="pac-atalho-tit">Faturamento e indicadores</div>
                  <div className="pac-atalho-sub">Gráfico + melhores clientes</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("manifestar")}>
                  <span style={{ color: ORANGE }}><Icon name="check" size={22} /></span>
                  <div className="pac-atalho-tit">Manifestações{aManifestar > 0 ? <span className="pac-tag">{aManifestar}</span> : null}</div>
                  <div className="pac-atalho-sub">Liberar o XML das compras</div>
                </button>
              </div>
            </>
          ) : null}

          {/* ===================== MINHAS NOTAS ===================== */}
          {view === "notas" ? (
            <>
              {tituloSecao("file", "Minhas notas fiscais")}
              {filtroPeriodo(true)}
              <div className="pac-card">
                <div className="pac-toolbar">
                  <div className="pac-tabs">
                    {[{ v: "", label: "Todas" }, { v: "emitida", label: "Vendas (saída)" }, { v: "recebida", label: "Compras (entrada)" }].map((t) => (
                      <button key={t.v} type="button" className={`pac-tab${origem === t.v ? " active" : ""}`} onClick={() => setOrigem(t.v)}>{t.label}</button>
                    ))}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarZip("xml")} disabled={zipBusy}>{zipBusy ? "Gerando ZIP..." : "⬇ ZIP de XMLs"}</button>
                    <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarZip("pdf")} disabled={zipBusy}>⬇ ZIP de PDFs</button>
                  </div>
                </div>
                <p style={{ margin: "0 0 10px", color: GRAY, fontSize: 13 }}>
                  {loading ? "Carregando..." : `${docs.length} nota(s) no período${docs.length > MAX_LINHAS ? ` — mostrando as ${MAX_LINHAS} mais recentes (use os filtros ou baixe o ZIP)` : ""}.`}
                </p>
                {tabelaNotas(docsVisiveis)}
              </div>
            </>
          ) : null}

          {/* ===================== DOCUMENTOS DO ESCRITÓRIO ===================== */}
          {view === "documentos" ? (
            <>
              {tituloSecao("folder", "Documentos do escritório", escritorio && escritorio.nao_lidos > 0 ? <span className="pac-tag">{escritorio.nao_lidos} novos</span> : undefined)}
              <div className="pac-card">
                {!escritorio ? (
                  <p style={{ margin: 0, color: GRAY }}>Carregando...</p>
                ) : escritorio.documentos.length === 0 ? (
                  <p style={{ margin: 0, color: GRAY }}>
                    Nenhum documento ainda. Quando o escritório te enviar guias, relatórios ou comunicados, eles aparecem aqui.
                  </p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="pac-table">
                      <thead>
                        <tr>
                          <th>Tipo</th><th>Documento</th><th>Competência</th><th>Vencimento</th>
                          <th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "center" }}>Ação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {escritorio.documentos.map((d) => {
                          const t = tipoEscritorio(d.tipo);
                          return (
                            <tr key={d.id}>
                              <td>{pill(t.label, t.cor)}</td>
                              <td>
                                <span style={!d.lido ? { fontWeight: 500 } : undefined}>
                                  {!d.lido ? "🔵 " : ""}{d.titulo}
                                </span>
                                {d.mensagem ? <div style={{ fontSize: 12, color: GRAY }}>{d.mensagem}</div> : null}
                              </td>
                              <td>{d.competencia || "—"}</td>
                              <td>{d.vencimento ? dataBR(d.vencimento) : "—"}</td>
                              <td style={{ textAlign: "right" }}>{d.valor != null ? brl(d.valor) : "—"}</td>
                              <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                                {d.tem_arquivo ? (
                                  <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarDocEscritorio(d)} disabled={baixando === `esc-${d.id}`}>
                                    {baixando === `esc-${d.id}` ? "..." : "⬇ Baixar"}
                                  </button>
                                ) : <span style={{ color: GRAY }}>—</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : null}

          {/* ===================== FATURAMENTO E INDICADORES ===================== */}
          {view === "indicadores" ? (
            <>
              {tituloSecao("chart", "Faturamento e indicadores")}
              {filtroPeriodo(false)}
              {dash && dash.faturamento_mensal.length > 0 ? (
                <div className="pac-card" style={{ marginBottom: 16 }}>
                  <h3 style={{ marginTop: 0, color: NAVY }}>Faturamento por mês <span style={{ fontSize: 13, fontWeight: 400, color: GRAY }}>(tendência — últimos 6 meses)</span></h3>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 150, padding: "8px 4px 0" }}>
                    {dash.faturamento_mensal.map((f) => (
                      <div key={f.mes} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }} title={brl(f.valor)}>
                        <span style={{ fontSize: 11, color: GRAY }}>{(f.valor / 1000).toFixed(0)}k</span>
                        <div style={{ width: "100%", maxWidth: 48, height: `${Math.max(4, Math.round((f.valor / fatMax) * 110))}px`, background: GREEN, borderRadius: "4px 4px 0 0" }} />
                        <span style={{ fontSize: 12, color: GRAY }}>{mesLabel(f.mes)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {dash ? (
                <div className="pac-paineis">
                  <div className="pac-card">
                    <h3 style={{ marginTop: 0, color: NAVY, display: "flex", alignItems: "center", gap: 8 }}><Icon name="users" size={18} /> Melhores clientes</h3>
                    <Ranking items={dash.top_clientes} cor={BLUE} />
                  </div>
                  <div className="pac-card">
                    <h3 style={{ marginTop: 0, color: NAVY, display: "flex", alignItems: "center", gap: 8 }}><Icon name="truck" size={18} /> Maiores fornecedores</h3>
                    <Ranking items={dash.top_fornecedores} cor={NAVY} />
                  </div>
                </div>
              ) : (
                <div className="pac-card"><p style={{ margin: 0, color: GRAY }}>Sem indicadores no período.</p></div>
              )}
            </>
          ) : null}

          {/* ===================== MANIFESTAÇÕES ===================== */}
          {view === "manifestar" ? (
            <>
              {tituloSecao("check", "Manifestações")}
              {filtroPeriodo(false)}
              <div className="pac-card">
                <div className="pac-toolbar">
                  <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>
                    {aManifestar > 0
                      ? `${aManifestar} compra(s) aguardando Ciência da Operação. Manifestar libera o XML/PDF completo.`
                      : "Nenhuma compra pendente de manifestação. Tudo em dia. ✅"}
                  </p>
                  {aManifestar > 0 ? (
                    <button type="button" className="pac-btn pac-btn-primary" onClick={manifestarTodas} disabled={manifBusy === "lote"} title="Dar Ciência da Operação em todas as compras em resumo">
                      {manifBusy === "lote" ? "Manifestando..." : `✍ Manifestar ${aManifestar} pendente(s)`}
                    </button>
                  ) : null}
                </div>
                <p style={{ margin: "0 0 10px", color: GRAY, fontSize: 12, fontStyle: "italic" }}>
                  Prazos: Ciência até 10 dias após a emissão · Confirmação até 90 dias. Notas com mais de 90 dias ficam fora do prazo.
                </p>
                {tabelaNotas(manifestaveis)}
              </div>
            </>
          ) : null}
        </div>
      </div>

      <style jsx>{`
        .pac-portal { display: flex; min-height: 100vh; background: #f5f7fa; color: #1b2333;
          font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif; letter-spacing: -0.01em; }

        .pac-sidebar { width: 208px; flex-shrink: 0; background: ${NAVY}; color: #c4d0e4;
          display: flex; flex-direction: column; gap: 16px; padding: 16px 12px; }
        .pac-logo { display: flex; align-items: center; padding: 6px 6px 2px; cursor: pointer; }
        .pac-logo img { height: 34px; display: block; }
        .pac-nav { display: flex; flex-direction: column; gap: 14px; }
        .pac-navgroup { display: flex; flex-direction: column; gap: 2px; }
        .pac-navgroup-label { color: #6f82a6; font-size: 11px; letter-spacing: 0.08em; padding: 0 8px 4px; text-transform: uppercase; }
        .pac-navitem { position: relative; display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
          padding: 9px 10px; border-radius: 8px; border: none; background: transparent; color: #c4d0e4;
          font: inherit; font-size: 13.5px; cursor: pointer; transition: background .12s ease, color .12s ease; }
        .pac-navitem:hover { background: ${NAVY_2}; color: #fff; }
        .pac-navitem.active { background: rgba(236,139,28,0.16); color: #fff; box-shadow: inset 3px 0 0 ${ORANGE}; }
        .pac-navlabel { flex: 1; }
        .pac-badge { background: ${ORANGE}; color: ${NAVY}; font-size: 11px; font-weight: 500; padding: 0 7px; border-radius: 9px; }
        .pac-sidebar-foot { margin-top: auto; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 10px; }
        .pac-user-name { color: #9fb0cc; font-size: 12px; padding: 0 10px 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

        .pac-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .pac-topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px;
          background: #fff; border-bottom: 1px solid #e6eaf0; padding: 12px 24px; }
        .pac-topbar-empresa { font-size: 14px; font-weight: 500; color: ${NAVY}; }
        .pac-topbar-cnpj { font-size: 12px; color: ${GRAY}; }
        .pac-content { padding: 20px 24px; }

        .pac-card { background: #fff; border: 1px solid #e6eaf0; border-radius: 12px; padding: 16px 18px; }
        .pac-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
        .pac-kpi { padding: 14px 16px; }
        .pac-kpi-label { font-size: 13px; color: ${GRAY}; }
        .pac-kpi-value { font-size: 22px; font-weight: 500; margin: 2px 0; }
        .pac-kpi-sub { font-size: 12px; color: ${GRAY}; }

        .pac-atalhos { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .pac-atalho { text-align: left; background: #fff; border: 1px solid #e6eaf0; border-radius: 11px; padding: 16px;
          cursor: pointer; color: ${NAVY}; font: inherit; transition: transform .12s ease, box-shadow .12s ease; }
        .pac-atalho:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(22,41,77,0.08); }
        .pac-atalho-hero { background: ${NAVY}; border-color: ${NAVY}; color: #fff; }
        .pac-atalho-hero :global(svg) { color: ${ORANGE}; }
        .pac-atalho-tit { font-size: 14px; font-weight: 500; margin-top: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .pac-atalho-sub { font-size: 12px; margin-top: 2px; opacity: .8; }
        .pac-atalho-hero .pac-atalho-sub { color: #b9c6dd; opacity: 1; }
        .pac-tag { background: #fdecd6; color: ${ORANGE_TX}; font-size: 11px; padding: 1px 7px; border-radius: 9px; font-weight: 500; }
        .pac-atalho-hero .pac-tag { background: ${ORANGE}; color: ${NAVY}; }

        .pac-paineis { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }

        .pac-filtros { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
        .pac-filtros label { display: grid; gap: 5px; font-size: 13px; color: ${GRAY}; }
        .pac-filtros input, .pac-filtros select { appearance: none; border: 1px solid #d8dee8; border-radius: 8px;
          padding: 8px 10px; font: inherit; font-size: 14px; background: #fff; color: #1b2333; min-width: 140px; }
        .pac-filtros input:focus, .pac-filtros select:focus { outline: none; border-color: ${ORANGE}; box-shadow: 0 0 0 3px rgba(236,139,28,0.18); }

        .pac-btn { appearance: none; font: inherit; font-size: 13px; padding: 8px 14px; border-radius: 8px; cursor: pointer; transition: filter .12s ease, background .12s ease; }
        .pac-btn:disabled { opacity: .55; cursor: not-allowed; }
        .pac-btn-primary { background: ${ORANGE}; color: #fff; border: none; font-weight: 500; }
        .pac-btn-primary:hover:not(:disabled) { filter: brightness(1.05); }
        .pac-btn-ghost { background: #fff; border: 1px solid #d8dee8; color: ${NAVY}; }
        .pac-btn-ghost:hover:not(:disabled) { background: #f1f4f8; }

        .pac-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        .pac-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
        .pac-tab { appearance: none; font: inherit; font-size: 13px; padding: 7px 13px; border-radius: 8px; cursor: pointer;
          background: #fff; border: 1px solid #d8dee8; color: ${NAVY}; }
        .pac-tab.active { background: ${NAVY}; border-color: ${NAVY}; color: #fff; }

        .pac-table { width: 100%; border-collapse: collapse; }
        .pac-table th { text-align: left; font-size: 12px; color: ${GRAY}; text-transform: uppercase; letter-spacing: 0.04em;
          font-weight: 500; padding: 8px 10px; border-bottom: 1px solid #e6eaf0; }
        .pac-table td { padding: 10px; border-bottom: 1px solid #eef1f5; font-size: 13.5px; vertical-align: middle; }
        .pac-table tbody tr:hover td { background: #f8fafc; }

        .pac-toast { padding: 10px 14px; border-radius: 8px; font-size: 13.5px; margin-bottom: 14px; }
        .pac-toast-ok { background: #e6f6ef; color: #0f6e56; border: 1px solid #b7e3d2; }
        .pac-toast-err { background: #fdeaea; color: #a32d2d; border: 1px solid #f3c2c2; }

        @media (max-width: 820px) {
          .pac-sidebar { width: 56px; padding: 14px 6px; }
          .pac-navlabel, .pac-navgroup-label, .pac-user-name { display: none; }
          .pac-navitem { justify-content: center; padding: 10px 0; }
          .pac-navitem.active { box-shadow: inset 0 -2px 0 ${ORANGE}; }
          .pac-badge { position: absolute; top: 3px; right: 4px; padding: 0 5px; }
          .pac-logo { justify-content: center; padding: 4px 0; }
          .pac-logo img { height: 24px; }
        }
      `}</style>
    </div>
  );
}
