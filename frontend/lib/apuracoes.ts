// Camada tipada para apuracoes mensais (PGDAS-D)

import { apiFetch, ApiError } from "./api";

export type StatusApuracao = "DRAFT" | "TRANSMITIDA" | "DAS_GERADO" | "PAGO" | "ERRO";

export type Apuracao = {
  id: number;
  empresa_id: number;
  ano_mes: string;        // "YYYYMM"
  regime: string;
  status: StatusApuracao;
  receita_bruta: string | null;
  valor_devido: string | null;
  numero_declaracao: string | null;
  recibo: string | null;
  transmitida_em: string | null;
  das_numero_documento: string | null;
  das_codigo_barras: string | null;
  das_data_vencimento: string | null;
  das_pdf_path: string | null;
  receitas_segregadas: { atividade?: string; valor?: number }[] | null;
  created_at: string;
  updated_at: string;
};

export type ResumoMes = {
  ano_mes: string;
  total_empresas_ativas: number;
  apuracoes_geradas: number;
  pendentes: number;
  transmitidas: number;
  das_gerados: number;
  pagos: number;
  valor_devido_total: number;
  valor_pago: number;
  empresas_pendentes: { id: number; razao_social: string; cnpj: string }[];
};

export function listarApuracoes(opts: { empresaId?: number; anoMes?: string } = {}) {
  const params = new URLSearchParams();
  if (opts.empresaId) params.set("empresa_id", String(opts.empresaId));
  if (opts.anoMes) params.set("ano_mes", opts.anoMes);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<Apuracao[]>(`/api/v1/apuracoes${suffix}`);
}

export function obterApuracao(id: number) {
  return apiFetch<Apuracao>(`/api/v1/apuracoes/${id}`);
}

export function obterResumoMes(anoMes: string) {
  return apiFetch<ResumoMes>(`/api/v1/apuracoes/resumo/${anoMes}`);
}

export type ApuracaoCreateInput = {
  empresa_id: number;
  ano_mes: string;
  receita_bruta: number;
  receitas_segregadas?: { atividade?: string; valor?: number }[];
};

