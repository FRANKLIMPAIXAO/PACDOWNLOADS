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
