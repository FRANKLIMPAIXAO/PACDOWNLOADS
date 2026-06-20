// Situação fiscal consolidada da carteira (Prevenção — triagem por exceção).
import { apiFetch } from "./api";

export type PrevSituacao = "regular" | "pendencias" | "verificar" | null;

export type PrevEmpresa = {
  empresa_id: number;
  razao_social: string;
  cnpj: string;
  regime: string | null;
  situacao_fiscal: PrevSituacao;
  pendencias: string[];
  saldo_devedor: number;
  guias_vencidas: number;
  tem_parcelamento: boolean;
  tem_situacao: boolean;
};

export type PrevTotais = {
  empresas: number;
  regular: number;
  com_pendencia: number;
  a_verificar: number;
  sem_dado: number;
  empresas_com_debito: number;
  saldo_devedor: number;
  guias_vencidas: number;
  empresas_com_parcelamento: number;
};

export type PrevSituacaoFiscal = { totais: PrevTotais; empresas: PrevEmpresa[] };

/** Saúde fiscal de TODA a carteira numa chamada (situação + débitos + parcelamento). */
export function situacaoFiscalCarteira() {
  return apiFetch<PrevSituacaoFiscal>("/api/v1/prevencao/situacao-fiscal");
}

export type SitfisJob = {
  status: "rodando" | "concluido" | "erro";
  total: number;
  feitas: number;
  sucesso: number;
  falhas: number;
  atual: string | null;
  erros: { empresa: string; erro: string }[];
  erro_geral?: string;
};

/** Dispara, em background, a atualização do SITFIS de toda a carteira (Integra). */
export function atualizarSituacaoFiscal() {
  return apiFetch<{ job_id: string; ja_rodando: boolean }>(
    "/api/v1/prevencao/atualizar-situacao-fiscal",
    { method: "POST" },
  );
}

export function statusAtualizacaoSituacaoFiscal(jobId: string) {
  return apiFetch<SitfisJob>(`/api/v1/prevencao/atualizar-situacao-fiscal/status/${jobId}`);
}
