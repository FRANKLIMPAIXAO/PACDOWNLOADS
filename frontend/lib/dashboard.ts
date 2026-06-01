// Tipos + chamada do endpoint agregado de dashboard.

import { apiFetch } from "./api";

export type FornecedorTop = {
  cnpj: string | null;
  nome: string | null;
  qtd: number;
  valor: number;
};

export type ResumoDashboard = {
  mes: string;
  empresas: {
    total: number;
    ativas: number;
    sem_focus_token: number;
    sem_certificado_a1: number;
  };
  documentos_mes: {
    total: number;
    valor_total: number;
    canceladas: number;
    geral_acumulado: number;
  };
  manifestacao: {
    pendentes: number;
    manifestadas: number;
  };
  cnds: {
    vencendo_30d: number;
    vencidas: number;
  };
  ecac: {
    nao_lidas: number;
    alta_nao_lidas: number;
  };
  certificados: {
    vencendo_60d: number;
    vencidos: number;
  };
  // Campos novos (backend ≥ 25/05). Opcionais pra não crashar com backend velho.
  das_simples?: {
    atrasadas_qtd: number;
    atrasadas_valor: number;
    em_aberto_30d: number;
  };
  parcsn?: {
    ativos: number;
    parcelas_restantes_total: number;
  };
  pgfn?: {
    ativos: number;
    valor_total: number;
    valor_pago: number;
    parcelas_restantes_total: number;
  };
  dctfweb?: {
    emitidas_mes: number;
    empresas_pendentes: number;
  };
  fgts?: {
    pendentes_qtd: number;
    valor_a_pagar: number;
    vencidas_qtd: number;
    vencendo_30d_qtd: number;
    empresas_sem_guia_mes: number;
  };
  robo_sefaz?: {
    ultima_execucao_iniciada_em: string | null;
    ultima_execucao_status: string | null;
    ultima_execucao_persistidos: number;
    ultima_execucao_erros: number;
    em_andamento: number;
  };
  top_fornecedores: FornecedorTop[];
};

export function resumoDashboard(mes?: string) {
  const qs = mes ? `?mes=${mes}` : "";
  return apiFetch<ResumoDashboard>(`/api/v1/dashboard/resumo${qs}`);
}

// --- Visao consolidada por empresa ---

export type EmpresaCertStatus = "ok" | "vencendo" | "vencido" | "ausente";

export type LinhaPorEmpresa = {
  empresa_id: number;
  cnpj: string;
  razao_social: string;
  uf: string | null;
  regime: string | null;
  nfes_mes: number;
  das_atrasadas_qtd: number;
  das_atrasadas_valor: number;
  parcsn_ativos: number;
  pgfn_ativos: number;
  fgts_pendentes: number;
  fgts_mes_emitida: boolean;
  dctfweb_mes_emitida: boolean;
  cert_a1_status: EmpresaCertStatus;
  cert_a1_validade: string | null;
  tem_focus_token: boolean;
  ultima_execucao_robo: {
    iniciado_em: string;
    status: string;
    persistidos: number;
    erros: number;
  } | null;
};

export function listaPorEmpresa() {
  return apiFetch<LinhaPorEmpresa[]>(`/api/v1/dashboard/por-empresa`);
}
