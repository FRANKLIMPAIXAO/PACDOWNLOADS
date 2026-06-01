"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ProtectedRoute } from "../../../../components/protected-route";
import { ApiError } from "../../../../lib/api";
import { obterEmpresa, Empresa } from "../../../../lib/empresas";
import {
  CaixaPostalResumo,
  MensagemEcac,
  MensagemEcacDetalhe,
  detalharMensagem,
  listarCaixaPostal,
  marcarMensagensLidas,
  resumoCaixaPostal,
  syncCaixaPostal,
} from "../../../../lib/integra";

type FiltroLeitura = "todas" | "nao_lidas" | "lidas";
type FiltroRelevancia = "todas" | "alta" | "media" | "baixa";

const RELEV_LABEL: Record<string, string> = {
  "1": "Alta",
  "2": "Média",
  "3": "Baixa",
};

const RELEV_CLASS: Record<string, string> = {
  "1": "pill pill-err",
  "2": "pill pill-warn",
  "3": "pill pill-muted",
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("pt-BR");
  } catch {
    return iso;
  }
}

export default function CaixaPostalPage() {
  return (
    <ProtectedRoute>
      <CaixaPostalContent />
    </ProtectedRoute>
  );
}

function CaixaPostalContent() {
  const params = useParams<{ id: string }>();
  const empresaId = Number(params.id);

  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const [mensagens, setMensagens] = useState<MensagemEcac[] | null>(null);
  const [resumo, setResumo] = useState<CaixaPostalResumo | null>(null);
  const [detalhes, setDetalhes] = useState<Record<string, MensagemEcacDetalhe>>({});
  const [expandida, setExpandida] = useState<string | null>(null);
  const [filtroLeitura, setFiltroLeitura] = useState<FiltroLeitura>("todas");
  const [filtroRelev, setFiltroRelev] = useState<FiltroRelevancia>("todas");
  const [busca, setBusca] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [emp, msgs, res] = await Promise.all([
        obterEmpresa(empresaId),
        listarCaixaPostal(empresaId),
        resumoCaixaPostal(empresaId),
      ]);
      setEmpresa(emp);
      setMensagens(msgs);
      setResumo(res);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao carregar caixa postal.");
    }
  }, [empresaId]);

  useEffect(() => {
    if (!Number.isFinite(empresaId)) return;
    reload();
  }, [empresaId, reload]);

  async function handleSync() {
    setBusy("sync");
    setError(null);
    setToast(null);
    try {
      const r = await syncCaixaPostal(empresaId);
      setToast(
        `Sync: ${r.sincronizadas} mensagens · ${r.novas} novas · ${r.atualizadas} atualizadas`
      );
      await reload();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao sincronizar.");
    } finally {
      setBusy(null);
    }
  }

  async function handleMarcarTodasLidas() {
    if (!confirm("Marcar TODAS as mensagens como lidas localmente?")) return;
    setBusy("marcar-lidas");
    setError(null);
    setToast(null);
    try {
      const r = await marcarMensagensLidas(empresaId);
      setToast(`${r.marcadas} mensagens marcadas como lidas.`);
      await reload();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao marcar lidas.");
    } finally {
      setBusy(null);
    }
  }

  async function handleExpandir(isn: string) {
    if (expandida === isn) {
      setExpandida(null);
      return;
    }
    setExpandida(isn);
    if (detalhes[isn]) return; // ja carregado
    setBusy(`det-${isn}`);
    try {
      const d = await detalharMensagem(empresaId, isn);
      setDetalhes((prev) => ({ ...prev, [isn]: d }));
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao carregar detalhe.");
    } finally {
      setBusy(null);
    }
  }

  // Aplicacao dos filtros
  const filtradas = useMemo(() => {
    if (!mensagens) return [];
    return mensagens.filter((m) => {
      if (filtroLeitura === "nao_lidas" && m.indicador_leitura === "1") return false;
      if (filtroLeitura === "lidas" && m.indicador_leitura !== "1") return false;
      if (filtroRelev !== "todas") {
        const map = { alta: "1", media: "2", baixa: "3" };
        if (m.indicador_relevancia !== map[filtroRelev]) return false;
      }
      if (busca) {
        const b = busca.toLowerCase();
        const a = (m.assunto || "").toLowerCase();
        const r = (m.remetente || "").toLowerCase();
        if (!a.includes(b) && !r.includes(b)) return false;
      }
      return true;
    });
  }, [mensagens, filtroLeitura, filtroRelev, busca]);

  if (error && !mensagens) {
    return (
      <section className="panel">
        <p className="toast toast-error">{error}</p>
        <Link href={`/empresas/${empresaId}`} className="btn-secondary" style={{ marginTop: 16 }}>
          ← Voltar
        </Link>
      </section>
    );
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="muted" style={{ margin: 0 }}>
            <Link href={`/empresas/${empresaId}`} className="row-link">
              ← {empresa?.razao_social || "Empresa"}
            </Link>
          </p>
          <h2>Caixa Postal eCAC</h2>
          <p className="muted">Mensagens da Receita Federal via Integra Contador (Serpro).</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleSync}
            disabled={busy === "sync"}
          >
            {busy === "sync" ? "Sincronizando..." : "🔄 Sincronizar"}
          </button>
        </div>
      </header>

      {/* Cards de resumo */}
      {resumo ? (
        <section className="grid" style={{ marginBottom: 8 }}>
          <article className="metric metric--cyan">
            <span>Total</span>
            <strong>{resumo.total}</strong>
            <p>mensagens sincronizadas</p>
          </article>
          <article className={resumo.nao_lidas > 0 ? "metric metric--amber" : "metric metric--emerald"}>
            <span>Não lidas</span>
            <strong>{resumo.nao_lidas}</strong>
            <p>{resumo.lidas} ja lidas</p>
          </article>
          <article className={resumo.alta_relevancia_nao_lidas > 0 ? "metric metric--rose" : "metric metric--emerald"}>
            <span>Alta relevância</span>
            <strong>{resumo.alta_relevancia}</strong>
            <p>{resumo.alta_relevancia_nao_lidas} alta NÃO lida{resumo.alta_relevancia_nao_lidas === 1 ? "" : "s"}</p>
          </article>
        </section>
      ) : null}

      {/* Filtros */}
      <section className="panel" style={{ padding: "12px 14px", marginBottom: 8 }}>
        <div className="form-grid" style={{ gridTemplateColumns: "1fr 140px 140px auto", alignItems: "end" }}>
          <label>
            <span>Buscar</span>
            <input
              type="text"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="assunto, remetente..."
            />
          </label>
          <label>
            <span>Leitura</span>
            <select
              value={filtroLeitura}
              onChange={(e) => setFiltroLeitura(e.target.value as FiltroLeitura)}
            >
              <option value="todas">Todas</option>
              <option value="nao_lidas">Não lidas</option>
              <option value="lidas">Lidas</option>
            </select>
          </label>
          <label>
            <span>Relevância</span>
            <select
              value={filtroRelev}
              onChange={(e) => setFiltroRelev(e.target.value as FiltroRelevancia)}
            >
              <option value="todas">Todas</option>
              <option value="alta">Alta</option>
              <option value="media">Média</option>
              <option value="baixa">Baixa</option>
            </select>
          </label>
          <div>
            <button
              type="button"
              className="btn-secondary"
              onClick={handleMarcarTodasLidas}
              disabled={busy === "marcar-lidas" || (resumo?.nao_lidas ?? 0) === 0}
              title="Marca TODAS as mensagens como lidas no sistema local"
            >
              ✓ Marcar todas como lidas
            </button>
          </div>
        </div>
      </section>

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      {!mensagens ? (
        <section className="panel"><p className="muted">Carregando mensagens...</p></section>
      ) : mensagens.length === 0 ? (
        <section className="panel">
          <div className="empty-state">
            Nenhuma mensagem sincronizada. Clique em <strong>Sincronizar</strong> para puxar
            da Receita Federal via Integra Contador.
          </div>
        </section>
      ) : (
        <section className="panel">
          <p className="muted" style={{ margin: "0 0 12px 0", fontSize: "0.85rem" }}>
            {filtradas.length} de {mensagens.length} mensagem(s)
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
            {filtradas.map((m) => {
              const naoLida = m.indicador_leitura !== "1";
              const isOpen = expandida === m.isn_msg;
              const det = detalhes[m.isn_msg];
              return (
                <li
                  key={m.isn_msg}
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    background: naoLida ? "var(--bg-0)" : "var(--bg-1)",
                    overflow: "hidden",
                  }}
                >
                  {/* Cabecalho clicavel */}
                  <button
                    type="button"
                    onClick={() => handleExpandir(m.isn_msg)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "10px 14px",
                      background: "transparent",
                      border: "none",
                      color: "var(--text)",
                      cursor: "pointer",
                      display: "grid",
                      gridTemplateColumns: "auto 100px 80px 1fr auto",
                      gap: 12,
                      alignItems: "center",
                    }}
                  >
                    <span style={{ fontSize: "0.78rem", color: naoLida ? "var(--accent)" : "var(--muted)" }}>
                      {naoLida ? "●" : "○"}
                    </span>
                    <span style={{ fontSize: "0.82rem", color: "var(--muted)" }}>
                      {formatDate(m.data_envio)}
                    </span>
                    <span className={RELEV_CLASS[m.indicador_relevancia || "3"] || "pill"}>
                      {RELEV_LABEL[m.indicador_relevancia || "3"] || "—"}
                    </span>
                    <span style={{ fontWeight: naoLida ? 600 : 400 }}>
                      {m.assunto || "(sem assunto)"}
                    </span>
                    <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
                      {isOpen ? "▲" : "▼"}
                    </span>
                  </button>

                  {/* Conteudo expandido */}
                  {isOpen ? (
                    <div
                      style={{
                        padding: "12px 14px",
                        borderTop: "1px solid var(--border)",
                        background: "var(--bg-2, var(--bg-1))",
                      }}
                    >
                      <dl className="kv-grid" style={{ marginBottom: 12 }}>
                        <dt>Remetente</dt><dd>{m.remetente || "—"}</dd>
                        <dt>Data envio</dt><dd>{formatDate(m.data_envio)}</dd>
                        <dt>ISN</dt><dd><code style={{ fontSize: "0.78rem" }}>{m.isn_msg}</code></dd>
                      </dl>
                      {busy === `det-${m.isn_msg}` ? (
                        <p className="muted">Carregando conteúdo...</p>
                      ) : det?.conteudo_html ? (
                        <div
                          style={{
                            background: "white",
                            color: "black",
                            padding: 14,
                            borderRadius: 6,
                            maxHeight: 400,
                            overflow: "auto",
                            fontSize: "0.86rem",
                          }}
                          // Conteudo vem da Receita Federal — sanitizado pelo backend
                          dangerouslySetInnerHTML={{ __html: det.conteudo_html }}
                        />
                      ) : (
                        <p className="muted">Sem conteúdo HTML disponível.</p>
                      )}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </>
  );
}
