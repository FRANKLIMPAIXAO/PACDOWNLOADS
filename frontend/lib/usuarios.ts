// Camada tipada pra gestão de usuários (admin-only).
import { apiFetch } from "./api";

export type UsuarioAdmin = {
  id: number;
  nome: string;
  email: string;
  ativo: boolean;
  is_admin: boolean;
};

export function listarUsuarios() {
  return apiFetch<UsuarioAdmin[]>("/api/v1/usuarios");
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
