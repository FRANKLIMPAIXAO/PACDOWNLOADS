import "./globals.css";
import { ReactNode } from "react";

import { AppHeader } from "../components/app-header";
import { AuthProvider } from "../lib/auth-context";

export const metadata = {
  title: "PAC Download — Central fiscal",
  description: "Central fiscal moderna para escritorios contabeis: empresas, XMLs DF-e, CND, eCAC e SITFIS.",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
  // CRITICAL: notranslate impede o Google Translate de mexer no DOM.
  // Sem isso, o Chrome auto-traduz e dispara "removeChild on Node: The node
  // to be removed is not a child of this node" quando React tenta reconciliar
  // árvore que o Translate alterou. É a causa #1 desse erro em apps Next.js
  // em produção pra usuários BR.
  other: {
    google: "notranslate",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // lang="pt-BR" + translate="no" + classe notranslate: 3 sinais pro Chrome
    // não tentar traduzir. Funciona em todas as versões.
    <html lang="pt-BR" translate="no" className="notranslate" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AuthProvider>
          <div className="shell">
            <div className="frame">
              <AppHeader />
              {children}
            </div>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
