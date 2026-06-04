// Faturamento mensal (RBT12) — manual + puxar da Receita.
import { apiFetch } from "./api";

export type MesReceita = {
  ano_mes: string;
  valor_interno: number;
  valor_externo: number;
  origem?: string | null;
};

export type ReceitasMensaisResposta = {
  empresa_id: number;
  competencia: string;
  meses: MesReceita[];
  rbt12: number;
  meses_preenchidos: number;
};

export type PuxarReceitaResposta = {
  empresa_id: number;
  competencia: string;
  meses: Array<{ ano_mes: string; valor_interno: number; valor_externo: number; encontrado: boolean }>;
  encontrados: number;
  total_meses: number;
  erros: string[];
  aviso?: string | null;
};

/** Lista os 12 meses anteriores à competência com valores (0 se vazio). */
export function listarReceitasMensais(empresaId: number, competencia: string) {
  return apiFetch<ReceitasMensaisResposta>(
    `/api/v1/empresas/${empresaId}/receitas-mensais?competencia=${competencia}`,
  );
}

/** Salva (upsert) os meses da grade manual. */
export function salvarReceitasMensais(empresaId: number, meses: MesReceita[]) {
  return apiFetch<{ salvos: number }>(
    `/api/v1/empresas/${empresaId}/receitas-mensais`,
    { method: "PUT", body: JSON.stringify({ meses }) },
  );
}

/** Puxa o faturamento dos 12 meses anteriores via Integra Contador. */
export function puxarReceitaDaReceita(empresaId: number, competencia: string) {
  return apiFetch<PuxarReceitaResposta>(
    `/api/v1/empresas/${empresaId}/receitas-mensais/puxar-receita?competencia=${competencia}`,
    { method: "POST" },
  );
}
