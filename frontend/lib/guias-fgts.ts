// Camada API para Guias FGTS Digital (Infosimples modo Procurador).
// Backend: app/routes/guias_fgts.py

import { apiFetch } from "./api";

export type GuiaFgts = {
  id: number;
  empresa_id: number;
  periodo: string;
  competencia_formatada: string | null;
  data_vencimento: string | null;
  valor_total: string;
  valor_mensal: string | null;
  valor_rescisorio: string | null;
  valor_compensatorio: string | null;
  valor_encargos: string | null;
  quantidade_trabalhadores: number | null;
  pdf_url_infosimples: string | null;
  pdf_path: string | null;
  situacao: string;
  status_calculado: string;
  dias_para_vencer: number | null;
  data_pagamento: string | null;
  emitida_em: string;
};

export type GuiaFgtsComEmpresa = GuiaFgts & {
  empresa_cnpj: string | null;
  empresa_razao_social: string | null;
};

export type EmitirFgtsResposta = {
  sucesso: boolean;
  guia: GuiaFgts | null;
  erro: string | null;
};

export type HistoricoFgtsResposta = {
  total_guias: number;
  total_paginas: number;
  pagina: number;
  guias: Array<{
    numero?: string;
    tipo?: string;
    situacao?: string;
    valor_total?: string;
    data_limite_pagamento?: string;
    competencia?: string;
    [key: string]: unknown;
  }>;
  empregador: Record<string, unknown> | null;
  procurador: Record<string, unknown> | null;
};

export function listarGuiasFgtsEmpresa(empresaId: number) {
  return apiFetch<GuiaFgts[]>(`/api/v1/guias-fgts/empresa/${empresaId}`);
}

export function listarGuiasFgtsPendentes() {
  return apiFetch<GuiaFgtsComEmpresa[]>("/api/v1/guias-fgts/pendentes");
}

export function emitirGuiaFgts(empresaId: number, periodo: string) {
  return apiFetch<EmitirFgtsResposta>(
    `/api/v1/guias-fgts/empresa/${empresaId}/emitir`,
    { method: "POST", body: JSON.stringify({ periodo }) },
  );
}

export function consultarHistoricoFgts(
  empresaId: number,
  options: { periodo?: string; pagina?: number } = {},
) {
  const qs = new URLSearchParams();
  if (options.periodo) qs.set("periodo", options.periodo);
  if (options.pagina) qs.set("pagina", String(options.pagina));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<HistoricoFgtsResposta>(
    `/api/v1/guias-fgts/empresa/${empresaId}/historico-infosimples${suffix}`,
  );
}

export function marcarFgtsPaga(guiaId: number, dataPagamento?: string) {
  const qs = dataPagamento ? `?data_pagamento=${dataPagamento}` : "";
  return apiFetch<GuiaFgts>(
    `/api/v1/guias-fgts/${guiaId}/marcar-paga${qs}`,
    { method: "POST" },
  );
}

export function urlPdfFgts(guiaId: number): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  return `${base}/api/v1/guias-fgts/${guiaId}/pdf`;
}

// Helpers UI
export function formatarReal(valor: string | number | null): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = typeof valor === "string" ? parseFloat(valor) : valor;
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatarDataBR(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("T")[0].split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export function formatarPeriodo(yyyymm: string): string {
  if (!yyyymm || yyyymm.length !== 6) return yyyymm;
  return `${yyyymm.slice(4)}/${yyyymm.slice(0, 4)}`;
}

export function statusFgtsPill(status: string): string {
  if (status === "paga") return "pill pill-ok";
  if (status === "vencida") return "pill pill-err";
  if (status === "emitida") return "pill pill-info";
  return "pill pill-muted";
}

// Período "atual" pra default do form = mês anterior (FGTS vence dia 20 do mês +1)
export function periodoMesAnterior(): string {
  const hoje = new Date();
  const ano = hoje.getMonth() === 0 ? hoje.getFullYear() - 1 : hoje.getFullYear();
  const mes = hoje.getMonth() === 0 ? 12 : hoje.getMonth();
  return `${ano}${String(mes).padStart(2, "0")}`;
}
