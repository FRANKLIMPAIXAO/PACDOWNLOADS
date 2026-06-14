// Busca de NFS-e pelo ADN da Receita (mTLS com o cert A1 — grátis, sem Focus).
import { apiFetch } from "./api";

export type NfseElegivel = {
  id: number;
  razao_social: string;
  cnpj: string;
  ult_nsu: string | null;
};

export type NfseResultado = {
  empresa_id: number;
  razao_social?: string;
  ok?: boolean;
  novos?: number;
  emitidas?: number;
  recebidas?: number;
  eventos?: number;
  lotes?: number;
  cursor_final?: number;
  motivo_parada?: string;
  erro?: string | null;
  erros?: string[];
  alertas?: string[];
};

/** Empresas aptas (ativas, com cert A1). */
export function nfseElegiveis() {
  return apiFetch<NfseElegivel[]>("/api/v1/nfse-adn/elegiveis");
}

/** Sincroniza uma empresa (incremental por NSU). */
export function nfseSincronizar(empresaId: number, maxLotes = 50) {
  return apiFetch<NfseResultado>(
    `/api/v1/nfse-adn/empresa/${empresaId}/sincronizar?max_lotes=${maxLotes}`,
    { method: "POST" },
  );
}

/** Sincroniza um bloco (máx 5) de empresas. */
export function nfseSincronizarLote(empresaIds: number[], maxLotes = 30) {
  return apiFetch<{ resultados: NfseResultado[] }>(
    "/api/v1/nfse-adn/sincronizar-lote",
    { method: "POST", body: JSON.stringify({ empresa_ids: empresaIds, max_lotes: maxLotes }) },
  );
}
