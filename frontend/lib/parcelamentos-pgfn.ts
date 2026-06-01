// Camada API para Parcelamentos PGFN (Dívida Ativa).
// Backend: app/routes/parcelamentos_pgfn.py
//
// PGFN não tem provider automatizado (sem produto Infosimples / sem API Serpro).
// Cadastro MANUAL — usuário entra com numero, modalidade, valores, parcelas
// (provavelmente copiando do extrato do portal REGULARIZE).

import { apiFetch } from "./api";

export type ParcelamentoPgfn = {
  id: number;
  empresa_id: number;
  modalidade: string;
  numero: string;
  data_pedido: string | null;
  situacao: string | null;
  valor_total: string | null;
  valor_total_pago: string | null;
  quantidade_parcelas: number | null;
  parcelas_pagas: number | null;
  parcelas_restantes: number | null;
  percentual_concluido: number | null;
  sincronizado_em: string;
};

export type ParcelamentoPgfnComEmpresa = ParcelamentoPgfn & {
  empresa_cnpj: string | null;
  empresa_razao_social: string | null;
};

export type PgfnPayload = {
  numero: string;
  modalidade?: string;
  data_pedido?: string | null;
  situacao?: string;
  valor_total?: string | null;
  valor_total_pago?: string | null;
  quantidade_parcelas?: number | null;
  parcelas_pagas?: number | null;
};

export function listarParcelamentosPgfn(empresaId: number) {
  return apiFetch<ParcelamentoPgfn[]>(
    `/api/v1/parcelamentos-pgfn/empresa/${empresaId}`,
  );
}

export function listarTodosPgfnAtivos() {
  return apiFetch<ParcelamentoPgfnComEmpresa[]>(
    "/api/v1/parcelamentos-pgfn/ativos",
  );
}

export function criarPgfn(empresaId: number, payload: PgfnPayload) {
  return apiFetch<ParcelamentoPgfn>(
    `/api/v1/parcelamentos-pgfn/empresa/${empresaId}`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function atualizarPgfn(parcelamentoId: number, payload: PgfnPayload) {
  return apiFetch<ParcelamentoPgfn>(
    `/api/v1/parcelamentos-pgfn/${parcelamentoId}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export function deletarPgfn(parcelamentoId: number) {
  return apiFetch<void>(
    `/api/v1/parcelamentos-pgfn/${parcelamentoId}`,
    { method: "DELETE" },
  );
}

export function marcarBaixadoPgfn(parcelamentoId: number) {
  return apiFetch<ParcelamentoPgfn>(
    `/api/v1/parcelamentos-pgfn/${parcelamentoId}/baixar`,
    { method: "POST" },
  );
}

// ---- Helpers UI ----

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

export function situacaoPgfnPill(situacao: string | null): string {
  if (!situacao) return "pill pill-muted";
  const s = situacao.toLowerCase();
  if (s === "nao_listado_mais" || s.includes("baix") || s.includes("quita")) {
    return "pill pill-ok";
  }
  if (s.includes("ativ")) return "pill pill-info";
  if (s.includes("rescin") || s.includes("cancel")) return "pill pill-err";
  return "pill pill-warn";
}

// Modalidades comuns — sugestões pro autocomplete
export const MODALIDADES_PGFN = [
  "Parcelamento Ordinário",
  "Transação Tributária (Lei 13.988)",
  "Transação Excepcional",
  "Programa Especial de Regularização Tributária (PERT)",
  "Programa de Regularização Rural (PRR)",
  "Parcelamento Simplificado",
  "Outros",
];
