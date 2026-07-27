"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "../lib/auth-context";
import { contarNovasIndicacoes } from "../lib/indicacoes";

export function AppHeader() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [novasIndicacoes, setNovasIndicacoes] = useState(0);

  // Contador do badge "🤝 PAC Indica": carrega ao logar e a cada navegação (pra
  // zerar quando a equipe visita /indicacoes) + atualiza a cada 60s. Falha em
  // silêncio (badge some) — nunca quebra o header.
  useEffect(() => {
    if (!user) return;
    let vivo = true;
    const carregar = () =>
      contarNovasIndicacoes()
        .then((r) => { if (vivo) setNovasIndicacoes(r.novas); })
        .catch(() => {});
    carregar();
    const t = setInterval(carregar, 60000);
    return () => { vivo = false; clearInterval(t); };
  }, [user, pathname]);

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
          <Link href="/docs-cliente">📨 Docs do cliente</Link>
          <Link href="/admissoes">👤 Admissões</Link>
          <Link href="/indicacoes" style={{ position: "relative" }}>
            🤝 PAC Indica
            {novasIndicacoes > 0 ? (
              <span
                title={`${novasIndicacoes} indicação(ões) nova(s)`}
                style={{
                  marginLeft: 5, display: "inline-block", minWidth: 17, padding: "1px 5px",
                  background: "#ec8b1c", color: "#fff", borderRadius: 999, fontSize: 11,
                  fontWeight: 700, lineHeight: "15px", textAlign: "center", verticalAlign: "middle",
                }}
              >
                {novasIndicacoes}
              </span>
            ) : null}
          </Link>
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
