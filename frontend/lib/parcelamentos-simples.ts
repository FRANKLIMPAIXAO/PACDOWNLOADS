// Camada API para Parcelamentos Simples Nacional (PARCSN ordinário).
// Backend: app/routes/parcelamentos_simples.py

import { API_BASE_URL, apiFetch, getStoredToken } from "./api";

export type ParcelamentoSimples = {
  id: number;
  empresa_id: number;
  modalidade: string;
  numero: number;
  data_pedido: string | null;
  situacao: string | null;
  data_situacao: string | null;
  valor_total: string | null;
  valor_total_pago: string | null;
  quantidade_parcelas: number | null;
  parcelas_pagas: number | null;
  parcelas_restantes: number | null;
  percentual_concluido: number | null;
  sincronizado_em: string;
};

export type ParcelamentoSimplesComEmpresa = ParcelamentoSimples & {
  empresa_cnpj: string | null;
  empresa_razao_social: string | null;
};

export type ParcelaGeravel = {
  parcela: number; // YYYYMM
  valor: string;
};

export type SyncParcsnResposta = {
  novos: number;
  atualizados: number;
  erros: number;
  detalhes: Array<{ erro?: string; etapa?: string; numero?: number }> | null;
};

export function listarParcelamentos(empresaId: number) {
  return apiFetch<ParcelamentoSimples[]>(
    `/api/v1/parcelamentos-simples/empresa/${empresaId}`,
  );
}

export function sincronizarParcelamentos(empresaId: number) {
  return apiFetch<SyncParcsnResposta>(
    `/api/v1/parcelamentos-simples/empresa/${empresaId}/sync`,
    { method: "POST" },
  );
}

export function dashboardAtivos() {
  return apiFetch<ParcelamentoSimplesComEmpresa[]>(
    "/api/v1/parcelamentos-simples/ativos",
  );
}

export function listarParcelasGeraveis(empresaId: number) {
  return apiFetch<ParcelaGeravel[]>(
    `/api/v1/parcelamentos-simples/empresa/${empresaId}/parcelas-disponiveis`,
  );
}

/** Emite DAS de UMA parcela e devolve o PDF como Blob. */
export async function emitirDasParcela(
  empresaId: number,
  parcelaAnoMes: number,
): Promise<Blob> {
  const token = getStoredToken();
  const resp = await fetch(
    `${API_BASE_URL}/api/v1/parcelamentos-simples/empresa/${empresaId}/emitir-das`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ parcela_ano_mes: parcelaAnoMes }),
    },
  );
  if (!resp.ok) {
    throw new Error(`Erro ao emitir DAS parcela: HTTP ${resp.status}`);
  }
  return await resp.blob();
}

// ---- Helpers UI ----

export function formatarReal(valor: string | number | null): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = typeof valor === "string" ? parseFloat(valor) : valor;
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function formatarDataBR(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("T")[0].split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export function formatarCompetenciaAnoMes(yyyymm: number): string {
  const s = String(yyyymm);
  if (s.length !== 6) return s;
  return `${s.slice(4)}/${s.slice(0, 4)}`;
}

export function situacaoPill(situacao: string | null): string {
  if (!situacao) return "pill pill-muted";
  const s = situacao.toLowerCase();
  if (s.includes("encerrad") || s.includes("quita")) return "pill pill-ok";
  if (s.includes("parcelament")) return "pill pill-info";
  if (s.includes("rescin") || s.includes("cancel")) return "pill pill-err";
  return "pill pill-warn";
}
