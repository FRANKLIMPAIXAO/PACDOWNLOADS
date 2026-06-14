"use client";

import { DragEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import {
  Documento,
  DocumentosResumo,
  SincronizarFocusEmpresaResultado,
  SincronizarFocusMultiResultado,
  TipoDocumento,
  UploadResultado,
  baixarPdfDocumento,
  baixarXmlDocumento,
  baixarZipDocumentos,
  formatBrl,
  formatDate,
  listarDocumentos,
  manifestarDocumento,
  resumoDocumentos,
  sincronizarFocusEmpresa,
  sincronizarFocusMultiempresas,
  uploadEmMassa,
  verificarCanceladas,
} from "../../lib/documentos";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import { dfeDistribuirLote, dfeElegiveis, dfeManifestar, dfeManifestarDoc } from "../../lib/dfe";

const TIPOS: TipoDocumento[] = ["NFE", "CTE", "NFSE"];

export default function DocumentosPage() {
  return (
    <ProtectedRoute>
      <DocumentosContent />
    </ProtectedRoute>
  );
}

type FiltroCancelada = "ativas" | "canceladas" | "todas";

function DocumentosContent() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [documentos, setDocumentos] = useState<Documento[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [tipo, setTipo] = useState<TipoDocumento | "">("");
  const [filtroCancelada, setFiltroCancelada] = useState<FiltroCancelada>("ativas");
  // Aba entrada/saída: "" = todas, "emitida" = saída (robô SEFAZ),
  // "recebida" = entrada (Focus DF-e).
  const [filtroOrigem, setFiltroOrigem] = useState<"" | "emitida" | "recebida">("");
  const [resumo, setResumo] = useState<DocumentosResumo | null>(null);
  // Filtro de datas — default: último mês
  const [dataInicio, setDataInicio] = useState<string>(() => {
    const d = new Date();
    d.setUTCMonth(d.getUTCMonth() - 1);
    return d.toISOString().slice(0, 10);
  });
  const [dataFim, setDataFim] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [busyId, setBusyId] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadResultado, setUploadResultado] = useState<UploadResultado | null>(null);
  const [syncFocusModalOpen, setSyncFocusModalOpen] = useState(false);
  const [dfeBusy, setDfeBusy] = useState(false);
  const [dfeMsg, setDfeMsg] = useState<string | null>(null);

  // Distribuição Direta DF-e: puxa as RECEBIDAS de toda a carteira (empresas
  // com cert A1, sem Focus) direto da Receita, de graça. Fatia em blocos de 5.
  async function handleDistribuirDfe() {
    const umaEmpresa = empresaId !== "";
    const nomeSel = umaEmpresa
      ? (empresas.find((e) => e.id === empresaId)?.razao_social ?? "esta empresa")
      : "";
    if (!confirm(
      umaEmpresa
        ? `Puxar as RECEBIDAS de ${nomeSel} direto da Receita (grátis)?\n\n` +
          "Empresa grande pode bater no limite da Receita (656) e pedir ~1h " +
          "entre passadas — rode de novo mais tarde pra completar."
        : "Puxar as RECEBIDAS de TODAS as empresas com certificado (sem Focus), " +
          "direto da Receita — de graça?\n\nNa 1ª vez pode demorar (busca ~90 " +
          "dias de histórico). Pode rodar de novo depois (incremental)."
    )) return;
    setDfeBusy(true);
    setDfeMsg(umaEmpresa ? "Puxando..." : "Buscando empresas elegíveis...");
    setError(null);
    try {
      let ids: number[];
      if (umaEmpresa) {
        ids = [empresaId as number];
      } else {
        const elegiveis = await dfeElegiveis();
        if (elegiveis.length === 0) {
          setDfeMsg(null);
          setToast("Nenhuma empresa elegível (precisa de cert A1 e não ter Focus).");
          return;
        }
        ids = elegiveis.map((e) => e.id);
      }
      let recebidas = 0;
      let completas = 0;
      let erros = 0;
      // Uma empresa por vez, DRENANDO até a Receita dizer "não tem mais"
      // (concluido) — senão paramos cedo e perdíamos as notas mais recentes
      // (NSU é ordem antiga→nova). Guard evita loop infinito.
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        for (let guard = 0; guard < 8; guard++) {
          let res;
          try {
            const r = await dfeDistribuirLote([id], 20);
            res = r.resultados[0];
          } catch {
            erros += 1;
            break;
          }
          if (!res) break;
          recebidas += res.resumos_recebidas_novos || 0;
          completas += res.nfes_completas_novas || 0;
          if (res.erro) { erros += 1; break; }
          if (res.concluido || res.cstat === "656") break;
        }
        setDfeMsg(
          `Processadas ${i + 1}/${ids.length} empresas · ` +
          `${recebidas} recebidas novas` + (erros ? ` · ${erros} com aviso` : ""),
        );
      }
      setDfeMsg(null);
      setToast(
        `✅ DF-e Nacional: ${recebidas} recebidas + ${completas} completas importadas ` +
        `de ${ids.length} empresas (grátis). ${erros ? erros + " com aviso." : ""}`,
      );
      setRefreshTick((t) => t + 1);
    } catch (e) {
      setDfeMsg(null);
      setError(e instanceof ApiError ? e.message : "Falha na Distribuição DF-e.");
    } finally {
      setDfeBusy(false);
    }
  }

  // Manifestação (Ciência da Operação) das recebidas em resumo → libera o XML
  // completo. Contextual: empresa selecionada OU todas as elegíveis. Drena
  // cada empresa (re-chama até restantes_resumo=0).
  async function handleManifestarDfe() {
    const umaEmpresa = empresaId !== "";
    if (!confirm(
      (umaEmpresa
        ? "Dar CIÊNCIA DA OPERAÇÃO nas recebidas (em resumo) desta empresa?"
        : "Dar CIÊNCIA DA OPERAÇÃO em TODAS as recebidas em resumo da carteira?") +
      "\n\nIsso assina e envia o evento à Receita (é a manifestação mais leve, " +
      "sem aceite). Depois rode o DF-e Nacional de novo pra baixar o XML completo."
    )) return;
    setDfeBusy(true);
    setDfeMsg("Manifestando...");
    setError(null);
    try {
      let ids: number[];
      if (umaEmpresa) {
        ids = [empresaId as number];
      } else {
        const elegiveis = await dfeElegiveis();
        ids = elegiveis.map((e) => e.id);
      }
      let manifestadas = 0;
      let erros = 0;
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        for (let guard = 0; guard < 30; guard++) {
          let res;
          try {
            res = await dfeManifestar(id, 20);
          } catch {
            erros += 1;
            break;
          }
          manifestadas += (res.manifestadas || 0) + (res.ja_cientes || 0);
          erros += res.erros?.length || 0;
          if (res.restantes_resumo <= 0) break;
        }
        setDfeMsg(
          `Manifestadas ${manifestadas} · empresas ${i + 1}/${ids.length}` +
          (erros ? ` · ${erros} com aviso` : ""),
        );
      }
      setDfeMsg(null);
      setToast(
        `✍ Manifestação: ${manifestadas} notas com Ciência da Operação. ` +
        `Agora rode "DF-e Nacional" de novo pra baixar o XML completo. ` +
        (erros ? `${erros} com aviso.` : ""),
      );
      setRefreshTick((t) => t + 1);
    } catch (e) {
      setDfeMsg(null);
      setError(e instanceof ApiError ? e.message : "Falha na manifestação.");
    } finally {
      setDfeBusy(false);
    }
  }

  function handleUploadConcluido(r: UploadResultado) {
    setUploadResultado(r);
    setRefreshTick((t) => t + 1);
  }

  function aplicarPeriodoRapido(opcao: "mes-atual" | "mes-anterior" | "30d" | "60d" | "90d" | "ano" | "tudo") {
    const hoje = new Date();
    const fim = hoje.toISOString().slice(0, 10);
    let inicio = fim;
    if (opcao === "mes-atual") {
      inicio = new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
    } else if (opcao === "mes-anterior") {
      const primDiaAnterior = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
      const ultDiaAnterior = new Date(hoje.getFullYear(), hoje.getMonth(), 0);
      setDataInicio(primDiaAnterior.toISOString().slice(0, 10));
      setDataFim(ultDiaAnterior.toISOString().slice(0, 10));
      return;
    } else if (opcao === "30d") {
      const d = new Date(); d.setDate(d.getDate() - 30);
      inicio = d.toISOString().slice(0, 10);
    } else if (opcao === "60d") {
      const d = new Date(); d.setDate(d.getDate() - 60);
      inicio = d.toISOString().slice(0, 10);
    } else if (opcao === "90d") {
      const d = new Date(); d.setDate(d.getDate() - 90);
      inicio = d.toISOString().slice(0, 10);
    } else if (opcao === "ano") {
      inicio = new Date(hoje.getFullYear(), 0, 1).toISOString().slice(0, 10);
    } else if (opcao === "tudo") {
      setDataInicio("");
      setDataFim("");
      return;
    }
    setDataInicio(inicio);
    setDataFim(fim);
  }

  async function handleBaixar(documentoId: number, tipoArq: "xml" | "pdf") {
    setBusyId(`${tipoArq}-${documentoId}`);
    setError(null);
    try {
      if (tipoArq === "xml") await baixarXmlDocumento(documentoId);
      else await baixarPdfDocumento(documentoId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao baixar arquivo.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleBaixarLote(arquivo: "xml" | "pdf" | "ambos") {
    setBusyId(`lote-${arquivo}`);
    setError(null);
    setToast(null);
    const cancFiltro =
      filtroCancelada === "ativas" ? false
        : filtroCancelada === "canceladas" ? true
        : undefined;
    try {
      await baixarZipDocumentos({
        empresaId: empresaId || undefined,
        tipoDocumento: (tipo || undefined) as TipoDocumento | undefined,
        cancelada: cancFiltro,
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        arquivo,
      });
      setToast(`Download ZIP iniciado (${arquivo.toUpperCase()}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao baixar lote.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleManifestar(documentoId: number, ehResumo: boolean) {
    setBusyId(`manifest-${documentoId}`);
    setError(null);
    setToast(null);
    try {
      if (ehResumo) {
        // Nota da Distribuição DF-e (resumo) → manifestação DIRETA assinada.
        const r = await dfeManifestarDoc(documentoId);
        if (r.ok) {
          setToast(
            r.cstat === "573"
              ? "Esta nota já tinha Ciência da Operação (cStat 573)."
              : `Ciência registrada (cStat ${r.cstat})! Rode "DF-e: esta empresa" pra baixar o XML completo.`,
          );
        } else {
          setError(`Não manifestou: cStat ${r.cstat} — ${r.motivo}`);
        }
      } else {
        // Nota legada (Focus) → fluxo antigo.
        const r = await manifestarDocumento(documentoId, "ciencia");
        if (r.ja_estava_manifestado) {
          setToast(`NF ja estava manifestada (${r.manifestado_em?.slice(0, 10)}).`);
        } else {
          const extras: string[] = [];
          if (r.xml_atualizado) extras.push("XML completo OK");
          if (r.pdf_baixado) extras.push("DANFE PDF OK");
          const detalhe = extras.length
            ? ` (${extras.join(" + ")})`
            : " (Focus ainda sincronizando — DANFE chega em ~5min)";
          setToast(`Manifestada · SEFAZ ${r.status_sefaz ?? "OK"}${detalhe}.`);
        }
      }
      setRefreshTick((t) => t + 1);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao manifestar.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleManifestarTodas() {
    if (!empresaId) {
      setError("Selecione uma empresa pra manifestar em lote.");
      return;
    }
    setBusyId("manifest-todas");
    setError(null);
    setToast(null);
    try {
      // Manifestação DIRETA (DF-e, cert próprio, sem Focus). Processa um bloco
      // (limite 20) pra caber no timeout; o usuário clica de novo pra continuar.
      const res = await dfeManifestar(Number(empresaId), 20);
      // cStat 596 = fora do prazo de 10 dias da Ciência (nota antiga) — não é
      // erro de verdade, separamos pra não assustar.
      const fora = (res.erros || []).filter((e) => /596|prazo/i.test(e)).length;
      const outros = (res.erros?.length || 0) - fora;
      setToast(
        `Manifestação DF-e: ${res.manifestadas} nova(s) ciência · ` +
        `${res.ja_cientes} já tinham` +
        (fora ? ` · ${fora} fora do prazo de 10 dias (Ciência só p/ notas recentes)` : "") +
        (outros ? ` · ${outros} erro` : "") +
        `. Restam ${res.restantes_resumo} em resumo. ` +
        `Agora rode "DF-e: esta empresa" pra baixar o XML completo das manifestadas.`,
      );
      setRefreshTick((t) => t + 1);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao manifestar.");
    } finally {
      setBusyId(null);
    }
  }

  useEffect(() => {
    listarEmpresas().then(setEmpresas).catch(() => setEmpresas([]));
  }, []);

  useEffect(() => {
    setDocumentos(null);
    setError(null);
    const cancFiltro =
      filtroCancelada === "ativas" ? false
        : filtroCancelada === "canceladas" ? true
        : undefined;
    listarDocumentos({
      empresaId: empresaId || undefined,
      tipo: (tipo || undefined) as TipoDocumento | undefined,
      cancelada: cancFiltro,
      origem: filtroOrigem || undefined,
      dataInicio: dataInicio || undefined,
      dataFim: dataFim || undefined,
    })
      .then(setDocumentos)
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar documentos.");
      });
    // Totalizadores (emitidas/recebidas) — independem do filtro origem/cancelada
    resumoDocumentos({
      empresaId: empresaId || undefined,
      dataInicio: dataInicio || undefined,
      dataFim: dataFim || undefined,
    })
      .then(setResumo)
      .catch(() => setResumo(null));
  }, [empresaId, tipo, filtroCancelada, filtroOrigem, dataInicio, dataFim, refreshTick]);

  async function handleVerificarCanceladas() {
    setBusyId("verificar-cancel");
    setError(null);
    setToast(null);
    try {
      const r = await verificarCanceladas(empresaId || undefined);
      setToast(
        `Verificadas ${r.verificadas} NFes · ${r.novas_canceladas} novas canceladas detectadas.`
      );
      setRefreshTick((t) => t + 1);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha na verificacao de canceladas.");
    } finally {
      setBusyId(null);
    }
  }

  const empresaPorId = useMemo(() => {
    const map = new Map<number, Empresa>();
    for (const e of empresas) map.set(e.id, e);
    return map;
  }, [empresas]);

  const pendentesManifestacao = useMemo(() => {
    if (!documentos) return 0;
    // Conta só ENTRADAS não-manifestadas (saídas não precisam manifestação).
    // Saída = CNPJ emitente (pos 6-20 da chave) bate com CNPJ da empresa
    // OU campo origem='emitida'.
    return documentos.filter((d) => {
      if (d.tipo_documento !== "NFE") return false;
      if (d.json_original?.manifestado_em) return false;
      if (d.origem === "emitida") return false;  // saída marcada
      const emp = empresaPorId.get(d.empresa_id);
      if (emp && d.chave_acesso && d.chave_acesso.length >= 20) {
        const cnpjEmitente = d.chave_acesso.slice(6, 20);
        const cnpjEmpresa = (emp.cnpj || "").replace(/\D/g, "");
        if (cnpjEmitente === cnpjEmpresa) return false;  // saída detectada pela chave
      }
      return true;
    }).length;
  }, [documentos, empresaPorId]);

  /** True se o doc é SAÍDA (NFe emitida pela própria empresa).
   * Saídas NÃO precisam ser manifestadas — a SEFAZ já tem o XML completo
   * porque a empresa enviou ao autorizar. Manifestação é só pra NFes
   * RECEBIDAS de fornecedores (entradas).
   *
   * Lógica: compara CNPJ emitente (extraído da chave NFe, posições 6-20)
   * com CNPJ da empresa do PAC. Fallback: campo `origem` se vier preenchido.
   */
  const ehSaidaPropria = (d: NonNullable<typeof documentos>[number]): boolean => {
    if (d.origem === "emitida") return true;
    const emp = empresaPorId.get(d.empresa_id);
    if (!emp || !d.chave_acesso || d.chave_acesso.length < 20) return false;
    const cnpjEmitente = d.chave_acesso.slice(6, 20);
    const cnpjEmpresa = (emp.cnpj || "").replace(/\D/g, "");
    return cnpjEmitente === cnpjEmpresa;
  };

  const rows: ReactNode[][] = useMemo(() => {
    if (!documentos) return [];
    return documentos.map((d) => {
      const manifestadoEm = d.json_original?.manifestado_em;
      const isNFe = d.tipo_documento === "NFE";
      const ehSaida = ehSaidaPropria(d);
      // Nota da Distribuição DF-e ainda em resumo: sem XML completo no disco.
      const ehResumo = d.status === "resumo" || !d.xml_path;

      const statusVenda = d.cancelada ? (
        <span
          key={`st-${d.id}`}
          className="pill pill-err"
          title={
            d.motivo_cancelamento
              ? `Cancelada em ${d.cancelada_em || "?"}: ${d.motivo_cancelamento}`
              : "Cancelada"
          }
          style={{ fontSize: "0.72rem" }}
        >
          ✗ Cancelada
        </span>
      ) : (
        <span
          key={`st-${d.id}`}
          className="pill pill-ok"
          style={{ fontSize: "0.72rem" }}
        >
          Ativa
        </span>
      );

      const manifestStatus = manifestadoEm ? (
        <span
          key={`mn-${d.id}`}
          className="pill pill-ok"
          title={`Manifestada em ${manifestadoEm}`}
          style={{ fontSize: "0.72rem" }}
        >
          ✓ {formatDate(manifestadoEm)}
        </span>
      ) : ehSaida ? (
        // NFe própria (saída/venda): NÃO manifesta — a empresa que emitiu já
        // tem o XML completo na SEFAZ. Manifestação é só pra ENTRADAS.
        <span
          key={`mn-${d.id}`}
          className="pill pill-muted"
          title="NFe emitida pela própria empresa (saída). Manifestação não se aplica — só pra notas recebidas de fornecedores."
          style={{ fontSize: "0.72rem" }}
        >
          Saída
        </span>
      ) : isNFe ? (
        <button
          key={`mn-${d.id}`}
          type="button"
          className="btn-secondary"
          style={{ padding: "4px 10px", fontSize: "0.78rem" }}
          onClick={() => handleManifestar(d.id, ehResumo)}
          disabled={busyId === `manifest-${d.id}`}
          title="Registra Ciência da Operação na SEFAZ (libera o XML completo)"
        >
          {busyId === `manifest-${d.id}` ? "..." : "Manifestar"}
        </button>
      ) : (
        <span key={`mn-${d.id}`} className="muted" style={{ fontSize: "0.78rem" }}>
          —
        </span>
      );

      return [
        empresaPorId.get(d.empresa_id)?.razao_social || `#${d.empresa_id}`,
        d.tipo_documento,
        d.numero || "—",
        formatDate(d.data_emissao),
        d.nome_emitente || "—",
        formatBrl(d.valor_total),
        <code key={`chave-${d.id}`} style={{ fontSize: "0.78rem" }}>
          {d.chave_acesso.slice(0, 12)}…{d.chave_acesso.slice(-6)}
        </code>,
        statusVenda,
        manifestStatus,
        <div key={`acoes-${d.id}`} style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            className="btn-secondary"
            style={{ padding: "4px 10px", fontSize: "0.78rem" }}
            onClick={() => handleBaixar(d.id, "xml")}
            disabled={busyId === `xml-${d.id}` || ehResumo}
            title={ehResumo
              ? "XML completo ainda não disponível — nota em resumo. Manifeste primeiro."
              : "Baixa o XML como arquivo"}
          >
            {busyId === `xml-${d.id}` ? "..." : "⬇ XML"}
          </button>
          <button
            type="button"
            className="btn-secondary"
            style={{ padding: "4px 10px", fontSize: "0.78rem" }}
            onClick={() => handleBaixar(d.id, "pdf")}
            disabled={busyId === `pdf-${d.id}` || ehResumo}
            title={ehResumo
              ? "DANFE ainda não disponível — nota em resumo. Manifeste primeiro."
              : "Baixa o DANFE PDF (disponivel apos manifestacao + sync Focus)"}
          >
            {busyId === `pdf-${d.id}` ? "..." : "⬇ PDF"}
          </button>
        </div>,
      ];
    });
  }, [documentos, empresaPorId, busyId]);

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Central de documentos</h2>
          <p className="muted">
            Filtre por empresa ou tipo. Resultados ordenados pelos mais recentes.
          </p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn-primary"
          onClick={handleDistribuirDfe}
          disabled={dfeBusy}
          title="Puxa as RECEBIDAS de toda a carteira direto da Receita com o cert A1 — grátis, sem Focus"
          style={{ alignSelf: "end", background: "rgb(16,185,129)" }}
        >
          {dfeBusy
            ? "Sincronizando..."
            : empresaId !== ""
              ? "⬇ DF-e: esta empresa"
              : "⬇ DF-e Nacional (todas)"}
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={handleManifestarDfe}
          disabled={dfeBusy}
          title="Dá Ciência da Operação (assinada) nas recebidas em resumo → libera o XML completo"
          style={{ alignSelf: "end", background: "rgb(139,92,246)" }}
        >
          {dfeBusy
            ? "..."
            : empresaId !== ""
              ? "✍ Manifestar: esta"
              : "✍ Manifestar DF-e (todas)"}
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => setSyncFocusModalOpen(true)}
          title="Baixar NFes recebidas (entradas) via Focus NFe — DF-e Distribuição (paga)"
          style={{ alignSelf: "end" }}
        >
          ⬇ Sincronizar Focus NFe
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => { setUploadResultado(null); setUploadModalOpen(true); }}
          title="Importar XMLs em massa (ZIP da SEFAZ-GO ou arquivos individuais)"
          style={{ alignSelf: "end" }}
        >
          ⬆ Importar XMLs
        </button>
        <div className="page-actions form-grid" style={{ gridTemplateColumns: "200px 100px 140px 140px 140px" }}>
          <label>
            <span>Empresa</span>
            <select value={empresaId} onChange={(e) => setEmpresaId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Todas</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.id}>{e.razao_social}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Tipo</span>
            <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoDocumento | "")}>
              <option value="">Todos</option>
              {TIPOS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Status</span>
            <select
              value={filtroCancelada}
              onChange={(e) => setFiltroCancelada(e.target.value as FiltroCancelada)}
            >
              <option value="ativas">Ativas</option>
              <option value="canceladas">Canceladas</option>
              <option value="todas">Todas</option>
            </select>
          </label>
          <label>
            <span>Emissão de</span>
            <input
              type="date"
              value={dataInicio}
              onChange={(e) => setDataInicio(e.target.value)}
              max={dataFim || undefined}
            />
          </label>
          <label>
            <span>Emissão até</span>
            <input
              type="date"
              value={dataFim}
              onChange={(e) => setDataFim(e.target.value)}
              min={dataInicio || undefined}
            />
          </label>
        </div>
        </div>
      </header>

      {uploadModalOpen ? (
        <UploadModal
          empresaIdFiltro={empresaId || undefined}
          resultado={uploadResultado}
          onClose={() => setUploadModalOpen(false)}
          onConcluido={handleUploadConcluido}
        />
      ) : null}

      {syncFocusModalOpen ? (
        <SyncFocusModal
          empresas={empresas}
          empresaIdFiltro={empresaId || undefined}
          dataInicio={dataInicio}
          dataFim={dataFim}
          onClose={() => setSyncFocusModalOpen(false)}
          onConcluido={() => setRefreshTick((t) => t + 1)}
        />
      ) : null}

      {/* Atalhos rápidos de período */}
      <section
        className="panel"
        style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", padding: "10px 14px", marginBottom: 8 }}
      >
        <span className="muted" style={{ fontSize: "0.82rem", marginRight: 6 }}>
          Período rápido:
        </span>
        {([
          { id: "mes-atual", label: "Mês atual" },
          { id: "mes-anterior", label: "Mês anterior" },
          { id: "30d", label: "30 dias" },
          { id: "60d", label: "60 dias" },
          { id: "90d", label: "90 dias" },
          { id: "ano", label: "Ano corrente" },
          { id: "tudo", label: "Sem filtro" },
        ] as const).map((opt) => (
          <button
            key={opt.id}
            type="button"
            className="btn-secondary"
            style={{ padding: "4px 12px", fontSize: "0.78rem" }}
            onClick={() => aplicarPeriodoRapido(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </section>

      <section
        className="panel"
        style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", padding: "12px 14px" }}
      >
        <span className="muted" style={{ fontSize: "0.82rem" }}>
          Ações em lote{empresaId ? " (empresa selecionada)" : " (todas as empresas)"}
          {dataInicio || dataFim ? " (com filtro de período)" : ""}:
        </span>
        <button
          type="button"
          className="btn-primary"
          onClick={handleManifestarTodas}
          disabled={!empresaId || busyId === "manifest-todas" || pendentesManifestacao === 0}
          title={
            !empresaId
              ? "Selecione uma empresa primeiro"
              : pendentesManifestacao === 0
              ? "Nenhuma NFe pendente"
              : `Manifesta ${pendentesManifestacao} NFes pendentes + tenta baixar DANFE PDFs`
          }
        >
          {busyId === "manifest-todas"
            ? "Manifestando..."
            : pendentesManifestacao > 0
            ? `Manifestar ${pendentesManifestacao} pendente(s)`
            : "Manifestar todas"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleBaixarLote("xml")}
          disabled={busyId === "lote-xml" || !documentos || documentos.length === 0}
          title="Baixa ZIP com TODOS os XMLs filtrados"
        >
          {busyId === "lote-xml" ? "Gerando ZIP..." : "⬇ ZIP de XMLs"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleBaixarLote("pdf")}
          disabled={busyId === "lote-pdf" || !documentos || documentos.length === 0}
          title="Baixa ZIP com TODOS os DANFE PDFs disponíveis"
        >
          {busyId === "lote-pdf" ? "Gerando ZIP..." : "⬇ ZIP de PDFs"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleBaixarLote("ambos")}
          disabled={busyId === "lote-ambos" || !documentos || documentos.length === 0}
          title="Baixa ZIP com XML + PDF (lado a lado, mesma chave)"
        >
          {busyId === "lote-ambos" ? "Gerando ZIP..." : "⬇ ZIP XML + PDF"}
        </button>
        <span style={{ width: 1, height: 24, background: "var(--border)", margin: "0 4px" }} />
        <button
          type="button"
          className="btn-secondary"
          onClick={handleVerificarCanceladas}
          disabled={busyId === "verificar-cancel"}
          title="Varre XMLs locais e marca como cancelada quando detectar evento SEFAZ"
        >
          {busyId === "verificar-cancel" ? "Verificando..." : "🔍 Verificar cancelamentos"}
        </button>
      </section>

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}
      {dfeMsg ? (
        <p className="toast" style={{ background: "rgba(16,185,129,0.12)", border: "1px solid rgba(16,185,129,0.4)" }}>
          ⬇ {dfeMsg}
        </p>
      ) : null}

      {/* Totalizadores estilo Jettax: separação Emitidas (saída) × Recebidas (entrada) */}
      {resumo ? (
        <section
          className="panel"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 12,
            marginBottom: 8,
          }}
        >
          <TotalCard
            label="Faturamento (emitidas)"
            value={formatBrl(resumo.faturamento)}
            sub={`${resumo.emitidas.ativas} notas de saída`}
            color="rgb(34,197,94)"
          />
          <TotalCard
            label="Emitidas (saída)"
            value={String(resumo.emitidas.total)}
            sub={`${resumo.emitidas.canceladas} canceladas`}
            color="rgb(59,130,246)"
          />
          <TotalCard
            label="Recebidas (entrada)"
            value={String(resumo.recebidas.total)}
            sub={`${resumo.recebidas.canceladas} canceladas`}
            color="rgb(168,85,247)"
          />
          <TotalCard
            label="Total geral"
            value={String(resumo.total_geral)}
            sub="emitidas + recebidas"
            color="rgb(148,163,184)"
          />
        </section>
      ) : null}

      {/* Abas Emitidas / Recebidas (filtro origem) */}
      <section
        className="panel"
        style={{ display: "flex", gap: 6, padding: "8px 12px", marginBottom: 8 }}
      >
        {([
          { id: "", label: "📑 Todas", n: resumo?.total_geral },
          { id: "emitida", label: "⬆ Emitidas (saída)", n: resumo?.emitidas.total },
          { id: "recebida", label: "⬇ Recebidas (entrada)", n: resumo?.recebidas.total },
        ] as const).map((aba) => {
          const ativa = filtroOrigem === aba.id;
          return (
            <button
              key={aba.id || "todas"}
              type="button"
              className={ativa ? "btn-primary" : "btn-secondary"}
              onClick={() => setFiltroOrigem(aba.id as "" | "emitida" | "recebida")}
              style={{ fontSize: "0.85rem" }}
            >
              {aba.label}
              {aba.n !== undefined ? ` (${aba.n})` : ""}
            </button>
          );
        })}
      </section>

      {documentos === null ? (
        <section className="panel"><p className="muted">Carregando documentos...</p></section>
      ) : documentos.length === 0 ? (
        <section className="panel">
          <div className="empty-state">
            Nenhum documento encontrado. Cadastre uma empresa e execute o robo de distribuicao.
          </div>
        </section>
      ) : (
        <DataTable
          headers={[
            "Empresa", "Tipo", "Numero", "Emissao", "Emitente", "Valor", "Chave",
            "Status", "Manifestada", "Acoes",
          ]}
          rows={rows}
          subtitle={
            `${documentos.length} documento(s)` +
            (filtroCancelada === "ativas" ? " (somente ativas — canceladas ocultas)" : "") +
            (filtroCancelada === "canceladas" ? " (somente canceladas)" : "") +
            "."
          }
        />
      )}
    </>
  );
}

// ============ Card de totalizador ============

function TotalCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color: string;
}) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 8,
        padding: "12px 14px",
        borderLeft: `3px solid ${color}`,
      }}
    >
      <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, color }}>{value}</div>
      {sub ? <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{sub}</div> : null}
    </div>
  );
}

