"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "../lib/api";
import { criarAcessoCliente } from "../lib/usuarios";

/** Card (tela da empresa) pra o admin criar o acesso do CLIENTE ao portal.
 * O cliente loga em /portal e vê SÓ os documentos desta empresa. */
export function ClienteAcessoCard({ empresaId }: { empresaId: number }) {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErro(null);
    setBusy(true);
    try {
      await criarAcessoCliente({ nome: nome.trim(), email: email.trim(), password, empresa_id: empresaId });
      setOk(`Acesso criado! O cliente entra em /portal com o e-mail ${email.trim()}.`);
      setNome(""); setEmail(""); setPassword("");
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao criar acesso do cliente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>🔑 Acesso do cliente (Portal)</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Cria um login pra o dono desta empresa acessar as próprias notas em <code>/portal</code>.
        Ele vê só os documentos desta empresa — nada do escritório.
      </p>
      <form onSubmit={handleSubmit} className="form-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <label>
          <span>Nome do contato</span>
          <input value={nome} onChange={(e) => setNome(e.target.value)} required />
        </label>
        <label>
          <span>E-mail (login)</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" required />
        </label>
        <label>
          <span>Senha provisória</span>
          <input type="text" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} required />
        </label>
        <div style={{ display: "flex", alignItems: "end" }}>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Criando..." : "Criar acesso"}
          </button>
        </div>
      </form>
      {ok ? <p style={{ color: "rgb(16,185,129)" }}>{ok}</p> : null}
      {erro ? <p style={{ color: "rgb(248,113,113)" }}>{erro}</p> : null}
    </div>
  );
}
