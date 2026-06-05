// Camada tipada para o módulo Robô SEFAZ-GO.
// Backend: app/routes/robo_sefaz.py

import { apiFetch } from "./api";

export type StatusExecucao = "pendente" | "rodando" | "concluido" | "erro";
export type DisparoExecucao = "cron" | "manual";

export type AgendamentoInfo = {
  ativo: boolean;
  cron_expression: string;        // "0 3 5 * *" (dia 5 às 03h)
  descricao: string;
  uf: string;
  janela: string;                 // "mes_anterior"
};

export type ExecucaoRoboSefaz = {
  id: number;
  disparo: DisparoExecucao;
  uf: string;
  status: StatusExecucao;
  periodo_inicio: string;         // YYYY-MM-DD
  periodo_fim: string;            // YYYY-MM-DD
  empresa_id: number | null;
  iniciado_em: string;            // ISO
  finalizado_em: string | null;
  total_empresas: number;
  com_zip: number;
  sem_notas: number;
  erros: number;
  persistidos: number;
  duplicados: number;
  motivo_erro: string | null;
  duracao_segundos: number | null;
};

export type DetalheEmpresa = {
  empresa_id: number | null;
  cnpj: string | null;
  razao_social: string | null;
  sucesso: boolean;
  motivo: string | null;
  zip_path: string | null;
  upload_pac: {
    total_arquivos?: number;
    persistidos?: number;
    duplicados?: number;
    erros?: number;
  } | null;
  duracao_segundos: number;
  sem_resultados: boolean;
};

export type ExecucaoRoboSefazDetail = ExecucaoRoboSefaz & {
  detalhes: DetalheEmpresa[] | null;
};

export type DispararPayload = {
  empresa_id?: number | null;
  periodo_inicio?: string | null;  // YYYY-MM-DD
  periodo_fim?: string | null;
};

export function obterAgendamento() {
  return apiFetch<AgendamentoInfo>("/api/v1/robo-sefaz/agendamento");
}

export function listarExecucoes(params?: {
  limit?: number;
  offset?: number;
  status?: StatusExecucao;
}) {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  if (params?.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<ExecucaoRoboSefaz[]>(`/api/v1/robo-sefaz/execucoes${suffix}`);
}

export function obterExecucao(id: number) {
  return apiFetch<ExecucaoRoboSefazDetail>(`/api/v1/robo-sefaz/execucoes/${id}`);
}

export function dispararRobo(payload?: DispararPayload) {
  return apiFetch<ExecucaoRoboSefaz>("/api/v1/robo-sefaz/disparar", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

/** Cancela uma execução presa em pendente/rodando (marca como erro). */
export function cancelarExecucao(id: number) {
  return apiFetch<ExecucaoRoboSefaz>(
    `/api/v1/robo-sefaz/execucoes/${id}/cancelar`,
    { method: "POST" },
  );
}

/** Cria nova execução só com as empresas que falharam na execução dada. */
export function reprocessarErros(id: number) {
  return apiFetch<ExecucaoRoboSefaz>(
    `/api/v1/robo-sefaz/execucoes/${id}/reprocessar-erros`,
    { method: "POST" },
  );
}

/** Extrai o nome do .png de debug de dentro do `motivo` de uma falha. */
export function printDoMotivo(motivo: string | null | undefined): string | null {
  if (!motivo) return null;
  const m = motivo.match(/([A-Za-z0-9_.-]+\.png)/);
  return m ? m[1] : null;
}

/** Abre (com token) o screenshot que o agente salvou quando uma empresa falhou. */
export async function abrirDebugScreenshot(arquivo: string): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const token = typeof window !== "undefined"
    ? window.localStorage.getItem("pac_xml_token") : null;
  const r = await fetch(
    `${base}/api/v1/robo-sefaz/debug-screenshot?arquivo=${encodeURIComponent(arquivo)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!r.ok) throw new Error(`Falha ${r.status} ao abrir o print (pode ter sido limpo do disco)`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank");
  if (!w) {
    const a = document.createElement("a");
    a.href = url; a.download = arquivo;
    document.body.appendChild(a); a.click(); a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// Helpers de UI ------------------------------------------------------

export function statusPillClass(status: StatusExecucao): string {
  if (status === "concluido") return "pill pill-ok";
  if (status === "rodando") return "pill pill-info";
  if (status === "pendente") return "pill pill-muted";
  return "pill pill-err"; // erro
}

export function statusLabel(status: StatusExecucao): string {
  if (status === "concluido") return "Concluído";
  if (status === "rodando") return "Rodando";
  if (status === "pendente") return "Pendente";
  return "Erro";
}

export function formatarDuracao(segundos: number | null): string {
  if (segundos === null || segundos === undefined) return "—";
  if (segundos < 60) return `${Math.round(segundos)}s`;
  const m = Math.floor(segundos / 60);
  const s = Math.round(segundos % 60);
  return `${m}min ${s}s`;
}

export function formatarPeriodo(inicio: string, fim: string): string {
  // YYYY-MM-DD → DD/MM/YYYY
  const fmt = (iso: string) => {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
  };
  return `${fmt(inicio)} a ${fmt(fim)}`;
}