export function criarApuracao(payload: ApuracaoCreateInput) {
  return apiFetch<Apuracao>("/api/v1/apuracoes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type ResultadoTransmissao = {
  dry_run: boolean;
  valor_devido_rfb: number | null;
  valores_rfb: Array<{ codigoTributo: number; valor: number }>;
  valor_devido_pac: number | null;
  divergencia: number | null;
  status: string;
  raw: Record<string, unknown>;
  apuracao_id: number;
  // Avisos do backend (ex.: filiais declaradas zeradas por falta de nota — risco
  // de DAS subestimado). Mostrados em destaque no banner do dry-run.
  avisos?: string[];
};

/** Valida (dry-run) ou transmite a declaração PGDAS-D.
 *
 * `dryRun=true` (default) → indicadorTransmissao=False: RFB calcula sem entregar.
 * `dryRun=false` → transmite de verdade (gera declaração + recibo).
 */
export function transmitir(id: number, dryRun = true, forcar = false) {
  return apiFetch<ResultadoTransmissao>(
    `/api/v1/apuracoes/${id}/transmitir?dry_run=${dryRun ? "true" : "false"}&forcar=${forcar ? "true" : "false"}`,
    { method: "POST" },
  );
}

/** Detalhe estruturado do 409 (trava de divergência PAC × RFB). */
export type DivergenciaDetalhe = {
  erro?: string; // divergencia_pac_rfb | sem_comparacao
  mensagem?: string;
  divergencia?: number;
  valor_devido_pac?: number | null;
  valor_devido_rfb?: number | null;
  avisos?: string[];
};

export type TransmitirJob = {
  status: "rodando" | "concluido" | "erro";
  resultado?: ResultadoTransmissao;
  erro?: string;
  code?: number;
  detalhe?: DivergenciaDetalhe | null;
};

/** Dispara o dry-run/transmissão em BACKGROUND (não estoura o timeout ~60s do
 * Traefik) e devolve um job_id pra consultar. */
export function transmitirAsync(id: number, dryRun = true, forcar = false) {
  return apiFetch<{ job_id: string; status: string }>(
    `/api/v1/apuracoes/${id}/transmitir-async?dry_run=${dryRun ? "true" : "false"}&forcar=${forcar ? "true" : "false"}`,
    { method: "POST" },
  );
}
export function transmitirJob(jobId: string) {
  return apiFetch<TransmitirJob>(`/api/v1/apuracoes/transmitir-job/${jobId}`);
}

/** Dispara a transmissão em background e faz polling até concluir. Resolve com
 * o ResultadoTransmissao ou lança ApiError com o motivo real. Na trava de
 * divergência (409), o ApiError carrega o `detalhe` estruturado em `.detail`. */
export async function transmitirComPolling(
  id: number,
  dryRun = true,
  { intervaloMs = 3000, timeoutMs = 180000, forcar = false }: { intervaloMs?: number; timeoutMs?: number; forcar?: boolean } = {},
): Promise<ResultadoTransmissao> {
  const { job_id } = await transmitirAsync(id, dryRun, forcar);
  const inicio = Date.now();
  for (;;) {
    await new Promise((r) => setTimeout(r, intervaloMs));
    const job = await transmitirJob(job_id);
    if (job.status === "concluido" && job.resultado) return job.resultado;
    if (job.status === "erro") throw new ApiError(job.code || 502, job.detalhe || null, job.erro || "Falha na transmissão.");
    if (Date.now() - inicio > timeoutMs) {
      throw new ApiError(504, null, "A Receita está demorando muito pra responder. Tente de novo em instantes.");
    }
  }
}

export function gerarDas(id: number) {
  return apiFetch<Apuracao>(`/api/v1/apuracoes/${id}/das/gerar`, { method: "POST" });
}

export function marcarPago(id: number) {
  return apiFetch<Apuracao>(`/api/v1/apuracoes/${id}/pagar`, { method: "POST" });
}

export type Extrato = {
  competencia: string;
  linhas: { codigo: string; valor: number }[];
  valorTotal: number;
};

export function obterExtrato(id: number) {
  return apiFetch<Extrato>(`/api/v1/apuracoes/${id}/extrato`);
}

// --- Motor de calculo automatico (le XMLs e calcula receita) ---

export type ItemAnalisado = {
  cfop: string;
  direcao: "ENTRADA" | "SAIDA";
  natureza: string;
  afeta_receita: number;
  valor_produto: string;
  ncm: string | null;
  csosn: string | null;
  cst_icms: string | null;
  cst_pis: string | null;
  cst_cofins: string | null;
  tipo_tributacao: "NORMAL" | "MONOFASICO" | "ST" | "MONOFASICO_ST" | "ISENTA" | "EXPORTACAO";
  monofasico_categoria: string | null;
  contribuicao: string;
};

export type DocumentoAnalise = {
  documento_id: number;
  chave: string;
  cnpj_emitente: string | null;
  nome_emitente: string | null;
  valor_nota: string;
  direcao: "ENTRADA" | "SAIDA";
  natureza_predominante: string;
  afeta_receita: number;
  contribuicao_receita: string;
  com_st: boolean;
  monofasico: boolean;
  cfops: string[];
  itens: ItemAnalisado[];
  motivo_zero: string | null;
};

export type CalculoSegregado = {
  anexo: string;
  faixa: number;
  rbt12: string;
  aliquota_nominal: string;
  aliquota_efetiva: string;
  teto_excedido: boolean;
  receita_total: string;
  receita_normal: string;
  receita_monofasica: string;
  receita_st: string;
  receita_monofasica_st: string;
  receita_exportacao: string;
  valor_devido: string;
  valor_normal: string;
  valor_monofasico: string;
  valor_st: string;
  valor_monofasico_st: string;
  valor_exportacao: string;
  decomposicao: Record<string, string>;
};

export type ResumoMotor = {
  empresa_id: number;
  empresa_cnpj: string;
  empresa_nome: string;
  ano_mes: string;
  total_docs: number;
  saidas: number;
  entradas: number;
  docs_ignorados: number;
  total_normal: string;
  total_monofasico: string;
  total_st: string;
  total_monofasico_st: string;
  total_exportacao: string;
  total_servicos: string;
  total_devolucoes_venda: string;
  receita_bruta: string;
  monofasico_por_categoria: Record<string, string>;
  rbt12: string;
  primeira_apuracao: boolean;
  anexo: string;
  fator_r_valor: string | null;
  calculo: CalculoSegregado | null;
  documentos: DocumentoAnalise[];
  avisos: string[];
};

export function calcularPreview(empresaId: number, anoMes: string) {
  return apiFetch<ResumoMotor>(`/api/v1/apuracoes/calcular/${empresaId}/${anoMes}`);
}

export function calcularESalvar(empresaId: number, anoMes: string) {
  return apiFetch<Apuracao>(`/api/v1/apuracoes/calcular/${empresaId}/${anoMes}`, {
    method: "POST",
  });
}

// --- Fechamento em lote (a carteira inteira de uma vez) ---

export type LoteItem = {
  empresa_id: number;
  razao_social: string;
  ok: boolean;
  apuracao_id?: number;
  status?: string;
  total_docs?: number;
  saidas?: number;
  receita_bruta?: string;
  valor_devido?: string | null;
  anexo?: string;
  faixa?: number | null;
  aliquota_efetiva?: string | null;
  primeira_apuracao?: boolean;
  avisos: string[];
  erro?: string | null;
};

export type LoteResposta = { ano_mes: string; resultados: LoteItem[] };

/** Calcula+salva um BLOCO de empresas (frontend fatia a carteira). Máx 25/bloco. */
export function calcularLote(anoMes: string, empresaIds: number[]) {
  return apiFetch<LoteResposta>(`/api/v1/apuracoes/calcular-lote`, {
    method: "POST",
    body: JSON.stringify({ ano_mes: anoMes, empresa_ids: empresaIds }),
  });
}

export async function abrirDasPdf(apuracaoId: number, anoMes: string): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const token = typeof window !== "undefined"
    ? window.localStorage.getItem("pac_xml_token") : null;
  const r = await fetch(`${base}/api/v1/apuracoes/${apuracaoId}/das/pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error(`Falha ${r.status} ao baixar DAS`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank");
  if (!w) {
    const a = document.createElement("a");
    a.href = url; a.download = `das_${anoMes}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// --- Helpers UI ---

export function statusPillClass(s: StatusApuracao): string {
  if (s === "PAGO") return "pill pill-ok";
  if (s === "DAS_GERADO") return "pill pill-info";
  if (s === "TRANSMITIDA") return "pill pill-violet";
  if (s === "ERRO") return "pill pill-err";
  return "pill pill-muted";
}

export function statusLabel(s: StatusApuracao): string {
  if (s === "PAGO") return "Pago";
  if (s === "DAS_GERADO") return "DAS gerado";
  if (s === "TRANSMITIDA") return "Transmitida";
  if (s === "ERRO") return "Erro";
  return "Rascunho";
}

export function formatAnoMes(s: string): string {
  if (!s || s.length !== 6) return s;
  const meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  return `${meses[parseInt(s.slice(4)) - 1]}/${s.slice(0, 4)}`;
}

export function currentAnoMes(): string {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function previousAnoMes(): string {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}
