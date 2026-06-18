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

export type DocEscritorio = {
  id: number;
  tipo: string; // guia | relatorio | comunicado | outro
  titulo: string;
  mensagem: string | null;
  competencia: string | null;
  vencimento: string | null;
  valor: number | null;
  nome_arquivo: string | null;
  tem_arquivo: boolean;
  enviado_em: string | null;
  lido: boolean;
};
export type DocsEscritorio = { nao_lidos: number; documentos: DocEscritorio[] };

export type PortalCertidao = {
  id: number;
  tipo: string;
  tipo_label: string;
  numero: string | null;
  data_emissao: string | null;
  data_validade: string | null;
  status: string; // VALIDA | A_VENCER | VENCIDA | DESCONHECIDO
  dias_para_vencer: number | null;
  tem_pdf: boolean;
};

export type PortalGuiaDAS = {
  id: number;
  competencia: string;
  periodo_apuracao: string;
  valor_principal: number;
  valor_atualizado: number | null;
  data_vencimento: string | null;
  situacao: string; // em_aberto | paga | atrasada | parcialmente_paga
  dias_atraso: number;
  tem_pdf: boolean;
  recalculos: number;
  pode_recalcular: boolean;
};
export type PortalGuias = { guias: PortalGuiaDAS[]; valor_recalculo_extra: number };

export type PortalDctfweb = {
  id: number;
  periodo: string;
  categoria: string;
  origem: string; // ativa | andamento
  emitida_em: string | null;
  tem_pdf: boolean;
};

export type RecalculoResp = {
  ok: boolean;
  cobranca_necessaria?: boolean;
  valor?: number;
  recalculos_feitos?: number;
  cobrado?: boolean;
  situacao?: string;
  valor_atualizado?: number | null;
  data_vencimento?: string | null;
  mensagem?: string;
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

/** Documentos que o escritório entregou (guias/relatórios/comunicados via PAC TAREFAS). */
export function portalDocumentosEscritorio() {
  return portalFetch<DocsEscritorio>("/api/v1/portal/documentos-escritorio");
}

/** Baixa um documento entregue pelo escritório (marca como lido). */
export async function portalBaixarDocEscritorio(id: number, nomeSugerido?: string): Promise<void> {
  const token = getPortalToken();
  const resp = await fetch(`${API_BASE_URL}/api/v1/portal/documentos-escritorio/${id}/download`, {
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
  const filename = m ? m[1] : (nomeSugerido || `documento-${id}`);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  window.URL.revokeObjectURL(url);
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

/** Baixa um arquivo do portal por path (blob fetch com o token), salvando-o. */
async function portalDownloadBlob(path: string, nomeFallback: string): Promise<void> {
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
  const filename = m ? m[1] : nomeFallback;
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  window.URL.revokeObjectURL(url);
}

/** Certidões (CNDs) da empresa do cliente — a mais recente de cada tipo. */
export function portalCertidoes() {
  return portalFetch<{ certidoes: PortalCertidao[] }>("/api/v1/portal/certidoes");
}
export function portalBaixarCertidao(id: number) {
  return portalDownloadBlob(`/api/v1/portal/certidoes/${id}/pdf`, `certidao-${id}.pdf`);
}

/** Guias DAS (Simples) da empresa do cliente. */
export function portalGuias() {
  return portalFetch<PortalGuias>("/api/v1/portal/guias-das");
}
/** Recalcula a guia (DARF atualizada via Integra). 1º grátis, 2º+ R$ 5,00.
 * Sem `confirmar`, se for cobrar volta `cobranca_necessaria` sem chamar o Integra. */
export function portalAtualizarGuia(id: number, confirmar = false) {
  return portalFetch<RecalculoResp>(
    `/api/v1/portal/guias-das/${id}/atualizar?confirmar=${confirmar}`,
    { method: "POST" },
  );
}
export function portalBaixarGuia(id: number) {
  return portalDownloadBlob(`/api/v1/portal/guias-das/${id}/pdf`, `DAS-${id}.pdf`);
}

/** Guias DCTFWeb (DARF de contribuições da folha) emitidas pelo escritório. */
export function portalDctfweb() {
  return portalFetch<{ guias: PortalDctfweb[] }>("/api/v1/portal/guias-dctfweb");
}
export function portalBaixarDctfweb(id: number) {
  return portalDownloadBlob(`/api/v1/portal/guias-dctfweb/${id}/pdf`, `DCTFWeb-${id}.pdf`);
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
