"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatThread } from "../../components/chat-thread";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { listarEmpresas, type Empresa } from "../../lib/empresas";
import {
  Conversa,
  ThreadEmpresa,
  enviarMensagemEmpresa,
  listarConversas,
  threadEmpresa,
} from "../../lib/mensagens-chat";

export default function ConversasPage() {
  return (
    <ProtectedRoute>
      <ConversasContent />
    </ProtectedRoute>
  );
}

function quando(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const hoje = new Date();
  const mesmoDia = d.toDateString() === hoje.toDateString();
  return mesmoDia
    ? d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function ConversasContent() {
  const [conversas, setConversas] = useState<Conversa[] | null>(null);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [thread, setThread] = useState<ThreadEmpresa | null>(null);
  const [carregandoThread, setCarregandoThread] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [filtro, setFiltro] = useState("");
  const [novaEmpresa, setNovaEmpresa] = useState("");
  const selRef = useRef<number | null>(null);
  selRef.current = sel;

  const carregarConversas = useCallback(async () => {
    try {
      const r = await listarConversas();
      setConversas(r.conversas);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar conversas.");
    }
  }, []);

  const carregarThread = useCallback(async (empresaId: number, comSpinner = true) => {
    if (comSpinner) setCarregandoThread(true);
    try {
      const t = await threadEmpresa(empresaId);
      // Só aplica se ainda for a empresa selecionada (evita corrida no polling).
      if (selRef.current === empresaId) setThread(t);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao abrir a conversa.");
    } finally {
      if (comSpinner) setCarregandoThread(false);
    }
  }, []);

  useEffect(() => {
    carregarConversas();
    listarEmpresas().then(setEmpresas).catch(() => setEmpresas([]));
  }, [carregarConversas]);

  // Polling: atualiza a lista e a thread aberta a cada 12s (marca lidas ao abrir).
  useEffect(() => {
    const t = setInterval(() => {
      carregarConversas();
      if (selRef.current) carregarThread(selRef.current, false);
    }, 12000);
    return () => clearInterval(t);
  }, [carregarConversas, carregarThread]);

  function abrir(empresaId: number) {
    setSel(empresaId);
    setThread(null);
    carregarThread(empresaId).then(carregarConversas); // recarrega p/ zerar o badge
  }

  async function enviar(corpo: string) {
    if (!sel) return;
    await enviarMensagemEmpresa(sel, corpo);
    await carregarThread(sel, false);
    await carregarConversas();
  }

  const conversasFiltradas = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    const lista = conversas || [];
    if (!q) return lista;
    return lista.filter((c) => c.empresa_razao_social.toLowerCase().includes(q) || (c.empresa_cnpj || "").includes(q));
  }, [conversas, filtro]);

  const empresasParaNova = useMemo(() => {
    const q = novaEmpresa.trim().toLowerCase();
    if (!q) return [];
    return empresas
      .filter((e) => (e.razao_social || "").toLowerCase().includes(q) || (e.cnpj || "").includes(q))
      .slice(0, 8);
  }, [empresas, novaEmpresa]);

  return (
    <>
      <header className="page-header">
        <div>
          <h2>💬 Conversas</h2>
          <p className="muted">Fale com os clientes pelo portal — cada empresa tem sua conversa.</p>
        </div>
      </header>

      {erro ? <p className="toast toast-error">{erro}</p> : null}

      <div style={{ display: "flex", gap: 14, alignItems: "stretch", flexWrap: "wrap" }}>
        {/* Lista de conversas */}
        <section className="panel" style={{ flex: "1 1 300px", maxWidth: 380, minWidth: 260, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column", maxHeight: 560 }}>
          <div style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
            <input
              placeholder="Buscar conversa…"
              value={filtro}
              onChange={(e) => setFiltro(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 14 }}
            />
            {/* Iniciar nova conversa com qualquer empresa */}
            <details style={{ marginTop: 8 }}>
              <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--muted-strong)" }}>＋ Nova conversa</summary>
              <input
                placeholder="Empresa por nome ou CNPJ…"
                value={novaEmpresa}
                onChange={(e) => setNovaEmpresa(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 14, marginTop: 6 }}
              />
              {empresasParaNova.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  className="btn-ghost"
                  style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 8px", fontSize: 13 }}
                  onClick={() => { setNovaEmpresa(""); abrir(e.id); }}
                >
                  {e.razao_social} <span className="muted" style={{ fontSize: 11 }}>{e.cnpj}</span>
                </button>
              ))}
            </details>
          </div>

          <div style={{ overflowY: "auto", flex: 1 }}>
            {conversas === null ? (
              <p className="muted" style={{ padding: 14 }}>Carregando…</p>
            ) : conversasFiltradas.length === 0 ? (
              <p className="muted" style={{ padding: 14, fontSize: 13 }}>
                Nenhuma conversa ainda. Use <strong>＋ Nova conversa</strong> pra iniciar.
              </p>
            ) : (
              conversasFiltradas.map((c) => (
                <button
                  key={c.empresa_id}
                  type="button"
                  onClick={() => abrir(c.empresa_id)}
                  style={{
                    display: "block", width: "100%", textAlign: "left", padding: "11px 13px",
                    background: sel === c.empresa_id ? "var(--surface-hover)" : "transparent",
                    border: "none", borderBottom: "1px solid var(--border)", cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-strong)", fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {c.empresa_razao_social}
                    </span>
                    <span className="muted" style={{ fontSize: 11, flexShrink: 0 }}>{quando(c.ultima_em)}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginTop: 2 }}>
                    <span className="muted" style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {c.ultimo_autor === "escritorio" ? "Você: " : ""}{c.ultima_mensagem}
                    </span>
                    {c.nao_lidas > 0 ? (
                      <span style={{ flexShrink: 0, background: "#e8871e", color: "#fff", borderRadius: 999, fontSize: 11, fontWeight: 700, minWidth: 18, height: 18, display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0 5px" }}>
                        {c.nao_lidas}
                      </span>
                    ) : null}
                  </div>
                </button>
              ))
            )}
          </div>
        </section>

        {/* Thread aberta */}
        <section style={{ flex: "2 1 420px", minWidth: 300 }}>
          {sel === null ? (
            <div className="panel" style={{ height: 560, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <p className="muted">Selecione uma conversa à esquerda ou inicie uma nova.</p>
            </div>
          ) : (
            <>
              <div style={{ marginBottom: 8 }}>
                <strong style={{ color: "var(--text-strong)" }}>{thread?.empresa_razao_social || "…"}</strong>
                {thread?.empresa_cnpj ? <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>CNPJ {thread.empresa_cnpj}</span> : null}
              </div>
              <ChatThread
                mensagens={thread?.mensagens || []}
                meuLado="escritorio"
                onEnviar={enviar}
                carregando={carregandoThread}
                altura={520}
                vazioLabel="Nenhuma mensagem com esta empresa ainda. Escreva a primeira 👇"
              />
            </>
          )}
        </section>
      </div>
    </>
  );
}
