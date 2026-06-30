"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

import { useAuth } from "../lib/auth-context";
import { TrocarSenhaForcado } from "./trocar-senha-forcado";

/**
 * Wrapper que redireciona para /login quando o usuario nao esta autenticado.
 *
 * Uso: envolver o conteudo de uma pagina protegida.
 *   <ProtectedRoute><DashboardContent /></ProtectedRoute>
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <section className="panel">
        <p>Carregando...</p>
      </section>
    );
  }

  if (!user) {
    // Redirect em andamento; nao renderiza nada
    return null;
  }

  // Senha provisória (admin criou/resetou) → BLOQUEIA o app até o usuário
  // definir a senha dele. Cobre todas as páginas que usam ProtectedRoute.
  if (user.senha_provisoria) {
    return <TrocarSenhaForcado />;
  }

  return <>{children}</>;
}
