// Distribuição DF-e da NFe — puxa recebidas direto com o cert A1 (sem Focus).
import { apiFetch } from "./api";

export type DfeElegivel = {
  id: number;
  razao_social: string;
  cnpj: string;
  ult_nsu: string | null;
};

export type DfeResultado = {
  empresa_id: number;
  razao_social?: string;
  ok?: boolean;
  concluido?: boolean;
  resumos_recebidas_novos?: number;
  nfes_completas_novas?: number;
  eventos?: number;
  cstat?: string;
  motivo?: string;
  ult_nsu?: string;
  erro?: string | null;
  aviso?: string | null;
};

/** Empresas aptas (ativas, com cert A1, sem Focus). */
export function dfeElegiveis() {
  return apiFetch<DfeElegivel[]>("/api/v1/dfe-nfe/elegiveis");
}

/** Distribui um bloco (máx 5) de empresas. */
export function dfeDistribuirLote(empresaIds: number[], maxPaginas = 8) {
  return apiFetch<{ resultados: DfeResultado[] }>(
    "/api/v1/dfe-nfe/distribuir-lote",
    { method: "POST", body: JSON.stringify({ empresa_ids: empresaIds, max_paginas: maxPaginas }) },
  );
}

export type DfeManifestoResultado = {
  empresa_id: number;
  manifestadas: number;
  ja_cientes: number;
  erros: string[];
  restantes_resumo: number;
  aviso?: string | null;
};

/** Manifesta (Ciência da Operação) até `limite` recebidas em resumo da empresa. */
export function dfeManifestar(empresaId: number, limite = 20) {
  return apiFetch<DfeManifestoResultado>(
    `/api/v1/dfe-nfe/empresa/${empresaId}/manifestar?limite=${limite}`,
    { method: "POST" },
  );
}

/** Manifesta (Ciência da Operação) UMA nota específica (botão da linha). */
export function dfeManifestarDoc(documentoId: number) {
  return apiFetch<{ ok: boolean; cstat: string; motivo: string; aviso?: string | null }>(
    `/api/v1/dfe-nfe/documento/${documentoId}/manifestar`,
    { method: "POST" },
  );
}

// --- Relatório dos crons de distribuição (DF-e recebidas / CT-e frete) ---
export type CronEmpresaItem = {
  empresa_id: number;
  razao_social?: string;
  resumos?: number;
  completas?: number;
  cstat?: string;
};
export type CronExecucao = {
  id: number;
  criado_em: string | null;
  tipo: string; // dfe | cte
  total_elegiveis: number;
  processadas: number;
  novos: number;
  com_656: number;
  detalhe: CronEmpresaItem[];
  erro_msg: string | null;
};

/** Histórico do cron de distribuição. tipo='dfe' (recebidas NFe) | 'cte' (frete). */
export function cronExecucoes(tipo: "dfe" | "cte", limit = 30) {
  const base = tipo === "cte" ? "/api/v1/dfe-cte" : "/api/v1/dfe-nfe";
  return apiFetch<{ execucoes: CronExecucao[] }>(`${base}/cron-execucoes?limit=${limit}`);
}
