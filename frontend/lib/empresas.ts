// Camada tipada para os endpoints de empresa, integracao Focus e robo.
// Centraliza paths e shapes para evitar duplicacao nas paginas.

import { apiFetch } from "./api";

// --- Tipos ---

export type Empresa = {
  id: number;
  cnpj: string;
  razao_social: string;
  nome_fantasia?: string | null;
  // Cadastrais expandidos
  inscricao_estadual?: string | null;
  inscricao_municipal?: string | null;
  natureza_juridica_codigo?: string | null;
  natureza_juridica_descricao?: string | null;
  tributacao?: string | null;
  regime_tributario?: string | null;
  data_abertura?: string | null;
  data_inicio_sistema?: string | null;
  telefone?: string | null;
  whatsapp?: string | null;
  email_contato?: string | null;
  situacao_cadastral?: string | null;
  // Endereco
  cep?: string | null;
  logradouro_tipo?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  municipio?: string | null;
  uf?: string | null;
  // Tributario (Simples)
  ativo: boolean;
  anexo_simples?: string | null;
  anexo_servico?: string | null;
  atividade?: string | null;
  so_servico?: boolean;
  iss_aliquota?: number | string | null;
  folha_12m?: number | string | null;
  // Metadados
  ultimo_nsu_distribuicao?: string | null;
  data_cadastro?: string | null;
  // Flags de credenciais (booleanas)
  tem_focus_token?: boolean;
  tem_certificado_a1?: boolean;
  cert_a1_validade_ate?: string | null;
  cert_a1_subject?: string | null;
  tem_credenciais_prefeitura?: boolean;
  tem_credenciais_emissor_nacional?: boolean;
  tem_codigo_acesso_simples?: boolean;
  simples_cpf_responsavel?: string | null;
};

export type EmpresaCreatePayload = {
  cnpj: string;
  razao_social: string;
  nome_fantasia?: string;
  inscricao_estadual?: string;
  inscricao_municipal?: string;
  natureza_juridica_codigo?: string;
  natureza_juridica_descricao?: string;
  tributacao?: string;
  regime_tributario?: string;
  data_abertura?: string; // ISO YYYY-MM-DD
  data_inicio_sistema?: string;
  telefone?: string;
  whatsapp?: string;
  email_contato?: string;
  situacao_cadastral?: string;
  cep?: string;
  logradouro_tipo?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  municipio?: string;
  uf?: string;
  ativo?: boolean;
  anexo_simples?: string;
  anexo_servico?: string;
  atividade?: string;
};

export type EmpresaUpdatePayload = Partial<EmpresaCreatePayload>;

export type CnpjBuscaResultado = {
  cnpj: string;
  razao_social: string | null;
  nome_fantasia: string | null;
  natureza_juridica_codigo: string | null;
  natureza_juridica_descricao: string | null;
  data_abertura: string | null;
  telefone: string | null;
  email_contato: string | null;
  situacao_cadastral: string | null;
  cep: string | null;
  logradouro_tipo: string | null;
  logradouro: string | null;
  numero: string | null;
  complemento: string | null;
  bairro: string | null;
  municipio: string | null;
  uf: string | null;
  regime_tributario: string | null;
  _raw: {
    cnae_principal: { codigo: number | null; descricao: string | null };
    porte: string | null;
    capital_social: number | null;
    qsa: unknown[];
  };
};

export type CertificadoInfo = {
  cnpj_certificado: string;
  subject: string;
  validade_ate: string;
  valido_de: string;
  bate_cnpj_empresa: boolean;
  salvo_em: string;
};

export type FocusStatus = {
  empresa_local_id: number;
  empresa_local_cnpj: string;
  tem_token: boolean;
  empresa_focus?: Record<string, unknown> | null;
};

export type EnderecoFocusPayload = {
  logradouro: string;
  numero: string;
  complemento?: string;
  bairro?: string;
  codigo_municipio?: string;
  cidade?: string;
  uf?: string;
  cep?: string;
};

export type EmpresaFocusPayload = {
  cnpj: string;
  inscricao_estadual?: string;
  inscricao_municipal?: string;
  nome: string;
  nome_fantasia?: string;
  fone?: string;
  email?: string;
  regime_tributario?: string;
  endereco: EnderecoFocusPayload;
};

export type RoboResultado = {
  processados: number;
  baixados: number;
  duplicados: number;
  erros: number;
};

// --- Empresas (CRUD local) ---

export function listarEmpresas() {
  return apiFetch<Empresa[]>("/api/v1/empresas");
}

export function obterEmpresa(id: number) {
  return apiFetch<Empresa>(`/api/v1/empresas/${id}`);
}

