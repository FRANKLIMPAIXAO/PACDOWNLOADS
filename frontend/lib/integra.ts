// Camada tipada para os endpoints do Integra Contador (Serpro).

import { apiFetch } from "./api";

// --- Tipos ---

export type MensagemEcac = {
  id: number;
  empresa_id: number;
  isn_msg: string;
  assunto: string | null;
  remetente: string | null;
  data_envio: string | null;
  indicador_leitura: string | null;
  indicador_relevancia: string | null;
  sincronizada_em: string;
};

export type MensagemEcacDetalhe = MensagemEcac & {
  conteudo_html: string | null;
};

export type SyncCaixaPostalResposta = {
  sincronizadas: number;
  novas: number;
  atualizadas: number;
  erros: number;
};

export type Procuracao = {
  id: number;
  empresa_id: number;
  cnpj_outorgante: string;
  cnpj_outorgado: string;
  data_inicio: string | null;
  data_fim: string | null;
  situacao: string;
  servicos_autorizados: string[] | null;
  sincronizada_em: string;
};

export type Dte = {
  cnpj: string | null;
  indicador_optante: boolean | null;
  data_adesao: string | null;
  raw?: Record<string, unknown> | null;
};

// --- Caixa Postal ---

export function syncCaixaPostal(empresaId: number) {
  return apiFetch<SyncCaixaPostalResposta>(
    `/api/v1/empresas/${empresaId}/integra/caixa-postal/sync`,
    { method: "POST" },
  );
}

export function listarCaixaPostal(empresaId: number) {
  return apiFetch<MensagemEcac[]>(`/api/v1/empresas/${empresaId}/integra/caixa-postal`);
}

export function detalharMensagem(empresaId: number, isnMsg: string) {
  return apiFetch<MensagemEcacDetalhe>(
    `/api/v1/empresas/${empresaId}/integra/caixa-postal/${isnMsg}`,
  );
}

export type CaixaPostalResumo = {
  empresa_id: number;
  total: number;
  nao_lidas: number;
  lidas: number;
  alta_relevancia: number;
  alta_relevancia_nao_lidas: number;
};

export function resumoCaixaPostal(empresaId: number) {
  return apiFetch<CaixaPostalResumo>(
    `/api/v1/empresas/${empresaId}/integra/caixa-postal-resumo`,
  );
}

export function marcarMensagensLidas(empresaId: number, isns?: string[]) {
  return apiFetch<{ empresa_id: number; marcadas: number }>(
    `/api/v1/empresas/${empresaId}/integra/caixa-postal/marcar-lidas`,
    {
      method: "POST",
      body: JSON.stringify({ isns: isns ?? null }),
    },
  );
}

// --- Procuracao ---

export function syncProcuracao(empresaId: number) {
  return apiFetch<Procuracao>(
    `/api/v1/empresas/${empresaId}/integra/procuracao/sync`,
    { method: "POST" },
  );
}

export function obterProcuracao(empresaId: number) {
  return apiFetch<Procuracao>(`/api/v1/empresas/${empresaId}/integra/procuracao`);
}

// --- DTE ---

export function consultarDte(empresaId: number) {
  return apiFetch<Dte>(`/api/v1/empresas/${empresaId}/integra/dte`);
}

// --- SITFIS ---

export type SituacaoFiscal = {
  id: number;
  empresa_id: number;
  protocolo: string | null;
  pdf_path: string | null;
  status: string;
  gerada_em: string;
};

export function gerarSituacaoFiscal(empresaId: number) {
  return apiFetch<SituacaoFiscal>(
    `/api/v1/empresas/${empresaId}/integra/sitfis/gerar`,
    { method: "POST" },
  );
}

export function obterUltimaSituacao(empresaId: number) {
  return apiFetch<SituacaoFiscal>(
    `/api/v1/empresas/${empresaId}/integra/sitfis`,
  );
}

export async function abrirPdfSituacao(empresaId: number, situacaoId: number): Promise<void> {
  return abrirPdfAutenticado(
    `/api/v1/empresas/${empresaId}/integra/sitfis/${situacaoId}/pdf`,
    `sitfis-${situacaoId}.pdf`,
  );
}

// --- Pagamentos ---

export type Pagamento = {
  numero_documento: string | null;
  codigo_receita: string | null;
  descricao_receita: string | null;
  data_arrecadacao: string | null;
  valor_total: number | null;
};

export function listarPagamentos(
  empresaId: number,
  dataInicio: string,
  dataFim: string,
) {
  const params = new URLSearchParams({
    data_inicio: dataInicio,
    data_fim: dataFim,
  });
  return apiFetch<Pagamento[]>(
    `/api/v1/empresas/${empresaId}/integra/pagamentos?${params.toString()}`,
  );
}

export async function abrirComprovantePagamento(
  empresaId: number, numero: string,
): Promise<void> {
  return abrirPdfAutenticado(
    `/api/v1/empresas/${empresaId}/integra/pagamentos/${numero}/comprovante`,
    `comprovante-${numero}.pdf`,
  );
}

// --- Helper: baixar PDF passando JWT no header e abrir em nova aba ---

async function abrirPdfAutenticado(path: string, filename: string): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const token = typeof window !== "undefined" ? window.localStorage.getItem("pac_xml_token") : null;
  const response = await fetch(`${base}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Falha ${response.status} ao baixar PDF`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  // Abre em nova aba; se o browser bloquear, faz fallback de download
  const newWindow = window.open(url, "_blank");
  if (!newWindow) {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  // Libera memoria depois de 1 minuto
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
