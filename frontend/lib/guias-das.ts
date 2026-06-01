// Camada tipada para o módulo de Guias DAS Simples Nacional.
// Backend: app/routes/guias_das.py

import { API_BASE_URL, apiFetch, getStoredToken } from "./api";

export type SituacaoGuiaDAS =
  | "em_aberto"
  | "atrasada"
  | "paga"
  | "parcialmente_paga";

export type GuiaDAS = {
  id: number;
  empresa_id: number;
  periodo_apuracao: string;           // YYYYMM
  competencia_formatada: string;       // MM/YYYY
  numero_declaracao: string | null;
  recibo_declaracao: string | null;
  data_transmissao: string | null;     // ISO
  valor_principal: string;             // Decimal serializado
  data_vencimento_original: string;    // YYYY-MM-DD
  valor_atualizado: string | null;
  data_vencimento_atualizada: string | null;
  numero_das: string | null;
  codigo_barras: string | null;
  pdf_path: string | null;
  emitida_em: string | null;
  situacao: SituacaoGuiaDAS;
  data_pagamento: string | null;
  valor_pago: string | null;
  dias_atraso: number;
  sincronizada_em: string;
};

export type GuiaDASComEmpresa = GuiaDAS & {
  empresa_cnpj: string | null;
  empresa_razao_social: string | null;
};

export type SyncDASResposta = {
  novas: number;
  atualizadas: number;
  pagas_detectadas: number;
  erros: number;
  detalhes: Array<{ erro?: string; competencia?: string; etapa?: string }> | null;
};

// ---------------------------------------------------------------------

export function listarGuiasEmpresa(empresaId: number, somenteAtrasadas = false) {
  const qs = somenteAtrasadas ? "?somente_atrasadas=true" : "";
  return apiFetch<GuiaDAS[]>(`/api/v1/guias-das/empresa/${empresaId}${qs}`);
}

export function syncEmpresa(empresaId: number, ano: number) {
  return apiFetch<SyncDASResposta>(
    `/api/v1/guias-das/empresa/${empresaId}/sync`,
    { method: "POST", body: JSON.stringify({ ano }) },
  );
}

export function dashboardAtrasadas() {
  return apiFetch<GuiaDASComEmpresa[]>("/api/v1/guias-das/atrasadas");
}

export function emitirGuiaAtualizada(guiaId: number) {
  return apiFetch<GuiaDAS>(
    `/api/v1/guias-das/${guiaId}/atualizar`,
    { method: "POST" },
  );
}

/**
 * URL absoluta pra abrir/baixar o PDF (precisa de Authorization no header,
 * então usar via fetch + blob — não via window.open direto).
 */
export async function baixarPdf(guiaId: number): Promise<Blob> {
  const token = getStoredToken();
  const resp = await fetch(
    `${API_BASE_URL}/api/v1/guias-das/${guiaId}/pdf`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!resp.ok) {
    throw new Error(`Erro ao baixar PDF: HTTP ${resp.status}`);
  }
  return await resp.blob();
}

// Helpers UI ---------------------------------------------------------

export function situacaoPillClass(s: SituacaoGuiaDAS): string {
  if (s === "paga") return "pill pill-ok";
  if (s === "atrasada") return "pill pill-err";
  if (s === "parcialmente_paga") return "pill pill-warn";
  return "pill pill-muted"; // em_aberto
}

export function situacaoLabel(s: SituacaoGuiaDAS): string {
  if (s === "paga") return "Paga";
  if (s === "atrasada") return "Atrasada";
  if (s === "parcialmente_paga") return "Parcial";
  return "Em aberto";
}

export function formatarReal(valor: string | number | null): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = typeof valor === "string" ? parseFloat(valor) : valor;
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function formatarDataBR(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("T")[0].split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}
