"use client";

import { useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  GuiaFgts,
  GuiaFgtsComEmpresa,
  emitirGuiaFgts,
  formatarDataBR,
  formatarPeriodo,
  formatarReal,
  listarGuiasFgtsEmpresa,
  listarGuiasFgtsPendentes,
  marcarFgtsPaga,
  periodoMesAnterior,
  statusFgtsPill,
  urlPdfFgts,
} from "../../lib/guias-fgts";

export default function FgtsPage() {
  return (
    <ProtectedRoute>
      <Conteudo />
    </ProtectedRoute>
  );
}

function Conteudo() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [periodo, setPeriodo] = useState<string>(periodoMesAnterior());
  const [guias, setGuias] = useState<GuiaFgts[] | null>(null);
  const [pendentes, setPendentes] = useState<GuiaFgtsComEmpresa[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    carregar();
  }, []);

  async function carregar() {
    setBusy("carregar");
    try {
      const [e, p] = await Promise.all([listarEmpresas(), listarGuiasFgtsPendentes()]);
      setEmpresas(e);
      setPendentes(p);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar");
    } finally {
      setBusy(null);
    }
  }

  async function handleSelecionar(id: number) {
    setEmpresaId(id);
    if (id) {
      setBusy("listar");
      try {
        setGuias(await listarGuiasFgtsEmpresa(id));
      } catch (e) {
        setErro(e instanceof ApiError ? e.message : "Falha ao listar");
      } finally {
        setBusy(null);
      }
    } else {
      setGuias(null);
    }
  }

  async function handleEmitir() {
    if (empresaId === "") {
      setErro("Selecione uma empresa primeiro.");
      return;
    }
    if (!/^\d{6}$/.test(periodo)) {
      setErro("Período inválido. Use YYYYMM (ex: 202412).");
      return;
    }
    const ok = confirm(
      `Emitir guia FGTS Digital de ${formatarPeriodo(periodo)}? ` +
      "Vai gastar 1 consulta paga no Infosimples (~R$ 0,20).",
    );
    if (!ok) return;

    setBusy("emitir");
    setErro(null);
    try {
      const r = await emitirGuiaFgts(empresaId as number, periodo);
      if (r.sucesso && r.guia) {
        setToast(
          `Guia ${formatarPeriodo(r.guia.periodo)} emitida! ` +
          `Total: ${formatarReal(r.guia.valor_total)} · Vencimento: ${formatarDataBR(r.guia.data_vencimento)}`,
        );
        await handleSelecionar(empresaId as number);
        setPendentes(await listarGuiasFgtsPendentes());
      } else {
        setErro(r.erro || "Falha desconhecida ao emitir.");
      }
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao emitir");
    } finally {
      setBusy(null);
    }
  }

  async function handleMarcarPaga(g: GuiaFgts) {
    if (!confirm(`Marcar guia de ${formatarPeriodo(g.periodo)} como PAGA?`)) return;
    setBusy(`paga-${g.id}`);
    try {
      await marcarFgtsPaga(g.id);
      await handleSelecionar(empresaId as number);
      setPendentes(await listarGuiasFgtsPendentes());
      setToast(`Guia de ${formatarPeriodo(g.periodo)} marcada como paga.`);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao marcar");
    } finally {
      setBusy(null);
    }
  }

  function abrirPdf(g: GuiaFgts) {
    if (g.pdf_path) {
      window.open(urlPdfFgts(g.id), "_blank");
    } else if (g.pdf_url_infosimples) {
      window.open(g.pdf_url_infosimples, "_blank");
    } else {
      setErro("PDF não disponível ainda.");
    }
  }

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>FGTS Digital — Guias de Arrecadação</h1>
          <p className="muted">
            Emissão mensal via Infosimples (modo Procurador — cert do escritório no
            painel deles). Cada emissão custa ~R$ 0,20. Re-emitir mesmo período
            atualiza valores (caso houve admissão/demissão).
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
          <h2>Emitir Guia FGTS</h2>
        </header>
        <div style={{ padding: 16, display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 320 }}>
            <span className="muted" style={{ fontSize: 12 }}>Empresa</span>
            <select
              value={empresaId}
              onChange={(e) => handleSelecionar(e.target.value === "" ? 0 : Number(e.target.value))}
              disabled={busy !== null}
            >
              <option value="">— Selecione —</option>
              {empresas?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} ({e.cnpj})
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Competência (YYYYMM)</span>
            <input
              type="text"
              value={periodo}
              onChange={(e) => setPeriodo(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="202412"
              maxLength={6}
              style={{ width: 120 }}
              disabled={busy !== null}
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            onClick={handleEmitir}
            disabled={busy !== null || empresaId === ""}
          >
            {busy === "emitir" ? "Emitindo..." : "▶ Emitir guia (R$ 0,20)"}
          </button>
        </div>
      </section>

      {guias && guias.length > 0 ? (
        <DataTable
          title={`Guias FGTS da empresa (${guias.length})`}
          headers={[
            "Competência", "Vencimento", "Total", "Trabalhadores", "Status", "Pagamento", "Ações",
          ]}
          rows={guias.map((g) => [
            formatarPeriodo(g.periodo),
            formatarDataBR(g.data_vencimento),
            formatarReal(g.valor_total),
            String(g.quantidade_trabalhadores ?? "—"),
            <span key={`s-${g.id}`} className={statusFgtsPill(g.status_calculado)}>
              {g.status_calculado}
              {g.dias_para_vencer !== null && g.status_calculado === "emitida" && (
                <> · {g.dias_para_vencer >= 0 ? `${g.dias_para_vencer}d` : `${-g.dias_para_vencer}d atraso`}</>
              )}
            </span>,
            g.data_pagamento ? formatarDataBR(g.data_pagamento) : "—",
            <div key={`a-${g.id}`} style={{ display: "flex", gap: 4 }}>
              <button
                className="btn-ghost"
                onClick={() => abrirPdf(g)}
                disabled={busy !== null}
                title="Abrir PDF"
              >
                PDF
              </button>
              {g.status_calculado !== "paga" ? (
                <button
                  className="btn-ghost"
                  onClick={() => handleMarcarPaga(g)}
                  disabled={busy !== null}
                  title="Marcar como paga"
                >
                  ✓ paga
                </button>
              ) : null}
            </div>,
          ])}
        />
      ) : empresaId !== "" && guias && guias.length === 0 ? (
        <section className="panel">
          <p className="muted">
            Nenhuma guia FGTS emitida pra essa empresa ainda. Use o formulário acima.
          </p>
        </section>
      ) : null}

      <DataTable
        title={`Dashboard global — Guias FGTS pendentes (${pendentes?.length ?? 0})`}
        subtitle="Todas as guias emitidas e ainda não pagas no PAC, ordenadas por vencimento."
        headers={["Empresa", "Competência", "Vencimento", "Total", "Status"]}
        rows={
          pendentes?.map((g) => [
            g.empresa_razao_social ?? `#${g.empresa_id}`,
            formatarPeriodo(g.periodo),
            formatarDataBR(g.data_vencimento),
            formatarReal(g.valor_total),
            <span key={`p-${g.id}`} className={statusFgtsPill(g.status_calculado)}>
              {g.status_calculado}
            </span>,
          ]) ?? []
        }
      />
    </main>
  );
}
