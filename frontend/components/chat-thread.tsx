"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

// Mensagem única — formato normalizado pelo backend (PacChat).
export type ChatMensagem = {
  id: string | number;
  autor: "escritorio" | "cliente";
  autor_nome: string | null;
  corpo: string;
  // Mídia (anexo/áudio): tipo texto|imagem|video|audio|documento + URL pública.
  tipo?: string;
  midia_url?: string | null;
  midia_nome?: string | null;
  created_at: string | null;
};

const MAX_ANEXO_MB = 20;

function horaBR(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function Midia({ m, minha }: { m: ChatMensagem; minha: boolean }) {
  if (!m.midia_url) return null;
  const url = m.midia_url;
  const nome = m.midia_nome || "arquivo";
  if (m.tipo === "imagem") {
    return (
      <a href={url} target="_blank" rel="noreferrer">
        <img src={url} alt={nome} style={{ maxWidth: "100%", maxHeight: 240, borderRadius: 8, display: "block" }} />
      </a>
    );
  }
  if (m.tipo === "video") {
    return <video src={url} controls style={{ maxWidth: "100%", maxHeight: 260, borderRadius: 8, display: "block" }} />;
  }
  if (m.tipo === "audio") {
    return <audio src={url} controls style={{ maxWidth: "100%", minWidth: 220 }} />;
  }
  // documento / outros
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      download={nome}
      style={{
        display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8,
        background: minha ? "rgba(255,255,255,0.18)" : "#f1f3f7",
        color: minha ? "#fff" : "#14284a", textDecoration: "none", fontWeight: 600, fontSize: 13,
        maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      }}
    >
      📄 {nome}
    </a>
  );
}

/**
 * Thread de conversa estilo WhatsApp. Painel com fundo PRÓPRIO — funciona no tema
 * claro do portal. `meuLado` define qual bolha vai pra direita (minhas). Suporta
 * texto, anexo (📎) e nota de voz (🎤) quando `onEnviarArquivo` é passado.
 */
