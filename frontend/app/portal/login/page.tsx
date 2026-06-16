"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../../lib/api";
import { portalLogin } from "../../../lib/portal";

export default function PortalLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setBusy(true);
    try {
      await portalLogin(email.trim(), password);
      router.replace("/portal");
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao entrar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div className="card" style={{ width: "100%", maxWidth: 380 }}>
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <img src="/logo.svg" alt="PAC" style={{ height: 44, marginBottom: 8 }} />
          <h2 style={{ margin: 0 }}>Portal do Cliente</h2>
          <p className="muted" style={{ marginTop: 4 }}>Acesse as notas da sua empresa</p>
        </div>
        <form onSubmit={handleSubmit} className="form-grid" style={{ gridTemplateColumns: "1fr", gap: 14 }}>
          <label>
            <span>E-mail</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            <span>Senha</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {erro ? <p style={{ color: "rgb(248,113,113)", margin: 0 }}>{erro}</p> : null}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
