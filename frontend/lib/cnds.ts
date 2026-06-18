// Camada tipada para o módulo Controle de CND.

import { apiFetch } from "./api";

export type TipoCertidao =
  | "FEDERAL"           // SITFIS via Integra Contador (uso interno, 60d)
  | "FEDERAL_OFICIAL"   // CND oficial RFB+PGFN (sob demanda, 180d)
  | "FGTS"
  | "TRABALHISTA"
  | "ESTADUAL"
  | "MUNICIPAL";

export type StatusCertidao = "VALIDA" | "A_VENCER" | "VENCIDA" | "DESCONHECIDO";

export type Certidao = {
  id: number;
  empresa_id: number;
  tipo: TipoCertidao;
  numero: string | null;
  data_emissao: string | null;
  data_validade: string;
  pdf_path: string | null;
  observacoes: string | null;
  created_at: string;
  updated_at: string;
  status: StatusCertidao;
  dias_para_vencer: number | null;
  situacao_fiscal: string | null; // regular | pendencias | verificar | null
  pendencias: string[];
};

export type CndDashboardLinha = {
  empresa_id: number;
  empresa_razao_social: string;
  cnpj: string;
  federal: Certidao | null;          // SITFIS (Integra)
  federal_oficial: Certidao | null;  // CND oficial RFB+PGFN
  fgts: Certidao | null;
  trabalhista: Certidao | null;
  estadual: Certidao | null;
  municipal: Certidao | null;
  score: number;
};

export type TipoCndConfig = {
  tipo: TipoCertidao;
  label: string;
  full: string;
  fonte: string;            // "Integra Contador" | "Portal RFB" | "Manual" | ...
  validade_dias: number;
  automatico: boolean;       // tem botao "Renovar agora"?
  sob_demanda?: boolean;     // emitir somente sob demanda (nao no batch semanal)
};

export const TIPOS_CND: TipoCndConfig[] = [
  {
    tipo: "FEDERAL", label: "Federal RFB+PGFN",
    full: "Situacao fiscal RFB+PGFN (SITFIS interno + CND oficial sob demanda)",
    fonte: "Integra Contador (SITFIS) + Portal RFB (oficial)",
    validade_dias: 60,
    automatico: true,
  },
  {
    tipo: "FEDERAL_OFICIAL", label: "CND Federal oficial",
    full: "CND Conjunta RFB+PGFN — para licitacoes/bancos",
    fonte: "Portal RFB (scraper pendente)",
    validade_dias: 180,
    automatico: true,
    sob_demanda: true,
  },
  {
    tipo: "FGTS", label: "FGTS (CRF)",
    full: "Certidao de Regularidade do FGTS — Caixa",
    fonte: "Portal Caixa (scraper pendente — cadastrar manual)",
    validade_dias: 30,
    automatico: false,
  },
  {
    tipo: "TRABALHISTA", label: "Trabalhista (CNDT)",
    full: "Certidao Negativa de Debitos Trabalhistas — TST",
    fonte: "Portal TST (scraper pendente — cadastrar manual)",
    validade_dias: 180,
    automatico: false,
  },
  {
    tipo: "ESTADUAL", label: "Estadual",
    full: "CND Sefaz estadual — varia por UF",
    fonte: "Manual",
    validade_dias: 180,
    automatico: false,
  },
  {
    tipo: "MUNICIPAL", label: "Municipal",
    full: "CND Prefeitura — varia por municipio",
    fonte: "Manual",
    validade_dias: 180,
    automatico: false,
  },
];

export function dashboardCnds() {
  return apiFetch<CndDashboardLinha[]>("/api/v1/cnds/dashboard");
}

export function listarCnds(empresaId: number) {
  return apiFetch<Certidao[]>(`/api/v1/cnds/empresa/${empresaId}`);
}

export type CertidaoCreate = {
  tipo: TipoCertidao;
  numero?: string;
  data_emissao?: string;
  data_validade: string;
  observacoes?: string;
};

export function criarCnd(empresaId: number, payload: CertidaoCreate) {
  return apiFetch<Certidao>(`/api/v1/cnds/empresa/${empresaId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function atualizarCnd(certidaoId: number, payload: Partial<CertidaoCreate>) {
  return apiFetch<Certidao>(`/api/v1/cnds/${certidaoId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function removerCnd(certidaoId: number) {
  return apiFetch<void>(`/api/v1/cnds/${certidaoId}`, { method: "DELETE" });
}

export function uploadCndPdf(certidaoId: number, arquivo: File) {
  const form = new FormData();
  form.append("arquivo", arquivo);
  return apiFetch<Certidao>(`/api/v1/cnds/${certidaoId}/pdf`, {
    method: "PUT",
    body: form,
  });
}

// --- Renovacao automatica ---

// FEDERAL    → SITFIS via Integra Contador
// FEDERAL_OFICIAL → CND oficial RFB+PGFN via Playwright (sob demanda)
// TRABALHISTA / FGTS → portais via Playwright + 2captcha
export type TipoCndRenovavel = "FEDERAL" | "FEDERAL_OFICIAL" | "TRABALHISTA" | "FGTS";

export function renovarCndAutomatica(empresaId: number, tipo: TipoCndRenovavel) {
  return apiFetch<Certidao>(
    `/api/v1/cnds/empresa/${empresaId}/renovar?tipo=${tipo}`,
    { method: "POST" },
  );
}

export type RenovarVencendoResposta = {
  sucesso: number;
  falhas: number;
  pulados: number;
  detalhes: {
    empresa_id: number;
    empresa_nome: string;
    tipo: string;
    status: string;
    certidao_id?: number;
    validade_nova?: string;
    mensagem?: string;
  }[];
};

export function renovarVencendo(janelaDias = 7) {
  return apiFetch<RenovarVencendoResposta>(
    `/api/v1/cnds/renovar-vencendo?janela_dias=${janelaDias}`,
    { method: "POST" },
  );
}

export function statusPillClass(status: StatusCertidao): string {
  if (status === "VALIDA") return "pill pill-ok";
  if (status === "A_VENCER") return "pill pill-warn";
  if (status === "VENCIDA") return "pill pill-err";
  return "pill pill-muted";
}

export function statusLabel(status: StatusCertidao): string {
  if (status === "VALIDA") return "Valida";
  if (status === "A_VENCER") return "A vencer";
  if (status === "VENCIDA") return "Vencida";
  return "—";
}

type CertEfetiva = { status: StatusCertidao; situacao_fiscal?: string | null };

/** Status EFETIVO: a regularidade (pendência) tem prioridade sobre a data.
 * `verificar` = SITFIS que não deu pra ler o diagnóstico → não afirmar válida. */
export function efetivoLabel(c: CertEfetiva): string {
  if (c.status === "VENCIDA") return "Vencida";
  if (c.situacao_fiscal === "pendencias") return "Com pendências";
  if (c.situacao_fiscal === "verificar") return "Verificar";
  return statusLabel(c.status);
}
export function efetivoPillClass(c: CertEfetiva): string {
  if (c.status === "VENCIDA") return "pill pill-err";
  if (c.situacao_fiscal === "pendencias") return "pill pill-err";
  if (c.situacao_fiscal === "verificar") return "pill pill-muted";
  return statusPillClass(c.status);
}
