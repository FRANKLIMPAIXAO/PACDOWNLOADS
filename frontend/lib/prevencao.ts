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
