// Camada API para Guias DCTFWeb (GERARGUIA31 + GERARGUIAANDAMENTO313).
// Backend: app/routes/guias_dctfweb.py

import { API_BASE_URL, apiFetch, getStoredToken } from "./api";

export type OrigemGuiaDctfweb = "ativa" | "andamento";

export type GuiaDctfweb = {
  id: number;
  empresa_id: number;
  categoria: string;
  ano_pa: string;
  mes_pa: string | null;
  dia_pa: string | null;
  cno_afericao: number | null;
  num_proc_reclamatoria: string | null;
  origem: OrigemGuiaDctfweb;
  pdf_path: string;
  emitida_em: string;
  periodo_formatado: string;
};

export type GuiaDctfwebComEmpresa = GuiaDctfweb & {
  empresa_cnpj: string | null;
  empresa_razao_social: string | null;
};

export type EmitirGuiaDctfwebPayload = {
  categoria: string | number;
  ano_pa: string;
  mes_pa?: string | null;
  dia_pa?: string | null;
  cno_afericao?: number | null;
  num_proc_reclamatoria?: string | null;
};

/** Categorias DCTFWeb mais comuns (catálogo Serpro). */
export const CATEGORIAS_DCTFWEB: { value: string; label: string; precisaMes: boolean }[] = [
  { value: "GERAL_MENSAL", label: "40 — Geral Mensal", precisaMes: true },
  { value: "PF_MENSAL", label: "50 — PF Mensal", precisaMes: true },
  { value: "GERAL_13o_SALARIO", label: "41 — Geral 13º Salário", precisaMes: false },
  { value: "PF_13o_SALARIO", label: "51 — PF 13º Salário", precisaMes: false },
  { value: "ESPETACULO_DESPORTIVO", label: "45 — Espetáculo Desportivo", precisaMes: true },
  { value: "AFERICAO", label: "44 — Aferição de Obra", precisaMes: true },
  { value: "RECLAMATORIA_TRABALHISTA", label: "46 — Reclamatória Trabalhista", precisaMes: true },
];

export function listarGuiasEmpresa(empresaId: number) {
  return apiFetch<GuiaDctfweb[]>(`/api/v1/guias-dctfweb/empresa/${empresaId}`);
}

export function listarRecentes() {
  return apiFetch<GuiaDctfwebComEmpresa[]>("/api/v1/guias-dctfweb/recentes");
}

export function emitirAtiva(empresaId: number, payload: EmitirGuiaDctfwebPayload) {
  return apiFetch<GuiaDctfweb>(
    `/api/v1/guias-dctfweb/empresa/${empresaId}/emitir-ativa`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function emitirAndamento(empresaId: number, payload: EmitirGuiaDctfwebPayload) {
  return apiFetch<GuiaDctfweb>(
    `/api/v1/guias-dctfweb/empresa/${empresaId}/emitir-andamento`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function baixarPdf(guiaId: number): Promise<Blob> {
  const token = getStoredToken();
  const resp = await fetch(
    `${API_BASE_URL}/api/v1/guias-dctfweb/${guiaId}/pdf`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!resp.ok) throw new Error(`Erro ao baixar PDF: HTTP ${resp.status}`);
  return await resp.blob();
}

export function formatarDataHoraBR(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function origemLabel(o: OrigemGuiaDctfweb): string {
  return o === "ativa" ? "Ativa (transmitida)" : "Em andamento";
}

export function origemPill(o: OrigemGuiaDctfweb): string {
  return o === "ativa" ? "pill pill-ok" : "pill pill-info";
}
