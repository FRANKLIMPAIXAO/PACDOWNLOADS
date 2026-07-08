import "./globals.css";
import { ReactNode } from "react";

import { AppHeader } from "../components/app-header";
import { PwaRegister } from "../components/pwa-register";
import { AuthProvider } from "../lib/auth-context";

export const metadata = {
  title: "PAC Gestão",
  description: "Portal do cliente: notas fiscais, guias, certidões e conversa com o escritório.",
  applicationName: "PAC Portal",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  // iOS: abre em tela cheia (standalone) ao adicionar à tela inicial.
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent" as const,
    title: "PAC Portal",
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

// Next 15: themeColor + viewport ficam em `viewport` (não em metadata).
// viewportFit=cover deixa o app usar a tela toda respeitando o notch/área segura.
export const viewport = {
  themeColor: "#14284a",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
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
        <PwaRegister />
      </body>
    </html>
  );
}
