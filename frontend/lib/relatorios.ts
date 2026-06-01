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

export function obterResumoMensal() {
  return apiFetch<ResumoMensal>("/api/v1/relatorios/resumo-mensal");
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

export function gerarExcelGeral() {
  return abrirArquivoAutenticado(
    "/api/v1/relatorios/geral/excel",
    "relatorio_geral.xlsx",
  );
}

export function gerarExcelEmpresa(empresaId: number, nome: string) {
  const safe = nome.replace(/[^a-zA-Z0-9]+/g, "_");
  return abrirArquivoAutenticado(
    `/api/v1/relatorios/empresa/${empresaId}/excel`,
    `relatorio_${safe}.xlsx`,
  );
}
