"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../lib/api";
import {
  getPortalToken,
  portalBaixarArquivo,
  portalDocumentos,
  portalLogout,
  portalMe,
  portalResumo,
  type PortalDocumento,
  type PortalMe,
  type PortalResumo,
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

// Período padrão: últimos 30 dias.
function hoje(): string {
  return new Date().toISOString().slice(0, 10);
}
function trintaDiasAtras(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

export default function PortalNotasPage() {
  const router = useRouter();
  const [me, setMe] = useState<PortalMe | null>(null);
  const [resumo, setResumo] = useState<PortalResumo | null>(null);
  const [docs, setDocs] = useState<PortalDocumento[]>([]);
  const [tipo, setTipo] = useState("");
  const [dataInicio, setDataInicio] = useState(trintaDiasAtras());
  const [dataFim, setDataFim] = useState(hoje());
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [baixando, setBaixando] = useState<string | null>(null);

  // Guard: sem token do portal → manda pro login.
  useEffect(() => {
    if (!getPortalToken()) {
      router.replace("/portal/login");
      return;
    }
    portalMe()
      .then(setMe)
      .catch(() => {
        portalLogout();
        router.replace("/portal/login");
      });
  }, [router]);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const params = { data_inicio: dataInicio, data_fim: dataFim };
      const [r, d] = await Promise.all([
        portalResumo(params),
        portalDocumentos({ ...params, tipo_documento: tipo || undefined, cancelada: false }),
      ]);
      setResumo(r);
      setDocs(d);
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao carregar as notas.");
    } finally {
      setLoading(false);
    }
  }, [dataInicio, dataFim, tipo]);

  useEffect(() => {
    if (getPortalToken()) carregar();
  }, [carregar]);

  async function baixar(doc: PortalDocumento, t: "xml" | "pdf") {
    const key = `${doc.id}-${t}`;
    setBaixando(key);
    setErro(null);
    try {
      await portalBaixarArquivo(doc.id, t);
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : `Falha ao baixar ${t.toUpperCase()}.`);
    } finally {
      setBaixando(null);
    }
  }

  function sair() {
    portalLogout();
    router.replace("/portal/login");
  }

  return (
    <div className="frame" style={{ padding: 24, maxWidth: 1200, margin: "0 auto" }}>
      {/* Cabeçalho do portal */}
      <header
        style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          gap: 16, flexWrap: "wrap", marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <img src="/logo.svg" alt="PAC" style={{ height: 36 }} />
          <div>
            <h2 style={{ margin: 0 }}>{me?.empresa?.razao_social || "Minhas Notas"}</h2>
            <p className="muted" style={{ margin: 0 }}>
              {me?.empresa?.cnpj ? `CNPJ ${me.empresa.cnpj}` : "Portal do Cliente"}
            </p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="muted">{me?.nome}</span>
          <button type="button" className="btn-ghost" onClick={sair}>Sair</button>
        </div>
      </header>

      {/* Filtros */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="form-grid" style={{ gridTemplateColumns: "160px 160px 160px auto", gap: 12, alignItems: "end" }}>
          <label>
            <span>Tipo</span>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos</option>
              <option value="NFE">NF-e / NFC-e</option>
              <option value="CTE">CT-e</option>
              <option value="NFSE">NFS-e</option>
            </select>
          </label>
          <label>
            <span>Emissão de</span>
            <input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
          </label>
          <label>
            <span>Emissão até</span>
            <input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
          </label>
          <button type="button" className="btn-primary" onClick={carregar} disabled={loading}>
            {loading ? "Buscando..." : "Atualizar"}
          </button>
        </div>
      </div>

      {/* Cards de resumo */}
      {resumo ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 16 }}>
          <div className="card" style={{ borderLeft: "3px solid rgb(16,185,129)" }}>
            <p className="muted" style={{ margin: 0 }}>Faturamento (emitidas)</p>
            <strong style={{ fontSize: 22, color: "rgb(16,185,129)" }}>{brl(resumo.faturamento)}</strong>
            <p className="muted" style={{ margin: 0 }}>{resumo.emitidas.ativas} notas de saída</p>
          </div>
          <div className="card" style={{ borderLeft: "3px solid rgb(59,130,246)" }}>
            <p className="muted" style={{ margin: 0 }}>Emitidas (saída)</p>
            <strong style={{ fontSize: 22 }}>{resumo.emitidas.total}</strong>
          </div>
          <div className="card" style={{ borderLeft: "3px solid rgb(168,85,247)" }}>
            <p className="muted" style={{ margin: 0 }}>Recebidas (entrada)</p>
            <strong style={{ fontSize: 22 }}>{resumo.recebidas.total}</strong>
          </div>
          <div className="card">
            <p className="muted" style={{ margin: 0 }}>Total geral</p>
            <strong style={{ fontSize: 22 }}>{resumo.total_geral}</strong>
          </div>
        </div>
      ) : null}

      {erro ? <p style={{ color: "rgb(248,113,113)" }}>{erro}</p> : null}

      {/* Tabela de notas */}
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          {loading ? "Carregando..." : `${docs.length} nota(s) no período (ativas).`}
        </p>
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Emissão</th>
                <th>Emitente / Destinatário</th>
                <th style={{ textAlign: "right" }}>Valor</th>
                <th style={{ textAlign: "center" }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.tipo_documento}</td>
                  <td>{dataBR(doc.data_emissao)}</td>
                  <td>{doc.origem === "emitida" ? (doc.nome_destinatario || "—") : (doc.nome_emitente || "—")}</td>
                  <td style={{ textAlign: "right" }}>{brl(doc.valor_total)}</td>
                  <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => baixar(doc, "xml")}
                      disabled={baixando === `${doc.id}-xml` || !doc.status || doc.status === "resumo"}
                      title={doc.status === "resumo" ? "XML ainda não disponível" : "Baixar XML"}
                    >
                      {baixando === `${doc.id}-xml` ? "..." : "XML"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => baixar(doc, "pdf")}
                      disabled={baixando === `${doc.id}-pdf` || doc.status === "resumo"}
                      title={doc.status === "resumo" ? "PDF ainda não disponível" : "Baixar PDF"}
                    >
                      {baixando === `${doc.id}-pdf` ? "..." : "PDF"}
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && docs.length === 0 ? (
                <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: 20 }}>Nenhuma nota no período.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
