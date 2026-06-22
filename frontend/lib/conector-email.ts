import { apiFetch } from "./api";

export type ConectorEmailConfig = { ativo: boolean; caixa: string | null };

export type ConectorEmailResultado = {
  emails_lidos: number;
  anexos: number;
  persistidos: number;
  duplicados: number;
  nao_cadastrada: number;
  erros: number;
  remetentes: string[];
};

export type ConectorEmailJob = {
  status: "rodando" | "concluido" | "erro";
  resultado?: ConectorEmailResultado;
  erro?: string;
};

/** Diz se o conector de e-mail está ligado (IMAP configurado no servidor). */
export function conectorEmailConfig() {
  return apiFetch<ConectorEmailConfig>("/api/v1/conector-email/config");
}

/** Dispara a leitura da caixa em background; volta o job_id. */
export function conectorEmailProcessar() {
  return apiFetch<{ job_id: string }>("/api/v1/conector-email/processar", { method: "POST" });
}

/** Consulta o andamento da leitura (polling). */
export function conectorEmailStatus(jobId: string) {
  return apiFetch<ConectorEmailJob>(`/api/v1/conector-email/status/${jobId}`);
}
