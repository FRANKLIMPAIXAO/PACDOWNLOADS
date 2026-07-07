"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

// Mensagem única — formato normalizado pelo backend (PacChat usa id string/uuid).
export type ChatMensagem = {
  id: string | number;
  autor: "escritorio" | "cliente";
  autor_nome: string | null;
  corpo: string;
  created_at: string | null;
};

function horaBR(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/**
 * Thread de conversa estilo WhatsApp. Painel com fundo PRÓPRIO — funciona tanto
 * embutido no tema escuro do escritório quanto no tema claro do portal, sem
 * herdar cores do pai. `meuLado` define qual bolha vai pra direita (minhas).
 */
export function ChatThread({
  mensagens,
  meuLado,
  onEnviar,
  carregando,
  vazioLabel,
  altura = 460,
}: {
  mensagens: ChatMensagem[];
  meuLado: "escritorio" | "cliente";
  onEnviar: (corpo: string) => Promise<void>;
  carregando?: boolean;
  vazioLabel?: string;
  altura?: number;
}) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  // Rola pro fim quando chega mensagem nova.
  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens.length]);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    const corpo = texto.trim();
    if (!corpo || enviando) return;
    setEnviando(true);
    try {
      await onEnviar(corpo);
      setTexto("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", height: altura,
        borderRadius: 14, overflow: "hidden", border: "1px solid rgba(0,0,0,0.10)",
        background: "#efe9e1", // tom quente tipo WhatsApp, neutro pros dois temas
      }}
    >
      {/* Mensagens */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
        {carregando ? (
          <p style={{ color: "#6b7280", textAlign: "center", marginTop: 20 }}>Carregando conversa…</p>
        ) : mensagens.length === 0 ? (
          <p style={{ color: "#6b7280", textAlign: "center", marginTop: 24, fontSize: 14 }}>
            {vazioLabel || "Nenhuma mensagem ainda. Escreva a primeira 👇"}
          </p>
        ) : (
          mensagens.map((m) => {
            const minha = m.autor === meuLado;
            return (
              <div key={m.id} style={{ display: "flex", justifyContent: minha ? "flex-end" : "flex-start" }}>
                <div
                  style={{
                    maxWidth: "76%", padding: "8px 11px 6px", borderRadius: 12,
                    background: minha ? "#e8871e" : "#ffffff",
                    color: minha ? "#ffffff" : "#1f2937",
                    boxShadow: "0 1px 1px rgba(0,0,0,0.12)",
                    borderTopRightRadius: minha ? 3 : 12,
                    borderTopLeftRadius: minha ? 12 : 3,
                  }}
                >
                  {!minha && m.autor_nome ? (
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#14284a", marginBottom: 2 }}>
                      {m.autor === "escritorio" ? "🏢 " : ""}{m.autor_nome}
                    </div>
                  ) : null}
                  <div style={{ fontSize: 14, whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.4 }}>
                    {m.corpo}
                  </div>
                  <div style={{ fontSize: 10, textAlign: "right", marginTop: 2, opacity: 0.7 }}>
                    {horaBR(m.created_at)}
                  </div>
                </div>
              </div>
            );
          })
        )}
        <div ref={fimRef} />
      </div>

      {/* Composer */}
      <form onSubmit={enviar} style={{ display: "flex", gap: 8, padding: 10, background: "#f7f4ef", borderTop: "1px solid rgba(0,0,0,0.08)" }}>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            // Enter envia; Shift+Enter quebra linha (igual WhatsApp web).
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(e as unknown as FormEvent); }
          }}
          placeholder="Escreva uma mensagem…"
          rows={1}
          style={{
            flex: 1, resize: "none", maxHeight: 120, padding: "10px 12px", borderRadius: 10,
            border: "1px solid #d7dbe6", fontSize: 14, fontFamily: "inherit", color: "#1f2937", background: "#fff",
          }}
        />
        <button
          type="submit"
          disabled={enviando || !texto.trim()}
          style={{
            border: "none", borderRadius: 10, padding: "0 18px", cursor: "pointer",
            background: "#e8871e", color: "#fff", fontWeight: 700, fontSize: 14,
            opacity: enviando || !texto.trim() ? 0.5 : 1,
          }}
        >
          {enviando ? "…" : "Enviar"}
        </button>
      </form>
    </div>
  );
}
