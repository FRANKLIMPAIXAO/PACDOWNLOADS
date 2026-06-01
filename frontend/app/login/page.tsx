"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("admin@pacxml.com.br");
  const [password, setPassword] = useState("admin123");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Se ja esta logado, redireciona para a home.
  useEffect(() => {
    if (!loading && user) {
      router.replace("/");
    }
  }, [user, loading, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Erro inesperado ao fazer login.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="auth-shell">
      <article className="panel auth-card">
        <span className="badge">Acesso ao painel</span>
        <h2>Entrar</h2>
        <p className="muted">Use suas credenciais do escritorio para continuar.</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            <span>E-mail</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              autoFocus
            />
          </label>

          <label>
            <span>Senha</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>

          {error ? <p className="auth-error">{error}</p> : null}

          <button type="submit" className="cta" disabled={submitting}>
            {submitting ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="muted auth-footer">
          Sem conta? <Link href="/register">Criar uma agora</Link>
        </p>
      </article>
    </section>
  );
}
