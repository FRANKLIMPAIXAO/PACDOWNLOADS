// Chat escritório ↔ cliente — lado do ESCRITÓRIO.
import { apiFetch } from "./api";
import type { ChatMensagem } from "../components/chat-thread";

export type { ChatMensagem };

export type Conversa = {
  empresa_id: number;
  empresa_razao_social: string;
  empresa_cnpj: string | null;
  ultima_mensagem: string;
  ultimo_autor: "escritorio" | "cliente";
  ultima_em: string | null;
  nao_lidas: number;
};

/** Caixa de entrada: empresas com conversa, última msg + não lidas. */
export function listarConversas() {
  return apiFetch<{ conversas: Conversa[] }>("/api/v1/mensagens/conversas");
}

export type ThreadEmpresa = {
  empresa_id: number;
  empresa_razao_social: string;
  empresa_cnpj: string | null;
  mensagens: ChatMensagem[];
};

/** Abre a conversa de uma empresa (marca as do cliente como lidas). */
export function threadEmpresa(empresaId: number) {
  return apiFetch<ThreadEmpresa>(`/api/v1/mensagens/empresa/${empresaId}`);
}

/** O escritório envia uma mensagem pra empresa. */
export function enviarMensagemEmpresa(empresaId: number, corpo: string) {
  return apiFetch<ChatMensagem>(`/api/v1/mensagens/empresa/${empresaId}`, {
    method: "POST",
    body: JSON.stringify({ corpo }),
  });
}

/** Total de mensagens de clientes não lidas pelo escritório (badge). */
export function totalNaoLidas() {
  return apiFetch<{ total: number }>("/api/v1/mensagens/nao-lidas");
}
