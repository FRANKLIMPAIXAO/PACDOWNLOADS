"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { useAuth } from "../../lib/auth-context";
import { ApiError } from "../../lib/api";

export default function RegisterPage() {
  const { register, user, loading } = useAuth();
  const router = useRouter();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/");
    }
  }, [user, loading, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError("A senha precisa de pelo menos 6 caracteres.");
      return;
    }
    setSubmitting(true);
    try {
      await register(nome, email, password);
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Erro inesperado ao registrar.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="auth-shell">
      <article className="panel auth-card">
        <span className="badge">Novo acesso</span>
        <h2>Criar conta</h2>
        <p className="muted">Cadastre um operador do escritorio para usar o painel.</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            <span>Nome completo</span>
            <input
              type="text"
              required
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              autoComplete="name"
              autoFocus
            />
          </label>

          <label>
            <span>E-mail</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>

          <label>
            <span>Senha</span>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>

          {error ? <p className="auth-error">{error}</p> : null}

          <button type="submit" className="cta" disabled={submitting}>
            {submitting ? "Registrando..." : "Criar conta"}
          </button>
        </form>

        <p className="muted auth-footer">
          Ja possui conta? <Link href="/login">Entrar</Link>
        </p>
      </article>
    </section>
  );
}
