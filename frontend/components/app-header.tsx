"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "../lib/auth-context";

export function AppHeader() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // Esconde header em paginas de auth (login/register) e em TODO o portal do
  // cliente (/portal/*) — o portal tem layout e navegação próprios, não deve
  // mostrar o menu do escritório.
  if (pathname === "/login" || pathname === "/register" || pathname.startsWith("/portal")) {
    return null;
  }

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <header className="topbar">
      <div className="brand">
        {/* Marca PAC — mark laranja em /public/logo.svg */}
        <img src="/logo.svg" alt="PAC" className="brand-logo" />
        <div>
          <h1>PAC Gestão</h1>
          <p>Inteligência Tributária</p>
        </div>
      </div>
      <div className="topbar-right">
        <nav className="nav">
          <Link href="/">Dashboard</Link>
          <Link href="/empresas">Empresas</Link>
          <Link href="/documentos">Documentos</Link>
          <Link href="/apuracoes">Apuracoes</Link>
          <Link href="/prevencao">Prevencao</Link>
          <Link href="/relatorios">Relatorios</Link>
          <Link href="/robo-sefaz">Robô SEFAZ</Link>
          <Link href="/das">DAS Simples</Link>
          <Link href="/parcelamentos-simples">PARCSN</Link>
          <Link href="/parcelamentos-pgfn">PGFN</Link>
          <Link href="/dctfweb">DCTFWeb</Link>
          <Link href="/fgts">FGTS</Link>
          <Link href="/cobrancas">💰 Cobranças</Link>
          <Link href="/conversas">💬 Conversas</Link>
          <Link href="/docs-cliente">📨 Docs do cliente</Link>
          <Link href="/admissoes">👤 Admissões</Link>
          {user?.is_admin ? <Link href="/usuarios">👥 Usuários</Link> : null}
        </nav>
        {user ? (
          <div className="user-chip">
            <span className="user-email" title={user.email}>{user.email}</span>
            <button type="button" className="btn-ghost" onClick={handleLogout}>
              Sair
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
