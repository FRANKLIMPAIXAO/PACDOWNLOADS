"use client";

import { useEffect, useState } from "react";

import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth-context";
import { listarEmpresas, type Empresa } from "../../lib/empresas";
import {
  AdmissaoOffice,
  listarAdmissoes,
  reenviarAdmissao,
  reenviarPendentes,
} from "../../lib/admissoes";

export default function AdmissoesPage() {
  return (
    <ProtectedRoute>
      <AdmissoesContent />
    </ProtectedRoute>
  );
}

function statusInfo(s: string): { label: string; cls: string } {
  switch (s) {
    case "concluida": return { label: "Concluída", cls: "pill-ok" };
    case "em_analise": return { label: "Em análise", cls: "pill-info" };
    case "cancelada": return { label: "Cancelada", cls: "pill-warn" };
    default: return { label: "Nova", cls: "pill" };
  }
}

function AdmissoesContent() {
  const { user } = useAuth();
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [adms, setAdms] = useState<AdmissaoOffice[] | null>(null);
  const [pendentes, setPendentes] = useState(0);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => { listarEmpresas().then(setEmpresas).catch(() => setEmpresas([])); }, []);

  function carregar() {
    setAdms(null); setErro(null);
    listarAdmissoes(empresaId || undefined)
      .then((r) => { setAdms(r.admissoes); setPendentes(r.pendentes_envio); })
      .catch((e) => { setErro(e instanceof ApiError ? e.message : "Falha ao carregar."); setAdms([]); });
  }
  useEffect(() => { carregar(); /* eslint-disable-next-line */ }, [empresaId]);

  async function reenviarUm(a: AdmissaoOffice) {
    setBusy(`um-${a.id}`); setErro(null); setToast(null);
    try {
      const r = await reenviarAdmissao(a.id);
      if (r.enviado) { setToast(`Admissão de ${a.funcionario || a.id} reenviada ao PAC TAREFAS.`); carregar(); }
      else setErro(`Ainda não foi: ${r.erro || "erro desconhecido"}`);
    } catch (e) { setErro(e instanceof ApiError ? e.message : "Falha ao reenviar."); }
    finally { setBusy(null); }
  }

  async function reenviarTodas() {
    setBusy("todas"); setErro(null); setToast(null);
    try {
      const r = await reenviarPendentes();
      setToast(`Reenvio concluído: ${r.enviadas}/${r.tentadas} entregues.`);
      carregar();
    } catch (e) { setErro(e instanceof ApiError ? e.message : "Falha ao reenviar."); }
    finally { setBusy(null); }
  }

  function dataBR(iso: string | null): string {
    if (!iso) return "—";
    const d = new Date(iso.length > 10 ? iso : iso + "T00:00:00");
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("pt-BR");
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Admissões dos clientes</h2>
          <p className="muted">
            Solicitações de admissão que os clientes enviaram pelo portal. Elas vão pro PAC TAREFAS
            (webhook) — aqui você acompanha e <strong>reenvia</strong> se alguma não tiver chegado.
          </p>
        </div>
      </header>

      {toast ? <p className="toast toast-ok">{toast}</p> : null}
      {erro ? <p className="toast toast-error">{erro}</p> : null}

      {pendentes > 0 && user?.is_admin ? (
        <section className="panel" style={{ border: "1px solid rgba(245,158,11,0.5)", marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ color: "rgb(180,106,12)" }}>⚠️ {pendentes} admissão(ões) ainda não chegaram no PAC TAREFAS.</span>
          <button type="button" className="btn-primary" onClick={reenviarTodas} disabled={busy === "todas"}>
            {busy === "todas" ? "Reenviando..." : "↻ Reenviar pendentes"}
          </button>
        </section>
      ) : null}

      <section className="panel">
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Empresa</span>
            <select value={empresaId} onChange={(e) => setEmpresaId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Todas</option>
              {empresas.map((e) => <option key={e.id} value={e.id}>{e.razao_social}</option>)}
            </select>
          </label>
          <button type="button" className="btn-ghost" style={{ alignSelf: "end" }} onClick={carregar}>↻ Atualizar</button>
        </div>

        {adms === null ? (
          <p className="muted">Carregando...</p>
        ) : adms.length === 0 ? (
          <p className="muted">Nenhuma admissão solicitada ainda{empresaId ? " por esta empresa" : ""}.</p>
        ) : (
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Funcionário</th><th>Empresa</th><th>Cargo</th><th>Admissão</th>
                <th>Anexos</th><th>Status</th><th>Entregue</th><th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {adms.map((a) => {
                const s = statusInfo(a.status);
                return (
                  <tr key={a.id}>
                    <td>{a.funcionario || "—"}<div className="muted" style={{ fontSize: 11 }}>{a.cpf}</div></td>
                    <td>{a.empresa || `#${a.id}`}</td>
                    <td>{a.cargo || "—"}</td>
                    <td>{dataBR(a.data_admissao)}</td>
                    <td>{a.anexos > 0 ? `📎 ${a.anexos}` : "—"}</td>
                    <td><span className={`pill ${s.cls}`}>{s.label}</span></td>
                    <td>
                      {a.enviado
                        ? <span className="pill pill-ok">Sim</span>
                        : <span className="pill pill-warn" title={a.envio_erro || ""}>Pendente</span>}
                    </td>
                    <td>
                      {!a.enviado && user?.is_admin ? (
                        <button type="button" className="btn-ghost" onClick={() => reenviarUm(a)} disabled={busy === `um-${a.id}`}>
                          {busy === `um-${a.id}` ? "..." : "↻ Reenviar"}
                        </button>
                      ) : <span className="muted" style={{ fontSize: 12 }}>—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
