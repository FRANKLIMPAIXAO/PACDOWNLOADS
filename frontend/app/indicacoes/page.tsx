"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Indicacao, atualizarStatusIndicacao, listarIndicacoes } from "../../lib/indicacoes";

export default function IndicacoesPage() {
  return (
    <ProtectedRoute>
      <IndicacoesContent />
    </ProtectedRoute>
  );
}

type Filtro = "todas" | "nova" | "em_contato" | "convertida" | "descartada";

const STATUS_INFO: Record<string, { label: string; cls: string }> = {
  nova: { label: "Nova", cls: "pill-warn" },
  em_contato: { label: "Em contato", cls: "pill-info" },
  convertida: { label: "Convertida ✓", cls: "pill-ok" },
  descartada: { label: "Descartada", cls: "pill-muted" },
};

function dataBR(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function IndicacoesContent() {
  const [itens, setItens] = useState<Indicacao[] | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [erro, setErro] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      setItens(await listarIndicacoes(filtro === "todas" ? undefined : filtro));
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar indicações.");
    }
  }, [filtro]);

  useEffect(() => { carregar(); }, [carregar]);

  const contadores = useMemo(() => {
    const c = { nova: 0, em_contato: 0, convertida: 0, descartada: 0, total: 0 };
    if (filtro === "todas" && itens) {
      for (const i of itens) { c.total++; (c as Record<string, number>)[i.status] = ((c as Record<string, number>)[i.status] || 0) + 1; }
    }
    return c;
  }, [itens, filtro]);

  async function mudarStatus(id: number, status: string) {
    setBusyId(id);
    try {
      await atualizarStatusIndicacao(id, status);
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao atualizar status.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="page">
      <header className="page-header" style={{ alignItems: "center" }}>
        <div>
          <h2>🤝 PAC Indica</h2>
          <p className="muted">Indicações enviadas pelo formulário do portal. Entre em contato e marque o andamento.</p>
        </div>
        <button type="button" className="btn-secondary" onClick={carregar}>↻ Atualizar</button>
      </header>

      {erro ? <p className="toast toast-error">{erro}</p> : null}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {([
          ["todas", "Todas"],
          ["nova", "Novas"],
          ["em_contato", "Em contato"],
          ["convertida", "Convertidas"],
          ["descartada", "Descartadas"],
        ] as [Filtro, string][]).map(([k, label]) => (
          <button
            key={k}
            type="button"
            className={filtro === k ? "btn-primary" : "btn-secondary"}
            style={{ padding: "5px 11px", fontSize: "0.82rem" }}
            onClick={() => setFiltro(k)}
          >
            {label}
          </button>
        ))}
        {filtro === "todas" && contadores.total > 0 ? (
          <span className="muted" style={{ alignSelf: "center", fontSize: "0.82rem", marginLeft: 4 }}>
            {contadores.total} no total · {contadores.nova} nova(s) · {contadores.convertida} convertida(s)
          </span>
        ) : null}
      </div>

      {!itens ? (
        <p className="muted">Carregando…</p>
      ) : itens.length === 0 ? (
        <section className="panel"><p className="muted">Nenhuma indicação {filtro !== "todas" ? "neste filtro" : "ainda"}.</p></section>
      ) : (
        <section className="panel" style={{ overflow: "auto" }}>
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Recebida</th>
                <th>Quem indicou</th>
                <th>Quem foi indicado</th>
                <th>Observação</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Ação</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((i) => {
                const st = STATUS_INFO[i.status] || { label: i.status, cls: "pill-muted" };
                return (
                  <tr key={i.id}>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.8rem" }}>{dataBR(i.created_at)}</td>
                    <td>
                      <strong>{i.nome_indicador}</strong>
                      <div className="muted" style={{ fontSize: "0.78rem" }}>{i.contato_indicador}{i.empresa_indicador ? ` · ${i.empresa_indicador}` : ""}</div>
                    </td>
                    <td>
                      <strong>{i.nome_indicado}</strong>
                      <div className="muted" style={{ fontSize: "0.78rem" }}>{i.contato_indicado}</div>
                    </td>
                    <td style={{ fontSize: "0.82rem", maxWidth: 240 }}>{i.observacao || <span className="muted">—</span>}</td>
                    <td><span className={`pill ${st.cls}`}>{st.label}</span></td>
                    <td style={{ textAlign: "right" }}>
                      <select
                        value={i.status}
                        disabled={busyId === i.id}
                        onChange={(e) => mudarStatus(i.id, e.target.value)}
                        style={{ padding: "5px 8px", borderRadius: 8, fontSize: "0.8rem" }}
                      >
                        <option value="nova">Nova</option>
                        <option value="em_contato">Em contato</option>
                        <option value="convertida">Convertida</option>
                        <option value="descartada">Descartada</option>
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
