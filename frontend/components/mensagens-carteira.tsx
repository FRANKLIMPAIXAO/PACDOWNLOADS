"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "../lib/api";
import {
  MensagensResumo,
  atualizarMensagens,
  mensagensResumo,
  statusAtualizarMensagens,
} from "../lib/mensagens";

/** Aba MENSAGENS do /prevencao: Caixa Postal (e-CAC) da carteira, por tipo. */
export function MensagensCarteira() {
  const [resumo, setResumo] = useState<MensagensResumo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tipoFiltro, setTipoFiltro] = useState<string>("");
  const [soNaoLidas, setSoNaoLidas] = useState(false);
  const [sync, setSync] = useState<{ rodando: boolean; texto: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const carregar = useCallback(async () => {
    setError(null);
    try {
      setResumo(await mensagensResumo());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao carregar mensagens.");
    }
  }, []);

  useEffect(() => {
    carregar();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [carregar]);

  async function handleSincronizar() {
    setError(null);
    try {
      const { job_id } = await atualizarMensagens();
      setSync({ rodando: true, texto: "Iniciando…" });
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const j = await statusAtualizarMensagens(job_id);
          if (j.status === "rodando") {
            setSync({
              rodando: true,
              texto: `${j.feitas}/${j.total} — ${j.atual ?? "…"} (${j.sucesso} ok · ${j.falhas} falha)`,
            });
          } else {
            if (pollRef.current) clearInterval(pollRef.current);
            setSync({
              rodando: false,
              texto:
                j.status === "erro"
                  ? `Erro: ${j.erro_geral ?? "falha geral"}`
                  : `Concluído: ${j.sucesso} sincronizadas · ${j.falhas} falha(s).`,
            });
            await carregar();
          }
        } catch {
          /* status transitório — segue tentando */
        }
      }, 3000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao iniciar a sincronização.");
    }
  }

  const itens = useMemo(() => {
    if (!resumo) return [];
    return resumo.mensagens.filter(
      (m) => (!tipoFiltro || m.tipo === tipoFiltro) && (!soNaoLidas || m.nao_lida),
    );
  }, [resumo, tipoFiltro, soNaoLidas]);

  return (
    <>
      <header className="page-header" style={{ alignItems: "center" }}>
        <div>
          <h3 style={{ margin: 0 }}>Mensagens do e-CAC</h3>
          <p className="muted" style={{ margin: 0 }}>
            Caixa Postal da carteira — Termo de Intimação, Exclusão do Simples, Malha Fiscal.
          </p>
        </div>
        <div className="page-actions" style={{ alignItems: "center", gap: 10 }}>
          {sync ? (
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              {sync.rodando ? "⏳ " : "✅ "}
              {sync.texto}
            </span>
          ) : null}
          <button
            type="button"
            className="btn-primary"
            onClick={handleSincronizar}
            disabled={sync?.rodando}
          >
            {sync?.rodando ? "Sincronizando…" : "🔄 Atualizar mensagens (Integra)"}
          </button>
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      {resumo === null ? (
        <section className="panel"><p className="muted">Carregando…</p></section>
      ) : resumo.total_mensagens === 0 ? (
        <section className="panel">
          <p style={{ marginTop: 0 }}>
            <strong>Nenhuma mensagem sincronizada ainda.</strong>
          </p>
          <p className="muted">
            Clique em <strong>Atualizar mensagens</strong> pra puxar a Caixa Postal do e-CAC
            de toda a carteira (via Integra Contador — custa chamadas, roda em segundo plano).
          </p>
        </section>
      ) : (
        <>
          <p className="muted" style={{ marginTop: -4, marginBottom: 10, fontSize: "0.9rem" }}>
            {resumo.total_mensagens} mensagens · <strong>{resumo.total_nao_lidas}</strong> não lidas ·{" "}
            {resumo.total_relevantes_nao_lidas} relevantes não lidas
          </p>

          {/* Cards por tipo */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
              gap: 12,
              marginBottom: 16,
            }}
          >
            {resumo.por_tipo.map((t) => {
              const ativo = tipoFiltro === t.tipo;
              return (
                <button
                  key={t.tipo}
                  type="button"
                  onClick={() => setTipoFiltro(ativo ? "" : t.tipo)}
                  className="panel"
                  style={{
                    textAlign: "left",
                    cursor: "pointer",
                    borderColor: ativo ? "var(--primary)" : undefined,
                    outline: ativo ? "2px solid var(--primary)" : "none",
                  }}
                  title="Clique pra filtrar a lista por este tipo"
                >
                  <div className="muted" style={{ fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: 0.4 }}>
                    {t.tipo}
                  </div>
                  <div style={{ fontSize: "1.7rem", fontWeight: 700, lineHeight: 1.1 }}>
                    {t.nao_lidas}
                    <span className="muted" style={{ fontSize: "0.9rem", fontWeight: 400 }}> não lidas</span>
                  </div>
                  <div className="muted" style={{ fontSize: "0.82rem" }}>
                    {t.empresas} empresa(s) · {t.total} no total
                    {t.relevantes_nao_lidas > 0 ? (
                      <span style={{ color: "rgb(248,113,113)" }}> · {t.relevantes_nao_lidas} relevante(s)</span>
                    ) : null}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Filtros da lista */}
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span className="muted" style={{ fontSize: "0.85rem" }}>Tipo:</span>
              <select value={tipoFiltro} onChange={(e) => setTipoFiltro(e.target.value)}>
                <option value="">Todos</option>
                {resumo.por_tipo.map((t) => (
                  <option key={t.tipo} value={t.tipo}>{t.tipo}</option>
                ))}
              </select>
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={soNaoLidas} onChange={(e) => setSoNaoLidas(e.target.checked)} />
              <span className="muted" style={{ fontSize: "0.85rem" }}>Só não lidas</span>
            </label>
            <span className="muted" style={{ fontSize: "0.82rem", marginLeft: "auto" }}>
              {itens.length} mensagem(ns){resumo.mensagens.length >= 400 ? " (amostra recente)" : ""}
            </span>
          </div>

          <section className="panel" style={{ padding: 0, overflowX: "auto" }}>
            <table className="data-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Empresa</th>
                  <th>Tipo</th>
                  <th>Assunto</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                {itens.map((m) => (
                  <tr key={`${m.empresa_id}-${m.isn_msg}`} style={{ opacity: m.nao_lida ? 1 : 0.6 }}>
                    <td>
                      <Link href={`/empresas/${m.empresa_id}/caixa-postal`} className="row-link">
                        {m.empresa}
                      </Link>
                    </td>
                    <td>
                      <span className="pill pill-muted" style={{ whiteSpace: "nowrap" }}>{m.tipo}</span>
                    </td>
                    <td>
                      {m.nao_lida ? <strong>● </strong> : null}
                      {m.relevante ? "🔴 " : ""}
                      {m.assunto || <span className="muted">—</span>}
                    </td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>
                      {m.data_envio ? new Date(m.data_envio).toLocaleDateString("pt-BR") : "—"}
                    </td>
                  </tr>
                ))}
                {itens.length === 0 ? (
                  <tr><td colSpan={4} className="muted" style={{ padding: 16 }}>Nenhuma mensagem com esse filtro.</td></tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
