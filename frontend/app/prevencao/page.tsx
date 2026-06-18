"use client";

import Link from "next/link";
import { Fragment, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import {
  CndDashboardLinha,
  StatusCertidao,
  TIPOS_CND,
  TipoCertidao,
  dashboardCnds,
  efetivoLabel,
  efetivoPillClass,
  renovarVencendo,
} from "../../lib/cnds";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  consultarDte,
  Dte,
  listarCaixaPostal,
  MensagemEcac,
  obterProcuracao,
  Procuracao,
  syncCaixaPostal,
} from "../../lib/integra";

type LinhaPrevencao = {
  empresa: Empresa;
  procuracao: Procuracao | null;
  mensagens: MensagemEcac[];
  dte: Dte | null;
};

export default function PrevencaoPage() {
  return (
    <ProtectedRoute>
      <PrevencaoContent />
    </ProtectedRoute>
  );
}

function PrevencaoContent() {
  const [linhas, setLinhas] = useState<LinhaPrevencao[] | null>(null);
  const [cnds, setCnds] = useState<CndDashboardLinha[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [renovandoTodas, setRenovandoTodas] = useState(false);

  const carregarTudo = useCallback(async () => {
    setError(null);
    try {
      const empresas = await listarEmpresas();
      const dadosLinhas = await Promise.all(
        empresas.map(async (empresa) => {
          const linha: LinhaPrevencao = {
            empresa, procuracao: null, mensagens: [], dte: null,
          };
          try { linha.mensagens = await listarCaixaPostal(empresa.id); } catch {}
          try { linha.procuracao = await obterProcuracao(empresa.id); } catch {}
          try { linha.dte = await consultarDte(empresa.id); } catch {}
          return linha;
        }),
      );
      setLinhas(dadosLinhas);
      const cndList = await dashboardCnds();
      setCnds(cndList);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao carregar prevencao.");
    }
  }, []);

  useEffect(() => { carregarTudo(); }, [carregarTudo]);

  async function handleSync(empresaId: number) {
    setSyncingId(empresaId);
    try {
      await syncCaixaPostal(empresaId);
      await carregarTudo();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    } finally {
      setSyncingId(null);
    }
  }

  async function handleRenovarTodas() {
    setRenovandoTodas(true);
    setToast(null); setError(null);
    try {
      const r = await renovarVencendo(7);
      setToast(
        `Robô SEFAZ: ${r.sucesso} renovadas · ${r.falhas} falhas · ${r.pulados} ainda válidas.`,
      );
      await carregarTudo();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao renovar.");
    } finally {
      setRenovandoTodas(false);
    }
  }

  const totais = useMemo(() => {
    if (!linhas || !cnds) return null;
    const empresas = linhas.length;
    const procAtivas = linhas.filter((l) => l.procuracao?.situacao === "ATIVA").length;
    const naoLidas = linhas.reduce(
      (sum, l) => sum + l.mensagens.filter((m) => m.indicador_leitura === "0").length,
      0,
    );
    const optantesDte = linhas.filter((l) => l.dte?.indicador_optante).length;
    let cndsValidas = 0;
    let cndsAVencer = 0;
    let cndsVencidas = 0;
    let cndsPendencia = 0;
    for (const c of cnds) {
      for (const tipo of TIPOS_CND) {
        const cert = c[tipo.tipo.toLowerCase() as keyof CndDashboardLinha] as
          | { status: StatusCertidao; situacao_fiscal?: string | null } | null;
        if (!cert) continue;
        if (cert.situacao_fiscal === "pendencias") cndsPendencia++;
        else if (cert.status === "VALIDA" && cert.situacao_fiscal !== "verificar") cndsValidas++;
        else if (cert.status === "A_VENCER") cndsAVencer++;
        else if (cert.status === "VENCIDA") cndsVencidas++;
      }
    }
    return { empresas, procAtivas, naoLidas, optantesDte, cndsValidas, cndsAVencer, cndsVencidas, cndsPendencia };
  }, [linhas, cnds]);

  if (error) {
    return (
      <section className="panel">
        <p className="toast toast-error">{error}</p>
      </section>
    );
  }

  if (!linhas || !cnds) {
    return (
      <section className="panel">
        <p className="muted">Carregando prevencao...</p>
      </section>
    );
  }

  if (linhas.length === 0) {
    return (
      <section className="panel">
        <header className="page-header">
          <div>
            <h2>Prevencao</h2>
            <p className="muted">Caixa Postal eCAC, DTE, Procuracoes e CND via Integra Contador.</p>
          </div>
        </header>
        <div className="empty-state">
          Nenhuma empresa cadastrada.{" "}
          <Link href="/empresas/novo" className="row-link">Cadastre uma empresa</Link>.
        </div>
      </section>
    );
  }

  const rows: ReactNode[][] = linhas.map((l) => {
    const naoLidas = l.mensagens.filter((m) => m.indicador_leitura === "0").length;
    return [
      <Link key={`e-${l.empresa.id}`} href={`/empresas/${l.empresa.id}`} className="row-link">
        {l.empresa.razao_social}
      </Link>,
      l.empresa.cnpj,
      l.procuracao?.situacao === "ATIVA" ? (
        <span key={`p-${l.empresa.id}`} className="pill pill-ok">Ativa</span>
      ) : (
        <span key={`p-${l.empresa.id}`} className="pill pill-warn">{l.procuracao?.situacao || "Pendente"}</span>
      ),
      l.dte === null ? (
        <span key={`d-${l.empresa.id}`} className="muted">—</span>
      ) : l.dte.indicador_optante ? (
        <span key={`d-${l.empresa.id}`} className="pill pill-ok">Optante</span>
      ) : (
        <span key={`d-${l.empresa.id}`} className="pill pill-warn">Nao</span>
      ),
      <span key={`m-${l.empresa.id}`}>
        {l.mensagens.length}
        {naoLidas > 0 ? <> · <span className="pill pill-warn">{naoLidas} novas</span></> : null}
      </span>,
      <button
        key={`s-${l.empresa.id}`}
        type="button"
        className="btn-secondary"
        style={{ padding: "5px 11px", fontSize: "0.82rem" }}
        onClick={() => handleSync(l.empresa.id)}
        disabled={syncingId === l.empresa.id}
      >
        {syncingId === l.empresa.id ? "..." : "Sync"}
      </button>,
    ];
  });

  // Coluna principal usa apenas tipos NAO sob demanda (5 colunas).
  // FEDERAL_OFICIAL nao entra (eh emitido pontualmente para licitacoes/bancos).
  const tiposTabela = TIPOS_CND.filter((t) => !t.sob_demanda);
  const cndRows: ReactNode[][] = cnds.map((c) => [
    <Link key={`ce-${c.empresa_id}`} href={`/empresas/${c.empresa_id}`} className="row-link">
      {c.empresa_razao_social}
    </Link>,
    ...tiposTabela.map((t) => {
      const cert = c[t.tipo.toLowerCase() as keyof CndDashboardLinha] as
        | { status: StatusCertidao; situacao_fiscal?: string | null; pendencias?: string[]; data_validade: string } | null;
      if (!cert) {
        return <span key={`${c.empresa_id}-${t.tipo}`} className="pill pill-muted">—</span>;
      }
      const pend = cert.pendencias && cert.pendencias.length ? ` · ${cert.pendencias.join(" · ")}` : "";
      return (
        <span key={`${c.empresa_id}-${t.tipo}`} className={efetivoPillClass(cert)} title={`${t.fonte} · validade ${cert.data_validade}${pend}`}>
          {efetivoLabel(cert)}
        </span>
      );
    }),
    <ScoreBar key={`sc-${c.empresa_id}`} score={c.score} />,
  ]);

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Prevencao</h2>
          <p className="muted">
            CND, Caixa Postal eCAC, DTE e Procuracoes — visao consolidada do escritorio.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleRenovarTodas}
            disabled={renovandoTodas}
          >
            {renovandoTodas ? "Renovando..." : "🤖 Robo SEFAZ — renovar todas vencendo"}
          </button>
        </div>
      </header>

      {toast ? <p className="toast">{toast}</p> : null}

      {totais ? (
        <section className="grid">
          <article className="metric metric--emerald">
            <span>Empresas monitoradas</span>
            <strong>{totais.empresas}</strong>
            <p>com integracao prevencao</p>
          </article>
          <article className="metric metric--cyan">
            <span>Procuracoes ativas</span>
            <strong>{totais.procAtivas}</strong>
            <p>de {totais.empresas} empresas</p>
          </article>
          <article className="metric metric--amber">
            <span>Mensagens nao lidas</span>
            <strong>{totais.naoLidas}</strong>
            <p>caixa postal eCAC</p>
          </article>
          <article className="metric metric--rose">
            <span>CNDs com pendência</span>
            <strong>{totais.cndsPendencia}</strong>
            <p>{totais.cndsVencidas} vencidas · {totais.cndsAVencer} a vencer · {totais.cndsValidas} válidas</p>
          </article>
        </section>
      ) : null}

      <header className="page-header" style={{ marginTop: 8 }}>
        <div>
          <h3>Controle de CNDs</h3>
          <p className="muted">
            Federal · FGTS · Trabalhista · Estadual · Municipal — clique numa empresa para gerenciar.
          </p>
        </div>
      </header>
      <DataTable
        headers={["Empresa", ...tiposTabela.map((t) => t.label), "Score"]}
        rows={cndRows}
        subtitle={`${cnds.length} empresa(s).`}
      />

      <header className="page-header" style={{ marginTop: 8 }}>
        <div>
          <h3>Caixa Postal · DTE · Procuracoes</h3>
          <p className="muted">Status de procuracao e mensagens da Receita Federal por empresa.</p>
        </div>
      </header>
      <DataTable
        headers={["Empresa", "CNPJ", "Procuracao", "DTE", "Mensagens", "Acao"]}
        rows={rows}
      />
    </>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const cls = score >= 0.8 ? "" : score >= 0.5 ? "score-bar--med" : "score-bar--low";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 120 }}>
      <div className={`score-bar ${cls}`}>
        <div className="score-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: "0.85rem", color: "var(--muted-strong)", minWidth: 32 }}>{pct}%</span>
    </div>
  );
}
