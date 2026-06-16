// Distribuição DF-e do CT-e — puxa os conhecimentos de transporte (frete)
// direto com o cert A1 (mTLS), sem Focus. Fila separada da NFe.
import { apiFetch } from "./api";

export type CteElegivel = {
  id: number;
  razao_social: string;
  cnpj: string;
  ult_nsu: string | null;
};

export type CteResultado = {
  empresa_id: number;
  razao_social?: string;
  ok?: boolean;
  concluido?: boolean;
  resumos_recebidas_novos?: number;
  ctes_completas_novas?: number;
  eventos?: number;
  cstat?: string;
  motivo?: string;
  ult_nsu?: string;
  erro?: string | null;
  aviso?: string | null;
};

/** Empresas aptas (ativas, com cert A1). NÃO exclui Focus — fila do CT-e é separada. */
export function cteElegiveis() {
  return apiFetch<CteElegivel[]>("/api/v1/dfe-cte/elegiveis");
}

/** Distribui um bloco (máx 5) de empresas. */
export function cteDistribuirLote(empresaIds: number[], maxPaginas = 8) {
  return apiFetch<{ resultados: CteResultado[] }>(
    "/api/v1/dfe-cte/distribuir-lote",
    { method: "POST", body: JSON.stringify({ empresa_ids: empresaIds, max_paginas: maxPaginas }) },
  );
}
