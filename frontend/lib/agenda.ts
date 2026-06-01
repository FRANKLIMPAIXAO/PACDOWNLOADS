// Camada tipada para agenda fiscal e alertas.

import { apiFetch } from "./api";

export type Severidade = "info" | "ok" | "warn" | "err";

export type EventoAgenda = {
  data: string; // YYYY-MM-DD
  titulo: string;
  descricao: string | null;
  tipo: string; // CND | DAS | DCTFWEB | GPS | FGTS | ECAC | OUTRO
  severidade: Severidade;
  empresa_id: number | null;
  empresa_nome: string | null;
};

export type AlertaItem = {
  titulo: string;
  descricao: string;
  severidade: Severidade;
  tipo: string;
  empresa_id: number | null;
};

export type AlertasResposta = {
  cnds_vencidas: number;
  cnds_a_vencer: number;
  mensagens_nao_lidas: number;
  empresas_sem_procuracao: number;
  itens: AlertaItem[];
};

export function listarEventos(mes?: string) {
  const qs = mes ? `?mes=${mes}` : "";
  return apiFetch<EventoAgenda[]>(`/api/v1/agenda/eventos${qs}`);
}

export function listarAlertas() {
  return apiFetch<AlertasResposta>("/api/v1/agenda/alertas");
}

export function severidadePill(s: Severidade): string {
  if (s === "ok") return "pill pill-ok";
  if (s === "warn") return "pill pill-warn";
  if (s === "err") return "pill pill-err";
  return "pill pill-info";
}

export function tipoColor(tipo: string): string {
  switch (tipo) {
    case "CND":     return "var(--accent-rose)";
    case "DAS":     return "var(--accent-emerald)";
    case "DCTFWEB": return "var(--accent-cyan)";
    case "GPS":     return "var(--accent-violet)";
    case "FGTS":    return "var(--accent-amber)";
    case "ECAC":    return "var(--accent-pink)";
    default:        return "var(--muted)";
  }
}
