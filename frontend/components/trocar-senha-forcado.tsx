"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { trocarSenha } from "../lib/usuarios";

/**
 * Tela que BLOQUEIA o app enquanto a senha for provisória (admin criou/resetou).
 * O usuário define a senha dele; ao salvar, recarrega o /auth/me (limpa a flag)
 * e o ProtectedRoute libera o conteúdo.
 */
export function TrocarSenhaForcado() {
  const { user, refreshUser, logout } = useAuth();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [conf, setConf] = useState("");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    if (nova.length < 6) {
      setErro("A nova senha precisa de ao menos 6 caracteres.");
      return;
    }
    if (nova !== conf) {
      setErro("A confirmação não bate com a nova senha.");
      return;
    }
    setBusy(true);
    try {
      await trocarSenha(atual, nova);
      await refreshUser(); // limpa senha_provisoria → ProtectedRoute libera o app
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao trocar a senha.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "70vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <section className="panel form-card" style={{ maxWidth: 440, width: "100%" }}>
        <h2 style={{ marginTop: 0 }}>🔐 Defina sua senha</h2>
        <p className="muted">
          Olá, {user?.nome?.split(" ")[0] || "bem-vindo"}! Sua senha é{" "}
          <strong>provisória</strong>. Por segurança, defina uma senha sua antes de continuar.
        </p>
        <form onSubmit={handleSubmit} className="form-stack">
          <label>
            <span>Senha provisória (a que você recebeu)</span>
            <input
              type="password"
              value={atual}
              onChange={(e) => setAtual(e.target.value)}
              autoComplete="current-password"
              required
              autoFocus
            />
          </label>
          <label>
            <span>Nova senha</span>
            <input
              type="password"
              value={nova}
              onChange={(e) => setNova(e.target.value)}
              autoComplete="new-password"
              minLength={6}
              required
            />
          </label>
          <label>
            <span>Confirmar nova senha</span>
            <input
              type="password"
              value={conf}
              onChange={(e) => setConf(e.target.value)}
              autoComplete="new-password"
              required
            />
          </label>
          {erro ? <p className="toast toast-error">{erro}</p> : null}
          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={logout}>
              Sair
            </button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? "Salvando..." : "Definir senha e entrar"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
