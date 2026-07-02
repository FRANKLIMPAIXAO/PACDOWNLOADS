import { apiFetch } from "./api";

export type ResumoMensal = {
  total_xmls_mes: number;
  total_nfe: number;
  total_cte: number;
  total_nfse: number;
  empresas_com_erro: number;
  ultimo_horario_consulta: string | null;
  gerado_em: string;
};

export function obterResumoMensal(competencia?: string) {
  const qs = competencia ? `?competencia=${encodeURIComponent(competencia)}` : "";
  return apiFetch<ResumoMensal>(`/api/v1/relatorios/resumo-mensal${qs}`);
}

async function abrirArquivoAutenticado(path: string, filename: string): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const token = typeof window !== "undefined"
    ? window.localStorage.getItem("pac_xml_token") : null;
  const r = await fetch(`${base}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error(`Falha ${r.status} ao gerar relatorio`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function gerarExcelGeral(competencia?: string) {
  const qs = competencia ? `?competencia=${encodeURIComponent(competencia)}` : "";
  const sufixo = competencia ? `_${competencia}` : "";
  return abrirArquivoAutenticado(
    `/api/v1/relatorios/geral/excel${qs}`,
    `relatorio_geral${sufixo}.xlsx`,
  );
}

export function gerarExcelEmpresa(empresaId: number, nome: string, competencia?: string) {
  const safe = nome.replace(/[^a-zA-Z0-9]+/g, "_");
  const qs = competencia ? `?competencia=${encodeURIComponent(competencia)}` : "";
  const sufixo = competencia ? `_${competencia}` : "";
  return abrirArquivoAutenticado(
    `/api/v1/relatorios/empresa/${empresaId}/excel${qs}`,
    `relatorio_${safe}${sufixo}.xlsx`,
  );
}
