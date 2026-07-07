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
export type PortalEmpresaItem = { id: number; razao_social: string; cnpj: string };
export type PortalMe = {
  nome: string;
  email: string;
  empresa: { id: number; razao_social: string; nome_fantasia: string | null; cnpj: string } | null;
  // Multi-empresa: empresa ativa + todas as que este login pode acessar.
  empresa_ativa_id?: number;
  empresas?: PortalEmpresaItem[];
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

/** Vencimento do certificado digital (A1 carregado no PAC, ou fallback de um
 * documento tipo 'certificado' do PAC TAREFAS). Senha NUNCA vem. */
export type CertificadoEmpresa = {
  validade: string;
  dias_para_vencer: number;
  subject: string | null;
  status: "valido" | "a_vencer" | "vencido";
  origem: "a1_pac" | "documento";
};
/** Documento cadastral/jurídico da empresa (contrato, alvará, certificado…). */
export type DocEmpresa = {
  id: number;
  tipo: string;
  titulo: string;
  mensagem: string | null;
  vencimento: string | null;
  nome_arquivo: string | null;
  tem_arquivo: boolean;
  enviado_em: string | null;
  lido: boolean;
};
export type DocsEmpresa = {
  certificado: CertificadoEmpresa | null;
  nao_lidos: number;
  documentos: DocEmpresa[];
};

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
  situacao_fiscal: string | null; // regular | pendencias | verificar | null
  pendencias: string[];
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

export type UploadSaidasResp = {
  total_arquivos: number;
  persistidos: number;
  duplicados: number;
  fora_do_escopo: number;
  nao_cadastrada: number;
  erros: number;
};

export type UploadSaidasJob = {
  status: "rodando" | "concluido" | "erro";
  feitas: number;
  total: number;
  resultado?: UploadSaidasResp;
  erro?: string;
};

/** Cliente sobe XMLs/ZIP das próprias notas (saída de qualquer estado). Multipart
 * — NÃO usa portalFetch (que força JSON); deixa o browser pôr o boundary. O upload
 * roda em BACKGROUND (varejo = milhares de NFC-e), então volta só o job_id e o
 * front faz polling em portalStatusUploadSaidas. */
export async function portalUploadSaidas(file: File): Promise<{ job_id: string }> {
  const fd = new FormData();
  fd.append("arquivo", file);
  const token = getPortalToken();
  const res = await fetch(`${API_BASE_URL}/api/v1/portal/upload-saidas`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });
  const text = await res.text();
  let payload: unknown = null;
  if (text) { try { payload = JSON.parse(text); } catch { payload = text; } }
  if (!res.ok) {
    const detail = payload && typeof payload === "object" && payload !== null && "detail" in payload
      ? (payload as { detail: unknown }).detail : payload;
    throw new ApiError(res.status, detail, typeof detail === "string" ? detail : `Erro ${res.status}`);
  }
  return payload as { job_id: string };
}

/** Consulta o progresso do upload em background (X/N + resultado final). */
export function portalStatusUploadSaidas(jobId: string) {
  return portalFetch<UploadSaidasJob>(`/api/v1/portal/upload-saidas/status/${jobId}`);
}

/** Cliente define a senha a partir do token do convite (link do e-mail) e já
 * fica logado (guarda o token do portal). Público (skipAuth). */
export async function portalDefinirSenha(token: string, senha: string): Promise<void> {
  const res = await portalFetch<{ access_token: string }>("/api/v1/portal/definir-senha", {
    method: "POST",
    skipAuth: true,
    body: JSON.stringify({ token, senha }),
  });
  setPortalToken(res.access_token);
}

export function portalMe() {
  return portalFetch<PortalMe>("/api/v1/portal/me");
}

export type AdmissaoResumo = {
  id: number;
  funcionario: string | null;
  cargo: string | null;
  data_admissao: string | null;
  status: string; // nova | em_analise | concluida | cancelada
  enviado: boolean;
  criado_em: string | null;
};

/** Cliente envia uma solicitação de admissão (form eSocial). anexos = base64. */
export function portalCriarAdmissao(dados: Record<string, unknown>, anexos: { nome: string; base64: string }[]) {
  return portalFetch<{ id: number; status: string; enviado_pactarefas: boolean; mensagem: string }>(
    "/api/v1/portal/admissoes",
    { method: "POST", body: JSON.stringify({ dados, anexos }) },
  );
}

/** Acompanhamento: as solicitações de admissão da empresa (status). */
export function portalAdmissoes() {
  return portalFetch<{ admissoes: AdmissaoResumo[] }>("/api/v1/portal/admissoes");
}

/** Troca a empresa ATIVA (cliente multi-empresa). Grava o novo token e devolve-o. */
export async function portalTrocarEmpresa(empresaId: number): Promise<void> {
  const res = await portalFetch<{ access_token: string }>(
    `/api/v1/portal/trocar-empresa?empresa_id=${empresaId}`,
    { method: "POST" },
  );
  setPortalToken(res.access_token);
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

/** Documentos cadastrais da empresa (contrato, alvará, certificado…) + vencimento
 * do certificado digital em destaque. Vêm do PAC TAREFAS. */
export function portalDocumentosEmpresa() {
  return portalFetch<DocsEmpresa>("/api/v1/portal/documentos-empresa");
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
export type SyncGuiasResp = {
  ok?: boolean;
  cobranca_necessaria?: boolean;
  valor?: number;
  cobrado?: boolean;
  mensagem?: string;
  anos?: number[];
  novas?: number;
  atualizadas?: number;
  pagas_detectadas?: number;
  erros?: number;
};
/** Cliente puxa as próprias guias DAS via Integra (self-service). Sem ano,
 * busca o ano atual + o anterior. 1ª busca grátis, depois R$ 5,00 (confirmar). */
export function portalSyncGuias(ano?: number, confirmar = false) {
  const q = new URLSearchParams();
  if (ano) q.set("ano", String(ano));
  if (confirmar) q.set("confirmar", "true");
  const qs = q.toString();
  return portalFetch<SyncGuiasResp>(
    `/api/v1/portal/guias-das/sync${qs ? `?${qs}` : ""}`,
    { method: "POST" },
  );
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

// --- Conversa (chat) com o escritório ---
import type { ChatMensagem } from "../components/chat-thread";
export type { ChatMensagem };

/** Mensagens da conversa do cliente (via PacChat). `erro` != null = PacChat fora. */
export function portalMensagens() {
  return portalFetch<{ mensagens: ChatMensagem[]; conversa_id?: string | null; erro?: string }>(
    "/api/v1/portal/mensagens",
  );
}

/** Nº de mensagens do escritório não lidas pelo cliente (badge). */
export function portalMensagensNaoLidas() {
  return portalFetch<{ total: number }>("/api/v1/portal/mensagens/nao-lidas");
}

/** O cliente envia uma mensagem pro escritório. */
export function portalEnviarMensagem(corpo: string) {
  return portalFetch<ChatMensagem>("/api/v1/portal/mensagens", {
    method: "POST",
    body: JSON.stringify({ corpo }),
  });
}
