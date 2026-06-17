// Portal do CLIENTE — cliente HTTP próprio, com token SEPARADO do escritório
// (pac_portal_token). Assim a sessão do cliente não colide com a do escritório
// no mesmo navegador. Read-only: lista e baixa as notas da empresa dele.
import { API_BASE_URL, ApiError } from "./api";

const PORTAL_TOKEN_KEY = "pac_portal_token";

export function getPortalToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(PORTAL_TOKEN_KEY);
}

export function setPortalToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(PORTAL_TOKEN_KEY, token);
  else window.localStorage.removeItem(PORTAL_TOKEN_KEY);
}

type PortalOptions = RequestInit & { skipAuth?: boolean };

export async function portalFetch<T = unknown>(path: string, options: PortalOptions = {}): Promise<T> {
  const { skipAuth, headers, body, ...rest } = options;
  const finalHeaders: Record<string, string> = { ...(headers as Record<string, string> | undefined) };
  if (!finalHeaders["Content-Type"] && body !== undefined) finalHeaders["Content-Type"] = "application/json";
  if (!skipAuth) {
    const token = getPortalToken();
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }
  const url = `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
  let response: Response;
  try {
    response = await fetch(url, { ...rest, headers: finalHeaders, body });
  } catch (err) {
    throw new ApiError(0, null, `Falha de rede: ${(err as Error).message}`);
  }
  if (response.status === 204) return undefined as T;
  let payload: unknown = null;
  const text = await response.text();
  if (text) { try { payload = JSON.parse(text); } catch { payload = text; } }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail: unknown }).detail : payload;
    const message = typeof detail === "string" ? detail : `Erro ${response.status} em ${path}`;
    throw new ApiError(response.status, detail, message);
  }
  return payload as T;
}

// --- Tipos ---
export type PortalMe = {
  nome: string;
  email: string;
  empresa: { id: number; razao_social: string; nome_fantasia: string | null; cnpj: string } | null;
};

export type PortalDocumento = {
  id: number;
  tipo_documento: "NFE" | "CTE" | "NFSE";
  chave_acesso: string;
  numero: string | null;
  data_emissao: string | null;
  nome_emitente: string | null;
  nome_destinatario: string | null;
  valor_total: number | string | null;
  origem: string;
  status: string;
  cancelada: boolean;
};

type ResumoOrigem = { total: number; valor_ativas: number; canceladas: number; ativas: number };
export type PortalResumo = {
  emitidas: ResumoOrigem;
  recebidas: ResumoOrigem;
  faturamento: number;
  entradas_proprias: number;
  total_geral: number;
};

export type RankItem = { nome: string; valor: number };
export type PortalDashboard = {
  faturamento_mensal: { mes: string; valor: number }[];
  top_clientes: RankItem[];
  top_fornecedores: RankItem[];
  a_manifestar: number;
};

// --- API ---
export async function portalLogin(email: string, password: string): Promise<void> {
  const res = await portalFetch<{ access_token: string }>("/api/v1/portal/login", {
    method: "POST",
    skipAuth: true,
    body: JSON.stringify({ email, password }),
  });
  setPortalToken(res.access_token);
}

export function portalLogout(): void {
  setPortalToken(null);
}

export function portalMe() {
  return portalFetch<PortalMe>("/api/v1/portal/me");
}

export function portalDocumentos(params: {
  tipo_documento?: string;
  origem?: string;
  data_inicio?: string;
  data_fim?: string;
  cancelada?: boolean;
} = {}) {
  const q = new URLSearchParams();
  if (params.tipo_documento) q.set("tipo_documento", params.tipo_documento);
  if (params.origem) q.set("origem", params.origem);
  if (params.data_inicio) q.set("data_inicio", params.data_inicio);
  if (params.data_fim) q.set("data_fim", params.data_fim);
  if (params.cancelada !== undefined) q.set("cancelada", String(params.cancelada));
  const qs = q.toString();
  return portalFetch<PortalDocumento[]>(`/api/v1/portal/documentos${qs ? `?${qs}` : ""}`);
}

/** Painel gerencial: faturamento mensal (tendência) + top clientes/fornecedores
 * (no período) + a manifestar. */
export function portalDashboard(params: { meses?: number; data_inicio?: string; data_fim?: string } = {}) {
  const q = new URLSearchParams();
  q.set("meses", String(params.meses ?? 6));
  if (params.data_inicio) q.set("data_inicio", params.data_inicio);
  if (params.data_fim) q.set("data_fim", params.data_fim);
  return portalFetch<PortalDashboard>(`/api/v1/portal/dashboard?${q.toString()}`);
}

/** Cliente dá Ciência da Operação numa nota de compra (libera o XML completo). */
export function portalManifestarDoc(documentoId: number) {
  return portalFetch<{ ok: boolean; cstat: string; motivo: string; aviso?: string | null }>(
    `/api/v1/portal/documentos/${documentoId}/manifestar`,
    { method: "POST" },
  );
}

/** Manifesta em lote as recebidas em resumo. */
export function portalManifestarLote(limite = 20) {
  return portalFetch<{ manifestadas: number; ja_cientes: number; restantes_resumo: number; aviso?: string | null }>(
    `/api/v1/portal/manifestar?limite=${limite}`,
    { method: "POST" },
  );
}

/** Baixa em lote (ZIP) as notas do período, respeitando tipo/origem. */
export async function portalBaixarZip(params: {
  tipo_documento?: string;
  origem?: string;
  data_inicio?: string;
  data_fim?: string;
  arquivo?: "xml" | "pdf" | "ambos";
}): Promise<void> {
  const q = new URLSearchParams();
  if (params.tipo_documento) q.set("tipo_documento", params.tipo_documento);
  if (params.origem) q.set("origem", params.origem);
  if (params.data_inicio) q.set("data_inicio", params.data_inicio);
  if (params.data_fim) q.set("data_fim", params.data_fim);
  q.set("arquivo", params.arquivo || "xml");
  const token = getPortalToken();
  const resp = await fetch(`${API_BASE_URL}/api/v1/portal/documentos/zip?${q.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) {
    let msg = `Erro ${resp.status}`;
    try { const j = await resp.json(); if (j?.detail) msg = j.detail; } catch { /* ignore */ }
    throw new ApiError(resp.status, null, msg);
  }
  const blob = await resp.blob();
  const cd = resp.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  const filename = m ? m[1] : "documentos.zip";
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  window.URL.revokeObjectURL(url);
}

export function portalResumo(params: { data_inicio?: string; data_fim?: string } = {}) {
  const q = new URLSearchParams();
  if (params.data_inicio) q.set("data_inicio", params.data_inicio);
  if (params.data_fim) q.set("data_fim", params.data_fim);
  const qs = q.toString();
  return portalFetch<PortalResumo>(`/api/v1/portal/documentos/resumo${qs ? `?${qs}` : ""}`);
}

/** Baixa XML ou PDF de um documento (blob fetch com o token do portal). */
export async function portalBaixarArquivo(documentoId: number, tipo: "xml" | "pdf"): Promise<void> {
  const path = tipo === "xml"
    ? `/api/v1/portal/documentos/${documentoId}/download`
    : `/api/v1/portal/documentos/${documentoId}/pdf`;
  const token = getPortalToken();
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) {
    let msg = `Erro ${resp.status}`;
    try { const j = await resp.json(); if (j?.detail) msg = j.detail; } catch { /* ignore */ }
    throw new ApiError(resp.status, null, msg);
  }
  const blob = await resp.blob();
  const cd = resp.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  const filename = m ? m[1] : `documento-${documentoId}.${tipo}`;
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
