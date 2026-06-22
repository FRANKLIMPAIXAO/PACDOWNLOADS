// Gestão (escritório) dos documentos entregues ao cliente (vindos do PAC TAREFAS).
import { apiFetch } from "./api";

export type DocEscritorioOffice = {
  id: number;
  empresa_id: number;
  empresa: string | null;
  cnpj: string | null;
  tipo: string;
  titulo: string;
  competencia: string | null;
  vencimento: string | null;
  valor: number | null;
  tem_arquivo: boolean;
  enviado_em: string | null;
  lido: boolean;
  origem: string;
};

/** Lista os documentos entregues ao cliente (filtra por empresa). */
export function listarDocsEscritorio(empresaId?: number) {
  const qs = empresaId ? `?empresa_id=${empresaId}` : "";
  return apiFetch<{ documentos: DocEscritorioOffice[] }>(`/api/v1/docs-escritorio${qs}`);
}

/** Exclui um documento da área do cliente (enviado errado). Admin-only. */
export function excluirDocEscritorio(id: number) {
  return apiFetch<{ ok: boolean; id: number }>(`/api/v1/docs-escritorio/${id}`, { method: "DELETE" });
}
