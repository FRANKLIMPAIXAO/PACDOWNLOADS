// Admissões enviadas pelos clientes (visão do escritório) + reenvio ao PAC TAREFAS.
import { apiFetch } from "./api";

export type AdmissaoOffice = {
  id: number;
  empresa: string | null;
  cnpj: string | null;
  funcionario: string | null;
  cpf: string | null;
  cargo: string | null;
  data_admissao: string | null;
  status: string; // nova | em_analise | concluida | cancelada
  enviado: boolean;
  envio_erro: string | null;
  anexos: number;
  criado_em: string | null;
};

export function listarAdmissoes(empresaId?: number) {
  const qs = empresaId ? `?empresa_id=${empresaId}` : "";
  return apiFetch<{ pendentes_envio: number; admissoes: AdmissaoOffice[] }>(`/api/v1/admissoes${qs}`);
}

export function reenviarAdmissao(id: number) {
  return apiFetch<{ id: number; enviado: boolean; erro: string | null }>(
    `/api/v1/admissoes/${id}/reenviar`, { method: "POST" });
}

export function reenviarPendentes() {
  return apiFetch<{ tentadas: number; enviadas: number }>(
    "/api/v1/admissoes/reenviar-pendentes", { method: "POST" });
}

/** Exclui uma solicitação de admissão (ex.: teste). Admin-only. */
export function excluirAdmissao(id: number) {
  return apiFetch<{ ok: boolean; id: number }>(`/api/v1/admissoes/${id}`, { method: "DELETE" });
}
