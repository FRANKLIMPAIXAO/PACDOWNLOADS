// Camada tipada pra gestão de usuários (admin-only).
import { apiFetch } from "./api";

export type UsuarioAdmin = {
  id: number;
  nome: string;
  email: string;
  ativo: boolean;
  is_admin: boolean;
  is_cliente?: boolean;
  empresa_id?: number | null;
};

export function listarUsuarios() {
  return apiFetch<UsuarioAdmin[]>("/api/v1/usuarios");
}

export type SegurancaDiag = {
  ambiente: string;
  is_production: boolean;
  secret_key_default_ou_fraco: boolean;
  senha_admin_default: boolean;
  cors_wildcard: boolean;
  mock_ligado_em_producao: boolean;
  resend_configurado: boolean;
};

/** Diagnóstico de segurança da config (admin-only). Só flags booleanas. */
export function segurancaDiagnostico() {
  return apiFetch<SegurancaDiag>("/api/v1/usuarios/seguranca-diagnostico");
}

export function criarUsuario(payload: {
  nome: string;
  email: string;
  password: string;
  is_admin: boolean;
}) {
  return apiFetch<UsuarioAdmin>("/api/v1/usuarios", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Cria um acesso de CLIENTE (portal) vinculado a uma empresa. Admin-only. */
export function criarAcessoCliente(payload: {
  nome: string;
  email: string;
  password: string;
  empresa_id: number;
}) {
  return apiFetch<UsuarioAdmin>("/api/v1/usuarios/cliente", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type ConviteResposta = {
  usuario: UsuarioAdmin & { is_cliente?: boolean; empresa_id?: number | null };
  email_enviado: boolean;
  detalhe: string;
  link: string | null;
};

/** Convida um CLIENTE por e-mail: cria acesso SEM senha e dispara o convite.
 * O cliente define a própria senha pelo link. Admin-only. */
export function convidarCliente(payload: { nome: string; email: string; empresa_id: number }) {
  return apiFetch<ConviteResposta>("/api/v1/usuarios/cliente/convidar", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Reenvia o convite (novo link) pra um cliente já cadastrado. Admin-only. */
export function reenviarConvite(usuarioId: number) {
  return apiFetch<ConviteResposta>(`/api/v1/usuarios/${usuarioId}/reenviar-convite`, {
    method: "POST",
  });
}

export function atualizarUsuario(
  id: number,
  payload: {
    nome?: string;
    ativo?: boolean;
    is_admin?: boolean;
    password?: string;
  },
) {
  return apiFetch<UsuarioAdmin>(`/api/v1/usuarios/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
