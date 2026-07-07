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

/** Usuário troca a PRÓPRIA senha (1º acesso com provisória, ou voluntário). */
export function trocarSenha(senhaAtual: string, novaSenha: string) {
  return apiFetch<{ ok: boolean }>("/api/v1/auth/trocar-senha", {
    method: "POST",
    body: JSON.stringify({ senha_atual: senhaAtual, nova_senha: novaSenha }),
  });
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

// --- Multi-empresa do cliente + controle de acessos ---
export type ClienteEmpresaItem = { id: number; razao_social: string | null; cnpj?: string | null; primaria?: boolean };

/** Empresas que um cliente pode acessar (primária + adicionais). */
export function listarEmpresasCliente(usuarioId: number) {
  return apiFetch<{ primaria_id: number; empresas: ClienteEmpresaItem[] }>(
    `/api/v1/usuarios/cliente/${usuarioId}/empresas`,
  );
}

/** Define as empresas ADICIONAIS (além da primária) que o cliente acessa. */
export function definirEmpresasCliente(usuarioId: number, empresaIds: number[]) {
  return apiFetch<{ primaria_id: number; adicionais: number[]; total: number }>(
    `/api/v1/usuarios/cliente/${usuarioId}/empresas`,
    { method: "PUT", body: JSON.stringify({ empresa_ids: empresaIds }) },
  );
}

export type ClienteAcesso = {
  id: number;
  nome: string;
  email: string;
  ativo: boolean;
  motivo_inativacao?: string | null;
  empresas: { id: number; razao_social: string | null }[];
  ultimo_acesso: string | null;
  total_acessos: number;
};

/** Relatório de controle: quais clientes acessam o portal e com que frequência. */
export function clientesAcesso() {
  return apiFetch<{ clientes: ClienteAcesso[] }>("/api/v1/usuarios/clientes-acesso");
}

/** Ativa/INATIVA o acesso de um CLIENTE ao portal (operador). Inativar bloqueia o
 * login e derruba o token na hora. `motivo` só quando inativa (ex.: inadimplente). */
export function definirAtivoCliente(usuarioId: number, ativo: boolean, motivo?: string) {
  return apiFetch<UsuarioAdmin>(`/api/v1/usuarios/cliente/${usuarioId}/ativo`, {
    method: "PATCH",
    body: JSON.stringify({ ativo, motivo: motivo || null }),
  });
}
