import { apiFetch } from "./api";

export type TipoDocumento = "NFE" | "CTE" | "NFSE";

export type TipoManifestacao =
  | "ciencia"
  | "confirmacao"
  | "desconhecimento"
  | "nao_realizada";

export type Documento = {
  id: number;
  empresa_id: number;
  tipo_documento: TipoDocumento;
  chave_acesso: string;
  numero?: string | null;
  serie?: string | null;
  data_emissao?: string | null;
  cnpj_emitente?: string | null;
  nome_emitente?: string | null;
  cnpj_destinatario?: string | null;
  nome_destinatario?: string | null;
  valor_total?: string | number | null;
  status: string;
  xml_path: string;
  json_original?: {
    manifestado_em?: string;
    manifestado_tipo?: TipoManifestacao;
    [key: string]: unknown;
  } | null;
  cancelada?: boolean;
  cancelada_em?: string | null;
  motivo_cancelamento?: string | null;
  protocolo_cancelamento?: string | null;
  /** Origem do documento: 'emitida' (saída da própria empresa), 'recebida'
   * (entrada de fornecedor). NFes 'emitida' NÃO precisam ser manifestadas.
   */
  origem?: string | null;
  created_at: string;
};

export type ManifestacaoResultadoUm = {
  documento_id: number;
  chave_acesso: string;
  tipo_manifestacao: TipoManifestacao;
  status_sefaz: string | null;
  protocolo: string | null;
  manifestado_em: string | null;
  xml_atualizado: boolean;
  pdf_baixado: boolean;
  ja_estava_manifestado: boolean;
};

export type ManifestacaoResultadoLote = {
  empresa_id: number;
  total: number;
  manifestadas: number;
  ja_manifestadas: number;
  pdf_baixadas: number;
  xml_atualizadas: number;
  erros: number;
};

export function listarDocumentos(
  filtros: {
    empresaId?: number;
    tipo?: TipoDocumento;
    cancelada?: boolean;
    dataInicio?: string; // YYYY-MM-DD
    dataFim?: string;    // YYYY-MM-DD
  } = {},
) {
  const params = new URLSearchParams();
  if (filtros.empresaId) params.set("empresa_id", String(filtros.empresaId));
  if (filtros.tipo) params.set("tipo_documento", filtros.tipo);
  if (filtros.cancelada !== undefined) {
    params.set("cancelada", filtros.cancelada ? "true" : "false");
  }
  if (filtros.dataInicio) params.set("data_inicio", filtros.dataInicio);
  if (filtros.dataFim) params.set("data_fim", filtros.dataFim);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<Documento[]>(`/api/v1/documentos${suffix}`);
}

// --- Sincronização via Focus NFe (distribuição DF-e) ---
//
// Baixa NFes RECEBIDAS contra o CNPJ via Focus NFe.
// Pré-requisito: empresa com focus_token salvo.
// Janela SEFAZ: 90 dias retroativos a partir da data_fim.

export type SincronizarFocusEmpresaResultado = {
  empresa_id: number;
  cnpj: string;
  ultimo_nsu_distribuicao: string | null;
  baixados: number;
  duplicados: number;
  empresa_nao_cadastrada: number;
  erros: number;
  total_arquivos: number;
  log_id: number | null;
};

export type SincronizarFocusMultiResultado = {
  processadas: number;
  baixados: number;
  duplicados: number;
  erros: number;
  detalhes: Array<{
    empresa_id: number;
    cnpj: string;
    sucesso: boolean;
    mensagem?: string;
    baixados?: number;
    duplicados?: number;
  }>;
};

export function sincronizarFocusEmpresa(
  empresaId: number,
  dataInicio: string,  // YYYY-MM-DD
  dataFim: string,
) {
  return apiFetch<SincronizarFocusEmpresaResultado>("/api/v1/robo/distribuicao", {
    method: "POST",
    body: JSON.stringify({
      empresa_id: empresaId,
      data_inicio: `${dataInicio}T00:00:00`,
      data_fim: `${dataFim}T23:59:59`,
    }),
  });
}

export function sincronizarFocusMultiempresas(
  dataInicio: string,
  dataFim: string,
) {
  return apiFetch<SincronizarFocusMultiResultado>("/api/v1/robo/multiempresas", {
    method: "POST",
    body: JSON.stringify({
      data_inicio: `${dataInicio}T00:00:00`,
      data_fim: `${dataFim}T23:59:59`,
    }),
  });
}

export type VerificarCanceladasResultado = {
  verificadas: number;
  novas_canceladas: number;
  empresa_id: number | null;
};

export function verificarCanceladas(empresaId?: number) {
  const qs = empresaId ? `?empresa_id=${empresaId}` : "";
  return apiFetch<VerificarCanceladasResultado>(
    `/api/v1/robo/verificar-canceladas${qs}`,
    { method: "POST" },
  );
}

// --- Upload em massa de XMLs (ZIP ou individual) ---

export type UploadDetalhe = {
  arquivo: string;
  chave: string | null;
  tipo: string | null;
  empresa_id: number | null;
  empresa_cnpj: string | null;
  origem: string | null;
  status: "ok" | "duplicado" | "erro" | "empresa_nao_cadastrada";
  mensagem: string | null;
};

