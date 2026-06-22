"use client";

import { useEffect, useState } from "react";

import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth-context";
import { listarEmpresas, type Empresa } from "../../lib/empresas";
import {
  DocEscritorioOffice,
  excluirDocEscritorio,
  listarDocsEscritorio,
} from "../../lib/documentos-escritorio";

export default function DocsClientePage() {
  return (
    <ProtectedRoute>
      <DocsClienteContent />
    </ProtectedRoute>
  );
}

function tipoLabel(t: string): string {
  const m: Record<string, string> = {
    guia: "Guia / imposto", relatorio: "Relatório", comunicado: "Comunicado",
    contrato: "Contrato", contrato_social: "Contrato social", alvara: "Alvará",
    certificado: "Certificado", procuracao: "Procuração", licenca: "Licença",
  };
  return m[t] || "Documento";
}

function DocsClienteContent() {
  const { user } = useAuth();
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [docs, setDocs] = useState<DocEscritorioOffice[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState<number | null>(null);

  useEffect(() => {
    listarEmpresas().then(setEmpresas).catch(() => setEmpresas([]));
  }, []);

  function carregar() {
    setDocs(null); setErro(null);
    listarDocsEscritorio(empresaId || undefined)
      .then((r) => setDocs(r.documentos))
      .catch((e) => { setErro(e instanceof ApiError ? e.message : "Falha ao carregar."); setDocs([]); });
  }

  useEffect(() => { carregar(); /* eslint-disable-next-line */ }, [empresaId]);

  async function excluir(d: DocEscritorioOffice) {
    if (!window.confirm(`Excluir "${d.titulo}" da área do cliente ${d.empresa || ""}? Esta ação não tem volta — o cliente deixa de ver este documento.`)) return;
    setExcluindo(d.id); setErro(null); setToast(null);
    try {
      await excluirDocEscritorio(d.id);
      setToast(`"${d.titulo}" foi removido da área do cliente.`);
      setDocs((cur) => (cur || []).filter((x) => x.id !== d.id));
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao excluir.");
    } finally { setExcluindo(null); }
  }

  function dataBR(iso: string | null): string {
    if (!iso) return "—";
    const dt = new Date(iso);
    return Number.isNaN(dt.getTime()) ? iso : dt.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Documentos do cliente</h2>
          <p className="muted">
            Documentos que o escritório (PAC TAREFAS) enviou pra área do cliente. Se algum foi
            enviado errado, exclua aqui — sai da visão do cliente na hora.
          </p>
        </div>
      </header>

      {toast ? <p className="toast toast-ok">{toast}</p> : null}
      {erro ? <p className="toast toast-error">{erro}</p> : null}

      <section className="panel">
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Empresa</span>
            <select value={empresaId} onChange={(e) => setEmpresaId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Todas</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.id}>{e.razao_social}</option>
              ))}
            </select>
          </label>
          <button type="button" className="btn-ghost" style={{ alignSelf: "end" }} onClick={carregar}>↻ Atualizar</button>
        </div>

        {docs === null ? (
          <p className="muted">Carregando...</p>
        ) : docs.length === 0 ? (
          <p className="muted">Nenhum documento enviado ainda{empresaId ? " para esta empresa" : ""}.</p>
        ) : (
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Empresa</th><th>Tipo</th><th>Documento</th><th>Competência</th>
                <th>Enviado</th><th>Lido</th><th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>{d.empresa || `#${d.empresa_id}`}<div className="muted" style={{ fontSize: 11 }}>{d.cnpj}</div></td>
                  <td><span className="pill pill-info">{tipoLabel(d.tipo)}</span></td>
                  <td>{d.titulo}</td>
                  <td>{d.competencia || "—"}</td>
                  <td>{dataBR(d.enviado_em)}</td>
                  <td>{d.lido ? <span className="pill pill-ok">Lido</span> : <span className="pill">Não lido</span>}</td>
                  <td>
                    {user?.is_admin ? (
                      <button type="button" className="btn-ghost" style={{ color: "rgb(220,38,38)" }} onClick={() => excluir(d)} disabled={excluindo === d.id}>
                        {excluindo === d.id ? "Excluindo..." : "🗑 Excluir"}
                      </button>
                    ) : <span className="muted" style={{ fontSize: 12 }}>só admin exclui</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