// ============ Modal de sincronização Focus NFe ============

/**
 * Modal pra disparar Focus NFe Distribuição de DF-e.
 *
 * Baixa NFes RECEBIDAS contra os CNPJs das empresas (entradas). Requer que a
 * empresa tenha `focus_token` salvo. Janela máxima SEFAZ: 90 dias retroativos.
 *
 * Modos:
 * - Empresa específica → POST /robo/distribuicao
 * - Todas (com Focus token) → POST /robo/multiempresas
 */
function SyncFocusModal({
  empresas,
  empresaIdFiltro,
  dataInicio,
  dataFim,
  onClose,
  onConcluido,
}: {
  empresas: Empresa[];
  empresaIdFiltro?: number;
  dataInicio: string;
  dataFim: string;
  onClose: () => void;
  onConcluido: () => void;
}) {
  const empresasComFocus = useMemo(
    () => empresas.filter((e) => e.ativo && (e as Empresa).tem_focus_token),
    [empresas],
  );
  const [empresaId, setEmpresaId] = useState<number | "todas" | "">(
    empresaIdFiltro && empresasComFocus.some((e) => e.id === empresaIdFiltro)
      ? empresaIdFiltro
      : "",
  );
  // Default período: últimos 30d se não veio do filtro
  const [inicio, setInicio] = useState<string>(() => {
    if (dataInicio) return dataInicio;
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [fim, setFim] = useState<string>(dataFim || new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultadoEmpresa, setResultadoEmpresa] =
    useState<SincronizarFocusEmpresaResultado | null>(null);
  const [resultadoMulti, setResultadoMulti] =
    useState<SincronizarFocusMultiResultado | null>(null);
  // Progresso do loop automático (apenas modo empresa)
  const [progresso, setProgresso] = useState<{
    lote: number;
    baixados: number;
    duplicados: number;
    erros: number;
    finalizado: boolean;
  } | null>(null);

  // Validação simples: SEFAZ guarda só 90 dias
  const intervalLongo = useMemo(() => {
    if (!inicio || !fim) return false;
    const ini = new Date(inicio).getTime();
    const f = new Date(fim).getTime();
    return (f - ini) / (1000 * 60 * 60 * 24) > 90;
  }, [inicio, fim]);

  // Limite de seguranca: max 40 lotes (~1000 NFes) caso loop NSU nao convergir
  const MAX_LOTES = 40;

  async function handleSync() {
    if (empresaId === "") {
      setErro("Selecione uma empresa ou 'Todas com Focus token'.");
      return;
    }
    if (!inicio || !fim) {
      setErro("Período é obrigatório (início e fim).");
      return;
    }
    if (inicio > fim) {
      setErro("Data início é posterior ao fim.");
      return;
    }
    setBusy(true);
    setErro(null);
    setResultadoEmpresa(null);
    setResultadoMulti(null);
    setProgresso(null);
    try {
      if (empresaId === "todas") {
        // Multi: backend itera todas — uma chamada só (sem loop frontend)
        const r = await sincronizarFocusMultiempresas(inicio, fim);
        setResultadoMulti(r);
      } else {
        // Empresa única: loop automatico enquanto tem_mais=true.
        // Backend limita ~25 NFes por chamada pra nao estourar Traefik;
        // aqui acumulamos lotes ate Focus dizer "nao tem mais" ou MAX_LOTES.
        const acumulado = {
          processados: 0,
          baixados: 0,
          duplicados: 0,
          erros: 0,
          tem_mais: false as boolean,
        };
        let lote = 0;
        while (lote < MAX_LOTES) {
          lote++;
          setProgresso({
            lote,
            baixados: acumulado.baixados,
            duplicados: acumulado.duplicados,
            erros: acumulado.erros,
            finalizado: false,
          });
          const r = await sincronizarFocusEmpresa(
            empresaId as number, inicio, fim,
          );
          acumulado.processados += r.processados;
          acumulado.baixados += r.baixados;
          acumulado.duplicados += r.duplicados;
          acumulado.erros += r.erros;
          acumulado.tem_mais = r.tem_mais;
          setProgresso({
            lote,
            baixados: acumulado.baixados,
            duplicados: acumulado.duplicados,
            erros: acumulado.erros,
            finalizado: false,
          });
          // Para o loop quando nao tem mais OU se nada foi processado
          // (NSU nao avancou — proteje contra loop infinito).
          if (!r.tem_mais || r.processados === 0) break;
        }
        setResultadoEmpresa({
          processados: acumulado.processados,
          baixados: acumulado.baixados,
          duplicados: acumulado.duplicados,
          erros: acumulado.erros,
          tem_mais: acumulado.tem_mais,  // se ainda tem após MAX_LOTES
        });
        setProgresso({
          lote,
          baixados: acumulado.baixados,
          duplicados: acumulado.duplicados,
          erros: acumulado.erros,
          finalizado: true,
        });
      }
      onConcluido();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao sincronizar via Focus");
    } finally {
      setBusy(false);
    }
  }

  const algumResultado = resultadoEmpresa !== null || resultadoMulti !== null;

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 640 }}
      >
        <header className="modal-header">
          <h2>⬇ Sincronizar via Focus NFe</h2>
          <button
            type="button"
            className="btn-ghost"
            onClick={onClose}
            disabled={busy}
          >
            ✕
          </button>
        </header>
        <div className="modal-body" style={{ display: "grid", gap: 14 }}>
          <p className="muted">
            Baixa <strong>NFes RECEBIDAS</strong> contra o CNPJ da empresa via{" "}
            <strong>Focus NFe</strong> (DF-e Distribuição). Requer que a empresa
            tenha <code>focus_token</code> cadastrado.
          </p>

          {empresasComFocus.length === 0 ? (
            <div className="toast toast-error">
              ⚠ Nenhuma empresa ativa com Focus token cadastrado. Vai em
              Empresas → editar → aba Integração e cole o token de cada cliente.
            </div>
          ) : null}

          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>
              Empresa ({empresasComFocus.length} com token)
            </span>
            <select
              value={empresaId === "" ? "" : String(empresaId)}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "todas") setEmpresaId("todas");
                else if (v === "") setEmpresaId("");
                else setEmpresaId(Number(v));
              }}
              disabled={busy || empresasComFocus.length === 0}
            >
              <option value="">— Selecione —</option>
              {empresasComFocus.length > 1 ? (
                <option value="todas">
                  📡 Todas ({empresasComFocus.length} empresas)
                </option>
              ) : null}
              {empresasComFocus.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} ({e.cnpj})
                </option>
              ))}
            </select>
          </label>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>
                Período de
              </span>
              <input
                type="date"
                value={inicio}
                onChange={(e) => setInicio(e.target.value)}
                max={fim || undefined}
                disabled={busy}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>
                até
              </span>
              <input
                type="date"
                value={fim}
                onChange={(e) => setFim(e.target.value)}
                min={inicio || undefined}
                max={new Date().toISOString().slice(0, 10)}
                disabled={busy}
              />
            </label>
          </div>

          {intervalLongo ? (
            <div className="toast toast-warn">
              ⚠ Janela maior que 90 dias. SEFAZ só mantém DF-e dos últimos 90 dias,
              eventos mais antigos podem ser ignorados.
            </div>
          ) : null}

          {erro ? <div className="toast toast-error">{erro}</div> : null}

          {/* Progresso ao vivo durante o loop automatico */}
          {busy && progresso ? (
            <div className="toast" style={{ background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.3)" }}>
              ⏳ <strong>Sincronizando lote {progresso.lote}/{MAX_LOTES}</strong> ·{" "}
              {progresso.baixados} XMLs baixados ·{" "}
              {progresso.duplicados} duplicados ·{" "}
              {progresso.erros} erros
              <div style={{ marginTop: 6, height: 4, background: "rgba(255,255,255,0.1)", borderRadius: 2 }}>
                <div style={{
                  width: `${Math.min(100, (progresso.lote / MAX_LOTES) * 100)}%`,
                  height: "100%",
                  background: "rgb(59,130,246)",
                  borderRadius: 2,
                  transition: "width 0.3s",
                }} />
              </div>
            </div>
          ) : null}

          {resultadoEmpresa && !busy ? (
            <div className={resultadoEmpresa.erros > 0 ? "toast toast-warn" : "toast toast-ok"}>
              {resultadoEmpresa.erros > 0 ? "⚠" : "✅"}{" "}
              <strong>{resultadoEmpresa.baixados}</strong> XMLs baixados ·{" "}
              <strong>{resultadoEmpresa.duplicados}</strong> duplicados ·{" "}
              <strong>{resultadoEmpresa.erros}</strong> erros ·{" "}
              <small>({resultadoEmpresa.processados} processados em {progresso?.lote || 1} lote(s))</small>
              {resultadoEmpresa.tem_mais ? (
                <div style={{ marginTop: 8, padding: 8, background: "rgba(245,158,11,0.1)", borderRadius: 4 }}>
                  ⚠ <strong>Limite de {MAX_LOTES} lotes atingido.</strong> Ainda
                  pode haver NFes pra baixar — clica <strong>▶ Sincronizar</strong>{" "}
                  de novo (NSU avançou, vai continuar de onde parou).
                </div>
              ) : null}
            </div>
          ) : null}

          {resultadoMulti ? (
            <div className="toast toast-ok">
              ✅ Processadas <strong>{resultadoMulti.processadas}</strong> empresas ·{" "}
              {resultadoMulti.baixados} XMLs baixados, {resultadoMulti.duplicados} dup,{" "}
              {resultadoMulti.erros} erros.
              {resultadoMulti.detalhes?.length > 0 ? (
                <details style={{ marginTop: 8 }}>
                  <summary>Detalhe por empresa</summary>
                  <ul style={{ margin: 6, fontSize: 12 }}>
                    {resultadoMulti.detalhes.map((d, i) => (
                      <li key={i}>
                        {d.cnpj} —{" "}
                        {d.sucesso
                          ? `${d.baixados} XMLs (${d.duplicados} dup)`
                          : `❌ ${d.mensagem || "erro"}`}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ) : null}

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn-ghost"
              onClick={onClose}
              disabled={busy}
            >
              {algumResultado ? "Fechar" : "Cancelar"}
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSync}
              disabled={busy || empresasComFocus.length === 0 || empresaId === ""}
            >
              {busy && progresso
                ? `Lote ${progresso.lote} · ${progresso.baixados} baixados`
                : busy
                ? "Sincronizando..."
                : "▶ Sincronizar"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Modal de upload em massa ============

function UploadModal({
  empresaIdFiltro,
  resultado,
  onClose,
  onConcluido,
}: {
  empresaIdFiltro?: number;
  resultado: UploadResultado | null;
  onClose: () => void;
  onConcluido: (r: UploadResultado) => void;
}) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleEnviar() {
    if (!arquivo) {
      setErro("Selecione um arquivo .zip ou .xml.");
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      const r = await uploadEmMassa(arquivo, empresaIdFiltro);
      onConcluido(r);
    } catch (err) {
      if (err instanceof ApiError) setErro(err.message);
      else setErro("Falha no upload.");
    } finally {
      setEnviando(false);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setArquivo(f);
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        zIndex: 100,
        display: "grid",
        placeItems: "center",
        padding: 20,
      }}
      onClick={onClose}
    >
      <section
        className="panel"
        style={{ maxWidth: 720, width: "100%", maxHeight: "85vh", overflow: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="page-header" style={{ alignItems: "center" }}>
          <h3>Importar XMLs em massa</h3>
          <button type="button" className="btn-secondary" onClick={onClose}>
            ✕ Fechar
          </button>
        </header>

        <p className="muted" style={{ margin: 0, fontSize: "0.86rem" }}>
          Aceita <strong>ZIP</strong> (ex: <code>29508531000171_01052026_16052026_5250.zip</code> da
          SEFAZ-GO) ou <strong>XML individual</strong>. Sistema detecta automaticamente
          tipo (NFe/NFCe/CTe/NFSe) e empresa pelo CNPJ no XML.
        </p>

        {/* Área drag-drop */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          style={{
            marginTop: 12,
            padding: "32px 24px",
            border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border)"}`,
            borderRadius: 12,
            textAlign: "center",
            background: dragOver ? "var(--bg-2, var(--bg-1))" : "var(--bg-1)",
            transition: "all 0.15s",
          }}
        >
          <p style={{ margin: 0, fontSize: "1rem" }}>
            {arquivo ? `📄 ${arquivo.name} (${(arquivo.size / 1024).toFixed(1)} KB)` : "📁 Arraste o arquivo aqui"}
          </p>
          <p className="muted" style={{ margin: "8px 0 12px 0", fontSize: "0.82rem" }}>
            ou clique abaixo para selecionar
          </p>
          <input
            type="file"
            accept=".zip,.xml"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            style={{ margin: "0 auto" }}
          />
        </div>

        {empresaIdFiltro ? (
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: 8 }}>
            ℹ️ Empresa selecionada no filtro vai ser usada como fallback se XML não
            tiver CNPJ destinatário (caso de resNFe DF-e).
          </p>
        ) : null}

        {erro ? <p className="toast toast-error">{erro}</p> : null}

        {!resultado ? (
          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleEnviar}
              disabled={enviando || !arquivo}
            >
              {enviando ? "Importando..." : "Importar"}
            </button>
          </div>
        ) : (
          <UploadResultadoView resultado={resultado} onClose={onClose} />
        )}
      </section>
    </div>
  );
}

function UploadResultadoView({
  resultado,
  onClose,
}: {
  resultado: UploadResultado;
  onClose: () => void;
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <p className="section-divider">Resultado da importação</p>
      <section className="grid" style={{ marginBottom: 12 }}>
        <article className="metric metric--emerald">
          <span>Persistidos</span>
          <strong>{resultado.persistidos}</strong>
          <p>novos no banco</p>
        </article>
        <article className="metric metric--cyan">
          <span>Duplicados</span>
          <strong>{resultado.duplicados}</strong>
          <p>já existentes</p>
        </article>
        <article
          className={resultado.empresa_nao_cadastrada > 0 ? "metric metric--amber" : "metric metric--cyan"}
        >
          <span>Sem empresa</span>
          <strong>{resultado.empresa_nao_cadastrada}</strong>
          <p>CNPJ não cadastrado</p>
        </article>
        <article
          className={resultado.erros > 0 ? "metric metric--rose" : "metric metric--cyan"}
        >
          <span>Erros</span>
          <strong>{resultado.erros}</strong>
          <p>de {resultado.total_arquivos} total</p>
        </article>
      </section>

      {resultado.detalhes.length > 0 ? (
        <details>
          <summary style={{ cursor: "pointer", marginBottom: 8 }}>
            Detalhes ({resultado.detalhes.length} arquivo(s))
          </summary>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 4, maxHeight: 300, overflow: "auto" }}>
            {resultado.detalhes.map((d, i) => (
              <li
                key={i}
                style={{
                  padding: "6px 10px",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  background: "var(--bg-1)",
                  fontSize: "0.78rem",
                }}
              >
                <span className={`pill ${
                  d.status === "ok" ? "pill-ok"
                  : d.status === "duplicado" ? "pill-warn"
                  : d.status === "erro" ? "pill-err"
                  : "pill-muted"
                }`} style={{ marginRight: 8 }}>
                  {d.status}
                </span>
                <code style={{ fontSize: "0.72rem" }}>{d.arquivo}</code>
                {d.tipo ? <span className="muted" style={{ marginLeft: 8 }}>{d.tipo}</span> : null}
                {d.origem ? <span className="muted" style={{ marginLeft: 8 }}>· {d.origem}</span> : null}
                {d.mensagem ? <div className="muted" style={{ marginTop: 4 }}>{d.mensagem}</div> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="form-actions">
        <button type="button" className="btn-primary" onClick={onClose}>
          Fechar e ver documentos
        </button>
      </div>
    </div>
  );
}
