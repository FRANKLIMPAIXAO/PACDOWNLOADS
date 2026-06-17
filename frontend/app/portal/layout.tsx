import { ReactNode } from "react";

// Layout do PORTAL DO CLIENTE. Fica DENTRO do layout raiz (html/body), mas o
// AppHeader do escritório é escondido em /portal (ver components/app-header).
// Cada página do portal renderiza seu próprio cabeçalho.
export default function PortalLayout({ children }: { children: ReactNode }) {
  return <div className="portal-shell">{children}</div>;
}