export type UploadResultado = {
  total_arquivos: number;
  persistidos: number;
  duplicados: number;
  empresa_nao_cadastrada: number;
  erros: number;
  detalhes: UploadDetalhe[];
};

export function uploadEmMassa(arquivo: File, empresaIdFallback?: number) {
  const form = new FormData();
  form.append("arquivo", arquivo);
  if (empresaIdFallback) {
    form.append("empresa_id_fallback", String(empresaIdFallback));
  }
  return apiFetch<UploadResultado>(
    `/api/v1/documentos/upload-em-massa`,
    { method: "POST", body: form },
  );
}

export function manifestarDocumento(
  documentoId: number,
  tipo: TipoManifestacao = "ciencia",
) {
  return apiFetch<ManifestacaoResultadoUm>("/api/v1/robo/manifestar-uma", {
    method: "POST",
    body: JSON.stringify({ documento_id: documentoId, tipo }),
  });
}

export function manifestarTodasEmpresa(
  empresaId: number,
  aguardarSyncSegundos = 0,
) {
  const params = new URLSearchParams({
    empresa_id: String(empresaId),
    aguardar_sync_segundos: String(aguardarSyncSegundos),
  });
  return apiFetch<ManifestacaoResultadoLote>(
    `/api/v1/robo/manifestar?${params.toString()}`,
    { method: "POST" },
  );
}

export function downloadXmlUrl(documentoId: number): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  return `${base}/api/v1/documentos/${documentoId}/download`;
}

export function downloadPdfUrl(documentoId: number): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  return `${base}/api/v1/documentos/${documentoId}/pdf`;
}

function _extrairNomeContentDisposition(header: string | null): string | null {
  if (!header) return null;
  // Tenta filename="..." e depois filename=... (sem aspas)
  const m1 = header.match(/filename\*?="([^"]+)"/);
  if (m1) return m1[1];
  const m2 = header.match(/filename\*?=([^;]+)/);
  return m2 ? m2[1].trim() : null;
}

/**
 * Baixa um arquivo do backend forcando download (Content-Disposition: attachment).
 * NAO abre em aba — sempre dispara o "Salvar como" do browser.
 */
async function _baixarUrlAutenticado(url: string, fallbackName: string): Promise<void> {
  const token =
    typeof window !== "undefined" ? window.localStorage.getItem("pac_xml_token") : null;
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    let detail = "";
    try {
      const j = await response.json();
      detail = j?.detail || "";
    } catch {
      detail = await response.text().catch(() => "");
    }
    throw new Error(detail || `Falha ${response.status}`);
  }
  const blob = await response.blob();
  const filename =
    _extrairNomeContentDisposition(response.headers.get("Content-Disposition")) ||
    fallbackName;
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}

/** Baixa o XML do documento (forca download — nao abre em aba). */
export async function baixarXmlDocumento(documentoId: number): Promise<void> {
  return _baixarUrlAutenticado(downloadXmlUrl(documentoId), `documento-${documentoId}.xml`);
}

/** Baixa o DANFE PDF do documento (forca download — nao abre em aba). */
export async function baixarPdfDocumento(documentoId: number): Promise<void> {
  return _baixarUrlAutenticado(downloadPdfUrl(documentoId), `documento-${documentoId}.pdf`);
}

/**
 * Baixa um ZIP com todos os arquivos filtrados.
 * `arquivo`: 'xml' (so XMLs), 'pdf' (so DANFE PDFs), 'ambos' (XML + PDF lado a lado).
 */
export async function baixarZipDocumentos(opts: {
  empresaId?: number;
  tipoDocumento?: TipoDocumento;
  cancelada?: boolean;
  dataInicio?: string;
  dataFim?: string;
  arquivo: "xml" | "pdf" | "ambos";
}): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const params = new URLSearchParams({ arquivo: opts.arquivo });
  if (opts.empresaId) params.set("empresa_id", String(opts.empresaId));
  if (opts.tipoDocumento) params.set("tipo_documento", opts.tipoDocumento);
  if (opts.cancelada !== undefined) {
    params.set("cancelada", opts.cancelada ? "true" : "false");
  }
  if (opts.dataInicio) params.set("data_inicio", opts.dataInicio);
  if (opts.dataFim) params.set("data_fim", opts.dataFim);
  await _baixarUrlAutenticado(
    `${base}/api/v1/documentos/zip?${params.toString()}`,
    `documentos_${opts.arquivo}.zip`,
  );
}

/** @deprecated Use `baixarXmlDocumento` / `baixarPdfDocumento` que forcam download. */
export async function abrirArquivoAutenticado(
  documentoId: number,
  tipo: "xml" | "pdf",
): Promise<void> {
  return tipo === "xml"
    ? baixarXmlDocumento(documentoId)
    : baixarPdfDocumento(documentoId);
}

export function formatBrl(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(num)) return "—";
  return num.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("pt-BR");
  } catch {
    return iso;
  }
}