export function criarEmpresa(payload: EmpresaCreatePayload) {
  return apiFetch<Empresa>("/api/v1/empresas", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function atualizarEmpresa(id: number, payload: EmpresaUpdatePayload) {
  return apiFetch<Empresa>(`/api/v1/empresas/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function inativarEmpresa(id: number) {
  return apiFetch<Empresa>(`/api/v1/empresas/${id}`, { method: "DELETE" });
}

// --- Integracao Focus NFe ---

export function statusFocus(empresaId: number) {
  return apiFetch<FocusStatus>(`/api/v1/empresas/${empresaId}/focus/status`);
}

export function importarFocusToken(empresaId: number, token: string) {
  return apiFetch<Empresa>(`/api/v1/empresas/${empresaId}/focus/token`, {
    method: "PUT",
    body: JSON.stringify({ token }),
  });
}

// --- Auto-cadastro Focus (reusa cert A1 já salvo no PAC) ---

export type AutoCadastrarResultado = {
  ja_tinha_token: boolean;
  token_salvo: boolean;
  mensagem?: string;
  focus_response?: Record<string, unknown>;
};

export type AutoCadastrarTodasResultado = {
  elegiveis: number;
  sucesso: number;
  falhas: number;
  ja_tinham: number;
  sem_cert: number;
  detalhes: Array<{
    empresa_id: number;
    cnpj: string;
    razao_social: string;
    status: "ok" | "erro";
    erro?: string;
  }>;
};

/** Cadastra UMA empresa no Focus reusando o cert A1 já cadastrado no PAC.
 *
 * Pré-req: backend tem FOCUS_MASTER_TOKEN + empresa tem cert_a1_path com .pfx existente.
 * Idempotente: empresa que já tem focus_token retorna `ja_tinha_token=true`.
 */
export function autoCadastrarFocus(empresaId: number) {
  return apiFetch<AutoCadastrarResultado>(
    `/api/v1/empresas/${empresaId}/focus/auto-cadastrar`,
    { method: "POST" },
  );
}

/** Cadastra TODAS as empresas elegíveis (ativa + cert A1 + sem focus_token). */
export function autoCadastrarFocusTodas() {
  return apiFetch<AutoCadastrarTodasResultado>(
    `/api/v1/empresas/focus/auto-cadastrar-todas`,
    { method: "POST" },
  );
}

// --- Importador XLSX Jettax ---

export type ImportXlsxItem = {
  cnpj: string;
  razao_social: string;
  status: "criada" | "atualizada" | "ignorada" | "erro";
  empresa_id?: number;
  mensagem?: string;
};

export type ImportXlsxResultado = {
  linhas_lidas: number;
  criadas: number;
  atualizadas: number;
  ignoradas: number;
  erros: number;
  dry_run: boolean;
  detalhes: ImportXlsxItem[];
};

/** Importa a carteira do Jettax 360 (XLSX) pro PAC.
 *
 * Backend faz UPSERT por CNPJ — cria nova ou atualiza existente.
 * `dryRun=true` simula sem persistir (recomendado pra primeira execução).
 */
export function importarXlsxJettax(arquivo: File, dryRun = false) {
  const form = new FormData();
  form.append("arquivo_xlsx", arquivo);
  return apiFetch<ImportXlsxResultado>(
    `/api/v1/empresas/importar-xlsx?dry_run=${dryRun ? "true" : "false"}`,
    { method: "POST", body: form },
  );
}

export function cadastrarOuAtualizarFocus(
  empresaId: number,
  payload: EmpresaFocusPayload,
  arquivoCertificado: File,
  senhaCertificado: string,
) {
  const form = new FormData();
  form.append("payload_json", JSON.stringify(payload));
  form.append("senha_certificado", senhaCertificado);
  form.append("arquivo_certificado", arquivoCertificado);
  return apiFetch<Record<string, unknown>>(
    `/api/v1/empresas/${empresaId}/focus`,
    { method: "PUT", body: form },
  );
}

export function renovarCertificadoFocus(
  empresaId: number,
  arquivoCertificado: File,
  senhaCertificado: string,
) {
  const form = new FormData();
  form.append("senha_certificado", senhaCertificado);
  form.append("arquivo_certificado", arquivoCertificado);
  return apiFetch<Record<string, unknown>>(
    `/api/v1/empresas/${empresaId}/focus/certificado`,
    { method: "PUT", body: form },
  );
}

// --- Busca CNPJ via BrasilAPI (autopreenchimento) ---

export function buscarCnpjPublico(cnpj: string) {
  const digits = cnpj.replace(/\D+/g, "");
  return apiFetch<CnpjBuscaResultado>(`/api/v1/empresas/_busca-cnpj/${digits}`);
}

// --- Certificado A1 (storage local) ---

export function uploadCertificado(
  empresaId: number,
  arquivo: File,
  senha: string,
  permitirCnpjDiferente = false,
) {
  const form = new FormData();
  form.append("arquivo_certificado", arquivo);
  form.append("senha_certificado", senha);
  form.append("permitir_cnpj_diferente", permitirCnpjDiferente ? "true" : "false");
  return apiFetch<CertificadoInfo>(
    `/api/v1/empresas/${empresaId}/certificado`,
    { method: "POST", body: form },
  );
}

export function deletarCertificado(empresaId: number) {
  return apiFetch<{ removido: boolean }>(
    `/api/v1/empresas/${empresaId}/certificado`,
    { method: "DELETE" },
  );
}

// --- Robo ---

export function executarRoboDistribuicao(
  empresaId: number,
  dataInicio: string,
  dataFim: string,
) {
  return apiFetch<RoboResultado>("/api/v1/robo/distribuicao", {
    method: "POST",
    body: JSON.stringify({
      empresa_id: empresaId,
      data_inicio: dataInicio,
      data_fim: dataFim,
    }),
  });
}
