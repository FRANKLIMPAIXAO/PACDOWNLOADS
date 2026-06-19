"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "../lib/api";
import { ConviteResposta, convidarCliente, criarAcessoCliente } from "../lib/usuarios";

/** Card (tela da empresa) pra o admin dar acesso do CLIENTE ao portal.
 * Padrão: CONVIDAR por e-mail (o cliente define a própria senha pelo link).
 * Fallback: criar com senha manual (cliente sem e-mail). */
export function ClienteAcessoCard({ empresaId }: { empresaId: number }) {
  const [modo, setModo] = useState<"convite" | "manual">("convite");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [convite, setConvite] = useState<ConviteResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  function reset() {
    setNome(""); setEmail(""); setPassword("");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setOk(null); setErro(null); setConvite(null); setCopiado(false);
    setBusy(true);
    try {
      if (modo === "convite") {
        const r = await convidarCliente({ nome: nome.trim(), email: email.trim(), empresa_id: empresaId });
        setConvite(r);
        reset();
      } else {
        await criarAcessoCliente({ nome: nome.trim(), email: email.trim(), password, empresa_id: empresaId });
        setOk(`Acesso criado! O cliente entra em /portal com o e-mail ${email.trim()}.`);
        reset();
      }
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao dar acesso ao cliente.");
    } finally {
      setBusy(false);
    }
  }

  async function copiarLink() {
    if (!convite?.link) return;
    try {
      await navigator.clipboard.writeText(convite.link);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    } catch {
      /* clipboard pode falhar em http — o link fica visível pra copiar manual */
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>🔑 Acesso do cliente (Portal)</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Dá um login pro dono desta empresa ver as próprias notas, certidões e guias em{" "}
        <code>/portal</code>. Ele vê só esta empresa — nada do escritório.
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <button type="button" className={modo === "convite" ? "btn-primary" : "btn-secondary"}
          onClick={() => { setModo("convite"); setOk(null); setConvite(null); setErro(null); }}>
          ✉️ Convidar por e-mail
        </button>
        <button type="button" className={modo === "manual" ? "btn-primary" : "btn-secondary"}
          onClick={() => { setModo("manual"); setOk(null); setConvite(null); setErro(null); }}>
          Criar com senha manual
        </button>
      </div>

      {modo === "convite" ? (
        <p className="muted" style={{ marginTop: 0, fontSize: "0.86rem" }}>
          O cliente recebe um e-mail com link pra <strong>criar a própria senha</strong> e entrar.
          Self-service, igual Jettax/Nibo.
        </p>
      ) : null}

      <form onSubmit={handleSubmit} className="form-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <label>
          <span>Nome do contato</span>
          <input value={nome} onChange={(e) => setNome(e.target.value)} required />
        </label>
        <label>
          <span>E-mail {modo === "convite" ? "(recebe o convite)" : "(login)"}</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" required />
        </label>
        {modo === "manual" ? (
          <label>
            <span>Senha provisória</span>
            <input type="text" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} required />
          </label>
        ) : null}
        <div style={{ display: "flex", alignItems: "end" }}>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? (modo === "convite" ? "Enviando..." : "Criando...") : (modo === "convite" ? "Enviar convite" : "Criar acesso")}
          </button>
        </div>
      </form>

      {ok ? <p style={{ color: "rgb(16,185,129)" }}>{ok}</p> : null}
      {erro ? <p style={{ color: "rgb(248,113,113)" }}>{erro}</p> : null}

      {convite ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid var(--border)", borderRadius: 10, background: "var(--bg-1)" }}>
          <p style={{ margin: "0 0 8px", color: convite.email_enviado ? "rgb(16,185,129)" : "rgb(245,158,11)" }}>
            {convite.email_enviado ? "✅ " : "⚠️ "}{convite.detalhe}
          </p>
          {convite.link ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <code style={{ fontSize: "0.78rem", wordBreak: "break-all", flex: 1, minWidth: 220 }}>
                {convite.link}
              </code>
              <button type="button" className="btn-secondary" style={{ padding: "5px 11px" }} onClick={copiarLink}>
                {copiado ? "Copiado!" : "Copiar link"}
              </button>
            </div>
          ) : null}
          <p className="muted" style={{ margin: "8px 0 0", fontSize: "0.78rem" }}>
            Pode mandar esse link por WhatsApp também — vale por 7 dias.
          </p>
        </div>
      ) : null}
    </div>
  );
}
