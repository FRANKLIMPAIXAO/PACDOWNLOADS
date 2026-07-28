import { apiFetch } from "./api";

export type PortalBloqueio = {
  id: number;
  empresa_id: number;
  cnpj: string;
  rotulo: string | null;
  created_at: string;
};

export function listarBloqueios(empresaId: number) {
  return apiFetch<PortalBloqueio[]>(`/api/v1/portal-bloqueios?empresa_id=${empresaId}`);
}

export function adicionarBloqueio(empresaId: number, cnpj: string, rotulo?: string) {
  return apiFetch<PortalBloqueio>("/api/v1/portal-bloqueios", {
    method: "POST",
    body: JSON.stringify({ empresa_id: empresaId, cnpj, rotulo: rotulo || undefined }),
  });
}

export function removerBloqueio(id: number) {
  return apiFetch<{ ok: boolean }>(`/api/v1/portal-bloqueios/${id}`, { method: "DELETE" });
}
