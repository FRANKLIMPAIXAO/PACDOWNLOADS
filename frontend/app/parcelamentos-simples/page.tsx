"use client";

import { useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  ParcelaGeravel,
  ParcelamentoSimples,
  ParcelamentoSimplesComEmpresa,
  dashboardAtivos,
  emitirDasParcela,
  formatarCompetenciaAnoMes,
  formatarDataBR,
  formatarReal,
  listarParcelamentos,
  listarParcelasGeraveis,
  sincronizarParcelamentos,
  situacaoPill,
} from "../../lib/parcelamentos-simples";

export default function ParcelamentosSimplesPage() {
  return (
    <ProtectedRoute>
      <Conteudo />
    </ProtectedRoute>
  );
}

function Conteudo() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [parcs, setParcs] = useState<ParcelamentoSimples[] | null>(null);
  const [ativos, setAtivos] = useState<ParcelamentoSimplesComEmpresa[] | null>(null);
  const [parcelasGeraveis, setParcelasGeraveis] = useState<ParcelaGeravel[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    carregar();
  }, []);

  async function carregar() {
    setBusy("carregar");
    setErro(null);
    try {
      const [e, a] = await Promise.all([listarEmpresas(), dashboardAtivos()]);
      setEmpresas(e);
      setAtivos(a);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar");
    } finally {
      setBusy(null);
    }
  }

  async function handleSync() {
    if (empresaId === "") {
      setErro("Selecione uma empresa primeiro.");
      return;
    }
    setBusy("sync");
    setErro(null);
    try {
      const r = await sincronizarParcelamentos(empresaId as number);
      setToast(`Sync OK: ${r.novos} novos, ${r.atualizados} atualizados, ${r.erros} erros`);
      const ps = await listarParcelamentos(empresaId as number);
      setParcs(ps);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao sincronizar");
    } finally {
      setBusy(null);
    }
  }

  async function handleListarParcelas() {
    if (empresaId === "") {
      setErro("Selecione uma empresa primeiro.");
      return;
    }
    setBusy("parcelas");
    setErro(null);
    try {
      const r = await listarParcelasGeraveis(empresaId as number);
      setParcelasGeraveis(r);
      if (r.length === 0) {
        setToast("Nenhuma parcela disponível pra emissão no momento.");
      }
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao listar parcelas");
    } finally {
      setBusy(null);
    }
  }

  async function handleEmitirDas(parcelaAnoMes: number) {
    if (empresaId === "") return;
    setBusy(`emit-${parcelaAnoMes}`);
    setErro(null);
    try {
      const blob = await emitirDasParcela(empresaId as number, parcelaAnoMes);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `DAS_PARCSN_${parcelaAnoMes}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setToast(`DAS da parcela ${formatarCompetenciaAnoMes(parcelaAnoMes)} emitida!`);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao emitir DAS");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Parcelamentos Simples Nacional (PARCSN)</h1>
          <p className="muted">
            Parcelamentos ativos do Simples Nacional (Lei 10.522/2002) via Integra
            Contador. Sincroniza PEDIDOSPARC163 + OBTERPARC164 e emite DAS de parcela
            via GERARDAS161.
          </p>
        </div>
      </header>

      {toast ? (
        <div className="toast" onClick={() => setToast(null)}>{toast}</div>
      ) : null}
      {erro ? (
        <div className="toast toast-error" onClick={() => setErro(null)}>{erro}</div>
      ) : null}

      <section className="table-card" style={{ marginBottom: 16 }}>
        <header>
          <h2>Sincronizar + parcelas disponíveis</h2>
        </header>
        <div style={{ padding: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <select
            value={empresaId}
            onChange={(e) => setEmpresaId(e.target.value === "" ? "" : Number(e.target.value))}
            disabled={busy !== null}
            style={{ minWidth: 280 }}
          >
            <option value="">— Selecione empresa —</option>
            {empresas?.map((e) => (
              <option key={e.id} value={e.id}>
                {e.razao_social} ({e.cnpj})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSync}
            disabled={busy !== null || empresaId === ""}
          >
            {busy === "sync" ? "Sincronizando..." : "Sincronizar parcelamentos"}
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={handleListarParcelas}
            disabled={busy !== null || empresaId === ""}
          >
            {busy === "parcelas" ? "..." : "Listar parcelas disponíveis"}
          </button>
        </div>
      </section>

      {parcelasGeraveis && parcelasGeraveis.length > 0 ? (
        <DataTable
          title={`Parcelas disponíveis pra emissão (${parcelasGeraveis.length})`}
          headers={["Competência", "Valor", "Ação"]}
          rows={parcelasGeraveis.map((p) => [
            formatarCompetenciaAnoMes(p.parcela),
            formatarReal(p.valor),
            <button
              key={`btn-${p.parcela}`}
              className="btn-primary"
              onClick={() => handleEmitirDas(p.parcela)}
              disabled={busy !== null}
            >
              {busy === `emit-${p.parcela}` ? "..." : "Emitir DAS"}
            </button>,
          ])}
        />
      ) : null}

      {parcs && parcs.length > 0 ? (
        <DataTable
          title={`Parcelamentos da empresa (${parcs.length})`}
          subtitle="Sincronizados via Integra Contador."
          headers={[
            "Nº", "Pedido", "Situação", "Valor total", "Pago",
            "Parcelas", "Restantes", "% concluído",
          ]}
          rows={parcs.map((p) => [
            String(p.numero),
            formatarDataBR(p.data_pedido),
            <span key={`sit-${p.id}`} className={situacaoPill(p.situacao)}>
              {p.situacao ?? "—"}
            </span>,
            formatarReal(p.valor_total),
            formatarReal(p.valor_total_pago),
            String(p.quantidade_parcelas ?? "—"),
            String(p.parcelas_restantes ?? "—"),
            p.percentual_concluido !== null ? `${p.percentual_concluido}%` : "—",
          ])}
        />
      ) : null}

      <DataTable
        title={`Dashboard global — Parcelamentos ativos (${ativos?.length ?? 0})`}
        subtitle="Todos os parcelamentos PARCSN em situação 'Em parcelamento'."
        headers={["Empresa", "CNPJ", "Nº", "Situação", "Restantes", "% concluído"]}
        rows={
          ativos?.map((p) => [
            p.empresa_razao_social ?? `#${p.empresa_id}`,
            p.empresa_cnpj ?? "—",
            String(p.numero),
            <span key={`sit-d-${p.id}`} className={situacaoPill(p.situacao)}>
              {p.situacao ?? "—"}
            </span>,
            String(p.parcelas_restantes ?? "—"),
            p.percentual_concluido !== null ? `${p.percentual_concluido}%` : "—",
          ]) ?? []
        }
      />
    </main>
  );
}
