// Camada tipada pra a aba Mensagens do /prevencao (Caixa Postal e-CAC da carteira).
import { apiFetch } from "./api";

export type MensagemTipo = {
  tipo: string;
  total: number;
  nao_lidas: number;
  relevantes_nao_lidas: number;
  empresas: number;
};

export type MensagemItem = {
  empresa_id: number;
  empresa: string;
  cnpj: string;
  tipo: string;
  assunto: string | null;
  nao_lida: boolean;
  relevante: boolean;
  data_envio: string | null;
  isn_msg: string;
};

export type MensagensResumo = {
  total_mensagens: number;
  total_nao_lidas: number;
  total_relevantes_nao_lidas: number;
  por_tipo: MensagemTipo[];
  mensagens: MensagemItem[];
};

export function mensagensResumo() {
  return apiFetch<MensagensResumo>("/api/v1/prevencao/mensagens-resumo");
}

export type MsgJob = {
  status: "rodando" | "concluido" | "erro";
  total: number;
  feitas: number;
  sucesso: number;
  falhas: number;
  atual: string | null;
  erros: { empresa: string; erro: string }[];
  erro_geral?: string;
};

/** Dispara a sincronização da Caixa Postal da carteira (background, custa Integra). */
export function atualizarMensagens() {
  return apiFetch<{ job_id: string; ja_rodando: boolean }>(
    "/api/v1/prevencao/atualizar-mensagens",
    { method: "POST" },
  );
}

export function statusAtualizarMensagens(jobId: string) {
  return apiFetch<MsgJob>(`/api/v1/prevencao/atualizar-mensagens/status/${jobId}`);
}
