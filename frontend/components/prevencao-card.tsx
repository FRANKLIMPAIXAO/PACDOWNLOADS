"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import {
  abrirComprovantePagamento,
  abrirPdfSituacao,
  consultarDte,
  Dte,
  detalharMensagem,
  gerarSituacaoFiscal,
  listarCaixaPostal,
  listarPagamentos,
  MensagemEcac,
  MensagemEcacDetalhe,
  obterProcuracao,
  obterUltimaSituacao,
  Pagamento,
  Procuracao,
  SituacaoFiscal,
  syncCaixaPostal,
  syncProcuracao,
} from "../lib/integra";

type Props = {
  empresaId: number;
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR");
  } catch {
    return iso;
  }
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function formatBrl(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function PrevencaoCard({ empresaId }: Props) {
  const [procuracao, setProcuracao] = useState<Procuracao | null>(null);
  const [procError, setProcError] = useState<string | null>(null);
  const [mensagens, setMensagens] = useState<MensagemEcac[] | null>(null);
  const [dte, setDte] = useState<Dte | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<MensagemEcacDetalhe | null>(null);
  const [situacao, setSituacao] = useState<SituacaoFiscal | null>(null);
  const [pagamentos, setPagamentos] = useState<Pagamento[] | null>(null);
  const [pagInicio, setPagInicio] = useState(isoDaysAgo(30));
  const [pagFim, setPagFim] = useState(isoToday());

  const reload = useCallback(async () => {
    setError(null);
    try {
      const msgs = await listarCaixaPostal(empresaId);
      setMensagens(msgs);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
    try {
      const proc = await obterProcuracao(empresaId);
      setProcuracao(proc);
      setProcError(null);
    } catch (err) {
      setProcuracao(null);
      if (err instanceof ApiError && err.status === 404) {
        setProcError("Nenhuma procuracao sincronizada ainda.");
      } else if (err instanceof ApiError) {
        setProcError(err.message);
      }
    }
    try {
      const d = await consultarDte(empresaId);
      setDte(d);
    } catch {
      setDte(null);
    }
    try {
      const s = await obterUltimaSituacao(empresaId);
      setSituacao(s);
    } catch {
      setSituacao(null);
    }
  }, [empresaId]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleSyncCaixa() {
    setBusy("caixa");
    setToast(null);
    setError(null);
    try {
      const r = await syncCaixaPostal(empresaId);
      setToast(
        `Caixa Postal: ${r.novas} novas, ${r.atualizadas} atualizadas, ${r.erros} erros.`,
      );
      await reload();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleSyncProcuracao() {
    setBusy("procuracao");
    setToast(null);
    setError(null);
    try {
      const p = await syncProcuracao(empresaId);
      setProcuracao(p);
      setProcError(null);
      setToast(`Procuracao sincronizada (${p.situacao}).`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleGerarSitfis() {
    setBusy("sitfis");
    setToast(null);
    setError(null);
    try {
      const s = await gerarSituacaoFiscal(empresaId);
      setSituacao(s);
      setToast(`Situacao fiscal gerada (id ${s.id}).`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleAbrirSitfisPdf() {
    if (!situacao) return;
    setBusy("sitfis-pdf");
    setError(null);
    try {
      await abrirPdfSituacao(empresaId, situacao.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao abrir PDF.");
    } finally {
      setBusy(null);
    }
  }

  async function handleListarPagamentos() {
    setBusy("pagamentos");
    setError(null);
    try {
      const p = await listarPagamentos(empresaId, pagInicio, pagFim);
      setPagamentos(p);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function handleAbrirComprovante(numero: string) {
    setBusy(`comp-${numero}`);
    setError(null);
    try {
      await abrirComprovantePagamento(empresaId, numero);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao baixar comprovante.");
    } finally {
      setBusy(null);
    }
  }

  async function handleAbrirDetalhe(isn: string) {
    setBusy(`msg-${isn}`);
    setError(null);
    try {
      const d = await detalharMensagem(empresaId, isn);
      setDetalhe(d);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  const naoLidas = (mensagens ?? []).filter((m) => m.indicador_leitura === "0").length;

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Prevencao (Integra Contador)</h3>
        <div className="page-actions">
          {procuracao?.situacao === "ATIVA" ? (
            <span className="pill pill-ok">Procuracao ativa</span>
          ) : (
            <span className="pill pill-warn">Procuracao pendente</span>
          )}
        </div>
      </header>

      <dl className="kv-grid">
        <dt>Procuracao eCAC</dt>
        <dd>
          {procuracao ? (
            <>
              {procuracao.situacao} · valida ate {procuracao.data_fim || "—"} ·{" "}
              <span className="muted">
                {procuracao.servicos_autorizados?.join(", ") || "—"}
              </span>
            </>
          ) : procError ? (
            <span className="muted">{procError}</span>
          ) : (
            <span className="muted">Carregando...</span>
          )}
        </dd>
        <dt>DTE</dt>
        <dd>
          {dte === null ? (
            <span className="muted">—</span>
          ) : dte.indicador_optante ? (
            <>
              <span className="pill pill-ok">Optante</span>{" "}
              <span className="muted">desde {dte.data_adesao || "—"}</span>
            </>
          ) : (
            <span className="pill pill-warn">Nao optante</span>
          )}
        </dd>
        <dt>Caixa Postal eCAC</dt>
        <dd>
          {mensagens === null ? (
            <span className="muted">Carregando...</span>
          ) : (
            <>
              {mensagens.length} mensagem(s) ·{" "}
              {naoLidas > 0 ? (
                <span className="pill pill-warn">{naoLidas} nao lidas</span>
              ) : (
                <span className="pill pill-ok">Tudo lido</span>
              )}
            </>
          )}
        </dd>
        <dt>Situacao fiscal</dt>
        <dd>
          {situacao ? (
            <>
              <span className="pill pill-ok">Gerada</span>{" "}
              <span className="muted">{formatDate(situacao.gerada_em)}</span>{" "}
              <button
                type="button"
                className="btn-secondary"
                style={{ padding: "4px 10px", fontSize: "0.82rem" }}
                onClick={handleAbrirSitfisPdf}
                disabled={busy === "sitfis-pdf"}
              >
                {busy === "sitfis-pdf" ? "..." : "Abrir PDF"}
              </button>
            </>
          ) : (
            <span className="muted">Nunca gerada.</span>
          )}
        </dd>
      </dl>

      <div className="page-actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={handleSyncProcuracao}
          disabled={busy === "procuracao"}
        >
          {busy === "procuracao" ? "Sincronizando..." : "Sincronizar procuracao"}
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={handleSyncCaixa}
          disabled={busy === "caixa"}
        >
          {busy === "caixa" ? "Sincronizando..." : "Sincronizar Caixa Postal"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={handleGerarSitfis}
          disabled={busy === "sitfis"}
        >
          {busy === "sitfis" ? "Gerando..." : "Gerar SITFIS"}
        </button>
      </div>

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      {mensagens && mensagens.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <p className="section-divider">Ultimas mensagens</p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {mensagens.slice(0, 8).map((m) => (
              <li
                key={m.id}
                style={{
                  padding: "10px 14px",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  background: "var(--surface-strong)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <strong>{m.assunto || "(sem assunto)"}</strong>
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      {m.remetente || "—"} · {formatDate(m.data_envio)}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    {m.indicador_leitura === "0" ? (
                      <span className="pill pill-warn">Nao lida</span>
                    ) : (
                      <span className="pill pill-muted">Lida</span>
                    )}
                    {m.indicador_relevancia ? (
                      <span className="pill pill-muted">{m.indicador_relevancia}</span>
                    ) : null}
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ padding: "6px 12px", fontSize: "0.85rem" }}
                      onClick={() => handleAbrirDetalhe(m.isn_msg)}
                      disabled={busy === `msg-${m.isn_msg}`}
                    >
                      {busy === `msg-${m.isn_msg}` ? "..." : "Abrir"}
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {detalhe ? (
        <div
          style={{
            marginTop: 12,
            padding: 16,
            border: "1px solid var(--border)",
            borderRadius: 14,
            background: "white",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <strong>{detalhe.assunto}</strong>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setDetalhe(null)}
            >
              Fechar
            </button>
          </div>
          {detalhe.conteudo_html ? (
            <div dangerouslySetInnerHTML={{ __html: detalhe.conteudo_html }} />
          ) : (
            <p className="muted">Sem conteudo.</p>
          )}
        </div>
      ) : null}

      <p className="section-divider" style={{ marginTop: 16 }}>Pagamentos (DARF/DAS)</p>
      <div
        className="form-grid"
        style={{ gridTemplateColumns: "160px 160px auto", alignItems: "end" }}
      >
        <label>
          <span>Data inicio</span>
          <input type="date" value={pagInicio} onChange={(e) => setPagInicio(e.target.value)} />
        </label>
        <label>
          <span>Data fim</span>
          <input type="date" value={pagFim} onChange={(e) => setPagFim(e.target.value)} />
        </label>
        <button
          type="button"
          className="btn-secondary"
          onClick={handleListarPagamentos}
          disabled={busy === "pagamentos"}
        >
          {busy === "pagamentos" ? "Buscando..." : "Listar pagamentos"}
        </button>
      </div>

      {pagamentos !== null ? (
        pagamentos.length === 0 ? (
          <p className="muted">Nenhum pagamento no periodo.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {pagamentos.map((p) => (
              <li
                key={p.numero_documento}
                style={{
                  padding: "10px 14px",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  background: "var(--surface-strong)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <div>
                  <strong>{p.descricao_receita || p.codigo_receita || "Receita"}</strong>
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    Doc {p.numero_documento} · {p.data_arrecadacao || "—"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <strong>{formatBrl(p.valor_total)}</strong>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ padding: "6px 12px", fontSize: "0.85rem" }}
                    onClick={() => handleAbrirComprovante(p.numero_documento || "")}
                    disabled={busy === `comp-${p.numero_documento}`}
                  >
                    {busy === `comp-${p.numero_documento}` ? "..." : "Comprovante"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}
