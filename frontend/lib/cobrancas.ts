// Cobranças do portal (recálculo de DAS) — visão do escritório.
// Backend: app/routes/cobrancas.py
import { apiFetch } from "./api";

export type Cobranca = {
  id: number;
  empresa_id: number;
  empresa_razao_social: string | null;
  empresa_cnpj: string | null;
  competencia: string | null;
  tipo: string;
  valor: number;
  descricao: string | null;
  paga: boolean;
  criada_em: string | null;
};

export type CobrancasResumo = { a_receber: number; recebido: number; pendentes: number };
export type CobrancasResp = { cobrancas: Cobranca[]; resumo: CobrancasResumo };

export function listarCobrancas(params: { paga?: boolean; empresaId?: number } = {}) {
  const q = new URLSearchParams();
  if (params.paga !== undefined) q.set("paga", String(params.paga));
  if (params.empresaId !== undefined) q.set("empresa_id", String(params.empresaId));
  const qs = q.toString();
  return apiFetch<CobrancasResp>(`/api/v1/cobrancas${qs ? `?${qs}` : ""}`);
}

export function marcarCobrancaPaga(id: number, paga = true) {
  return apiFetch<{ ok: boolean; id: number; paga: boolean }>(
    `/api/v1/cobrancas/${id}/marcar-paga?paga=${paga}`,
    { method: "POST" },
  );
}

export function brl(v: number | null | undefined): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
export function dataBR(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}
