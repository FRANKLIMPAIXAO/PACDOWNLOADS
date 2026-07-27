import { apiFetch } from "./api";

export type Indicacao = {
  id: number;
  nome_indicador: string;
  contato_indicador: string;
  empresa_indicador: string | null;
  nome_indicado: string;
  contato_indicado: string;
  observacao: string | null;
  status: string; // nova | em_contato | convertida | descartada
  origem: string;
  created_at: string;
};

export function contarNovasIndicacoes() {
  return apiFetch<{ novas: number }>("/api/v1/pac-indica/contagem");
}

export function listarIndicacoes(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<Indicacao[]>(`/api/v1/pac-indica${qs}`);
}

export function atualizarStatusIndicacao(id: number, status: string) {
  return apiFetch<Indicacao>(`/api/v1/pac-indica/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