export function ChatThread({
  mensagens,
  meuLado,
  onEnviar,
  onEnviarArquivo,
  carregando,
  vazioLabel,
  altura = 460,
}: {
  mensagens: ChatMensagem[];
  meuLado: "escritorio" | "cliente";
  onEnviar: (corpo: string) => Promise<void>;
  onEnviarArquivo?: (file: Blob, nome: string, texto?: string) => Promise<void>;
  carregando?: boolean;
  vazioLabel?: string;
  altura?: number;
}) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [gravando, setGravando] = useState(false);
  const [segGrav, setSegGrav] = useState(0);
  const fimRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const cancelRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  async function escolherArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = ""; // permite reenviar o mesmo arquivo
    if (!f || !onEnviarArquivo) return;
    if (f.size > MAX_ANEXO_MB * 1024 * 1024) {
      alert(`Arquivo grande demais (máx ${MAX_ANEXO_MB} MB).`);
      return;
    }
    setEnviando(true);
    try {
      await onEnviarArquivo(f, f.name, texto.trim() || undefined);
      setTexto("");
    } catch {
      alert("Não consegui enviar o arquivo. Tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  async function iniciarGravacao() {
    if (!onEnviarArquivo || gravando) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      cancelRef.current = false;
      mr.ondataavailable = (ev) => { if (ev.data.size) chunksRef.current.push(ev.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        const tipo = mr.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: tipo });
        if (cancelRef.current || blob.size === 0) return;
        const ext = tipo.includes("ogg") ? "ogg" : "webm";
        setEnviando(true);
        try {
          await onEnviarArquivo(blob, `audio-${Date.now()}.${ext}`, undefined);
        } catch {
          alert("Não consegui enviar o áudio. Tente de novo.");
        } finally {
          setEnviando(false);
        }
      };
      mediaRecRef.current = mr;
      mr.start();
      setGravando(true);
      setSegGrav(0);
      timerRef.current = setInterval(() => setSegGrav((s) => s + 1), 1000);
    } catch {
      alert("Não consegui acessar o microfone. Verifique a permissão do navegador.");
    }
  }

  function pararEnviarAudio() { cancelRef.current = false; mediaRecRef.current?.stop(); setGravando(false); }
  function cancelarGravacao() { cancelRef.current = true; mediaRecRef.current?.stop(); setGravando(false); }

  const podeMidia = !!onEnviarArquivo;

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", height: altura,
        borderRadius: 14, overflow: "hidden", border: "1px solid rgba(0,0,0,0.10)",
        background: "#efe9e1",
      }}
    >
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
            const temMidia = !!m.midia_url;
            const temTexto = !!(m.corpo && (m.tipo === "texto" || !temMidia || m.corpo !== m.midia_nome));
            return (
              <div key={m.id} style={{ display: "flex", justifyContent: minha ? "flex-end" : "flex-start" }}>
                <div
                  style={{
                    maxWidth: "78%", padding: "8px 11px 6px", borderRadius: 12,
                    background: minha ? "#e8871e" : "#ffffff",
                    color: minha ? "#ffffff" : "#1f2937",
                    boxShadow: "0 1px 1px rgba(0,0,0,0.12)",
                    borderTopRightRadius: minha ? 3 : 12,
                    borderTopLeftRadius: minha ? 12 : 3,
                    display: "grid", gap: 5,
                  }}
                >
                  {!minha && m.autor_nome ? (
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#14284a" }}>
                      {m.autor === "escritorio" ? "🏢 " : ""}{m.autor_nome}
                    </div>
                  ) : null}
                  {temMidia ? <Midia m={m} minha={minha} /> : null}
                  {temTexto ? (
                    <div style={{ fontSize: 14, whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.4 }}>
                      {m.corpo}
                    </div>
                  ) : null}
                  <div style={{ fontSize: 10, textAlign: "right", opacity: 0.7 }}>{horaBR(m.created_at)}</div>
                </div>
              </div>
            );
          })
        )}
        <div ref={fimRef} />
      </div>

      {/* Composer */}
      {gravando ? (
        <div style={{ display: "flex", gap: 8, alignItems: "center", padding: 12, background: "#f7f4ef", borderTop: "1px solid rgba(0,0,0,0.08)" }}>
          <span style={{ color: "#dc2626", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#dc2626", display: "inline-block" }} />
            Gravando… {Math.floor(segGrav / 60)}:{String(segGrav % 60).padStart(2, "0")}
          </span>
          <div style={{ flex: 1 }} />
          <button type="button" onClick={cancelarGravacao} style={{ border: "none", background: "transparent", color: "#6b7280", cursor: "pointer", fontWeight: 600 }}>Cancelar</button>
          <button type="button" onClick={pararEnviarAudio} style={{ border: "none", borderRadius: 10, padding: "8px 16px", background: "#e8871e", color: "#fff", fontWeight: 700, cursor: "pointer" }}>Enviar áudio</button>
        </div>
      ) : (
        <form onSubmit={enviar} style={{ display: "flex", gap: 8, alignItems: "flex-end", padding: 10, background: "#f7f4ef", borderTop: "1px solid rgba(0,0,0,0.08)" }}>
          {podeMidia ? (
            <>
              <input ref={fileRef} type="file" onChange={escolherArquivo} style={{ display: "none" }} />
              <button
                type="button"
                title="Anexar arquivo"
                onClick={() => fileRef.current?.click()}
                disabled={enviando}
                style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 20, padding: "8px 6px", opacity: enviando ? 0.5 : 1 }}
              >📎</button>
              <button
                type="button"
                title="Gravar áudio"
                onClick={iniciarGravacao}
                disabled={enviando}
                style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 20, padding: "8px 6px", opacity: enviando ? 0.5 : 1 }}
              >🎤</button>
            </>
          ) : null}
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(e as unknown as FormEvent); }
            }}
            placeholder={enviando ? "Enviando…" : "Escreva uma mensagem…"}
            rows={1}
            disabled={enviando}
            style={{
              flex: 1, resize: "none", maxHeight: 120, padding: "10px 12px", borderRadius: 10,
              border: "1px solid #d7dbe6", fontSize: 14, fontFamily: "inherit", color: "#1f2937", background: "#fff",
            }}
          />
          <button
            type="submit"
            disabled={enviando || !texto.trim()}
            style={{
              border: "none", borderRadius: 10, padding: "0 18px", height: 40, cursor: "pointer",
              background: "#e8871e", color: "#fff", fontWeight: 700, fontSize: 14,
              opacity: enviando || !texto.trim() ? 0.5 : 1,
            }}
          >
            {enviando ? "…" : "Enviar"}
          </button>
        </form>
      )}
    </div>
  );
}
