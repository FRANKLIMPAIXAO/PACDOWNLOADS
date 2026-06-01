"use client";

import { useEffect, useMemo, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  CATEGORIAS_DCTFWEB,
  EmitirGuiaDctfwebPayload,
  GuiaDctfwebComEmpresa,
  baixarPdf,
  emitirAndamento,
  emitirAtiva,
  formatarDataHoraBR,
  listarRecentes,
  origemLabel,
  origemPill,
} from "../../lib/guias-dctfweb";

export default function DctfwebPage() {
  return (
    <ProtectedRoute>
      <Conteudo />
    </ProtectedRoute>
  );
}

function Conteudo() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [recentes, setRecentes] = useState<GuiaDctfwebComEmpresa[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Form
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [categoria, setCategoria] = useState<string>("GERAL_MENSAL");
  const hoje = new Date();
  const mesAnt = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
  const [anoPa, setAnoPa] = useState<string>(String(mesAnt.getFullYear()));
  const [mesPa, setMesPa] = useState<string>(String(mesAnt.getMonth() + 1).padStart(2, "0"));

  const categoriaConfig = useMemo(
    () => CATEGORIAS_DCTFWEB.find((c) => c.value === categoria),
    [categoria],
  );

  useEffect(() => {
    carregar();
  }, []);

  async function carregar() {
    setBusy("carregar");
    setErro(null);
    try {
      const [e, g] = await Promise.all([listarEmpresas(), listarRecentes()]);
      setEmpresas(e);
      setRecentes(g);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar");
    } finally {
      setBusy(null);
    }
  }

  function montarPayload(): EmitirGuiaDctfwebPayload {
    const p: EmitirGuiaDctfwebPayload = { categoria, ano_pa: anoPa };
    if (categoriaConfig?.precisaMes && mesPa) {
      p.mes_pa = mesPa;
    }
    return p;
  }

  async function handleEmitir(origem: "ativa" | "andamento") {
    if (empresaId === "") {
      setErro("Selecione uma empresa primeiro.");
      return;
    }
    const fn = origem === "ativa" ? emitirAtiva : emitirAndamento;
    setBusy(`emit-${origem}`);
    setErro(null);
    try {
      const g = await fn(empresaId as number, montarPayload());
      setToast(
        `Guia DCTFWeb #${g.id} (${origem}) emitida pra ${g.periodo_formatado}. Clique "PDF" pra baixar.`,
      );
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao emitir guia");
    } finally {
      setBusy(null);
    }
  }

  async function handleBaixar(guiaId: number, periodo: string, origem: string) {
    setBusy(`pdf-${guiaId}`);
    setErro(null);
    try {
      const blob = await baixarPdf(guiaId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `DCTFWeb_${origem}_${periodo.replace("/", "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao baixar PDF");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>DCTFWeb — Emissão de Guias</h1>
          <p className="muted">
            Emite DARF DCTFWeb via Integra Contador. <strong>Ativa</strong> =
            declaração já transmitida (GERARGUIA31). <strong>Andamento</strong> =
            apuração ainda não transmitida (GERARGUIAANDAMENTO313).
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
          <h2>Nova guia DCTFWeb</h2>
        </header>
        <div
          style={{
            padding: 16,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <label>
            <span style={{ display: "block", marginBottom: 4 }}>Empresa</span>
            <select
              value={empresaId}
              onChange={(e) => setEmpresaId(e.target.value === "" ? "" : Number(e.target.value))}
              disabled={busy !== null}
              style={{ width: "100%" }}
            >
              <option value="">— Selecione —</option>
              {empresas?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} ({e.cnpj})
                </option>
              ))}
            </select>
          </label>
          <label>
            <span style={{ display: "block", marginBottom: 4 }}>Categoria</span>
            <select
              value={categoria}
              onChange={(e) => setCategoria(e.target.value)}
              disabled={busy !== null}
              style={{ width: "100%" }}
            >
              {CATEGORIAS_DCTFWEB.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span style={{ display: "block", marginBottom: 4 }}>Ano</span>
            <input
              type="number"
              min={2020}
              max={2099}
              value={anoPa}
              onChange={(e) => setAnoPa(e.target.value)}
              disabled={busy !== null}
              style={{ width: "100%" }}
            />
          </label>
          {categoriaConfig?.precisaMes ? (
            <label>
              <span style={{ display: "block", marginBottom: 4 }}>Mês</span>
              <select
                value={mesPa}
                onChange={(e) => setMesPa(e.target.value)}
                disabled={busy !== null}
                style={{ width: "100%" }}
              >
                {Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0")).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
          ) : (
            <div style={{ padding: "8px 0" }}>
              <span className="muted">Categoria anual: não precisa de mês.</span>
            </div>
          )}
        </div>
        <div style={{ padding: "0 16px 16px", display: "flex", gap: 12 }}>
          <button
            type="button"
            className="btn-primary"
            onClick={() => handleEmitir("ativa")}
            disabled={busy !== null || empresaId === ""}
          >
            {busy === "emit-ativa" ? "Emitindo..." : "▶ Emitir guia ATIVA (transmitida)"}
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => handleEmitir("andamento")}
            disabled={busy !== null || empresaId === ""}
          >
            {busy === "emit-andamento" ? "Emitindo..." : "⌛ Emitir guia em ANDAMENTO"}
          </button>
        </div>
      </section>

      {recentes === null ? (
        <p className="muted">Carregando…</p>
      ) : recentes.length === 0 ? (
        <section className="table-card">
          <header><h2>Histórico de guias DCTFWeb</h2></header>
          <p className="muted" style={{ padding: 16 }}>
            Nenhuma guia emitida ainda. Use o formulário acima pra emitir a primeira.
          </p>
        </section>
      ) : (
        <DataTable
          title={`Histórico de guias DCTFWeb (${recentes.length})`}
          subtitle="Ordenado por emissão mais recente."
          headers={[
            "Empresa", "Categoria", "Período", "Origem",
            "Emitida em", "Ação",
          ]}
          rows={recentes.map((g) => [
            <span key={`emp-${g.id}`}>
              <strong>{g.empresa_razao_social ?? `#${g.empresa_id}`}</strong>
              <br />
              <small className="muted">{g.empresa_cnpj}</small>
            </span>,
            g.categoria,
            g.periodo_formatado,
            <span key={`org-${g.id}`} className={origemPill(g.origem)}>
              {origemLabel(g.origem)}
            </span>,
            formatarDataHoraBR(g.emitida_em),
            <button
              key={`btn-${g.id}`}
              type="button"
              className="btn-ghost"
              onClick={() => handleBaixar(g.id, g.periodo_formatado, g.origem)}
              disabled={busy !== null}
            >
              {busy === `pdf-${g.id}` ? "..." : "Baixar PDF"}
            </button>,
          ])}
        />
      )}
    </main>
  );
}
