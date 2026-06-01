"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

import { AlertasCard } from "../components/alertas-card";
import { ApuracaoDashboardCard } from "../components/apuracao-dashboard-card";
import { CalendarioFiscal } from "../components/calendario-fiscal";
import { DataTable } from "../components/data-table";
import { ProtectedRoute } from "../components/protected-route";
import { ApiError } from "../lib/api";
import {
  LinhaPorEmpresa,
  ResumoDashboard,
  listaPorEmpresa,
  resumoDashboard,
} from "../lib/dashboard";
import { Documento, formatBrl, formatDate, listarDocumentos } from "../lib/documentos";

export default function HomePage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}

function DashboardContent() {
  const [resumo, setResumo] = useState<ResumoDashboard | null>(null);
  const [ultimosDocumentos, setUltimosDocumentos] = useState<Documento[] | null>(null);
  const [linhasEmpresa, setLinhasEmpresa] = useState<LinhaPorEmpresa[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Carrega em paralelo, mas tolera falha parcial — se "por-empresa" der 404
    // (backend velho sem o endpoint novo), o dashboard ainda renderiza.
    Promise.allSettled([
      resumoDashboard(),
      listarDocumentos({ cancelada: false }),
      listaPorEmpresa(),
    ]).then(([rResumo, rDocs, rEmp]) => {
      if (rResumo.status === "fulfilled") {
        setResumo(rResumo.value);
      } else {
        const e = rResumo.reason;
        setError(e instanceof ApiError ? e.message : "Falha ao carregar resumo do dashboard.");
      }
      if (rDocs.status === "fulfilled") {
        setUltimosDocumentos(rDocs.value.slice(0, 8));
      } else {
        setUltimosDocumentos([]);
      }
      if (rEmp.status === "fulfilled") {
        setLinhasEmpresa(rEmp.value);
      } else {
        // Endpoint novo pode não existir em backend antigo — só esconde a tabela.
        setLinhasEmpresa([]);
      }
    });
  }, []);

  if (error) {
    return (
      <section className="panel">
        <p className="toast toast-error">{error}</p>
      </section>
    );
  }

  if (!resumo || !ultimosDocumentos) {
    return (
      <section className="panel">
        <p className="muted">Carregando dashboard...</p>
      </section>
    );
  }

  const docsRows: ReactNode[][] = ultimosDocumentos.map((d) => [
    d.nome_emitente || "—",
    <span key={`tipo-${d.id}`} className="pill pill-info">{d.tipo_documento}</span>,
    d.numero || "—",
    formatDate(d.data_emissao),
    formatBrl(d.valor_total),
    d.cancelada
      ? <span key={`s-${d.id}`} className="pill pill-err">Cancelada</span>
      : <span key={`s-${d.id}`} className="pill pill-ok">Ativa</span>,
  ]);

  const fornecedoresRows: ReactNode[][] = resumo.top_fornecedores.map((f, i) => [
    `#${i + 1}`,
    f.nome || "—",
    f.cnpj || "—",
    f.qtd,
    formatBrl(f.valor),
  ]);

  return (
    <>
      <section className="hero">
        <article className="hero-note">
          <div>
            <span className="badge">Painel operacional · {resumo.mes}</span>
            <h2 style={{ marginTop: 12 }}>
              Central fiscal moderna para o seu escritório.
            </h2>
            <p style={{ marginTop: 8 }}>
              {resumo.empresas.ativas} empresa{resumo.empresas.ativas === 1 ? "" : "s"} ativa{resumo.empresas.ativas === 1 ? "" : "s"} ·{" "}
              {resumo.documentos_mes.geral_acumulado} documento{resumo.documentos_mes.geral_acumulado === 1 ? "" : "s"} sincronizado{resumo.documentos_mes.geral_acumulado === 1 ? "" : "s"} via DF-e.
            </p>
          </div>
          <div className="page-actions">
            <Link href="/empresas/novo" className="cta">+ Nova empresa</Link>
            <Link href="/documentos" className="btn-secondary">Ver documentos</Link>
          </div>
        </article>
      </section>

      {/* Linha 1 — Operação fiscal do mês */}
      <section className="grid">
        <article className="metric metric--emerald">
          <span>Empresas ativas</span>
          <strong>{resumo.empresas.ativas}</strong>
          <p>de {resumo.empresas.total} cadastradas</p>
        </article>
        <article className="metric metric--cyan">
          <span>NFes do mês</span>
          <strong>{resumo.documentos_mes.total}</strong>
          <p>{resumo.documentos_mes.canceladas > 0
            ? `${resumo.documentos_mes.canceladas} canceladas excluídas`
            : "sem cancelamentos"}</p>
        </article>
        <article className="metric metric--violet">
          <span>Faturamento mês</span>
          <strong>{formatBrl(resumo.documentos_mes.valor_total)}</strong>
          <p>NFes recebidas (ativas)</p>
        </article>
        <article
          className={
            resumo.manifestacao.pendentes > 0
              ? "metric metric--amber"
              : "metric metric--emerald"
          }
        >
          <span>Manifestação pendente</span>
          <strong>{resumo.manifestacao.pendentes}</strong>
          <p>
            {resumo.manifestacao.manifestadas} já manifestadas ·{" "}
            <Link href="/documentos" className="row-link">ver</Link>
          </p>
        </article>
      </section>

      {/* Linha 2 — Alertas críticos */}
      <section className="grid">
        <article
          className={
            resumo.cnds.vencidas > 0
              ? "metric metric--rose"
              : resumo.cnds.vencendo_30d > 0
              ? "metric metric--amber"
              : "metric metric--emerald"
          }
        >
          <span>CNDs vencendo 30d</span>
          <strong>{resumo.cnds.vencendo_30d}</strong>
          <p>
            {resumo.cnds.vencidas > 0
              ? `${resumo.cnds.vencidas} já vencidas · `
              : ""}
            <Link href="/prevencao" className="row-link">prevenção</Link>
          </p>
        </article>
        <article
          className={
            resumo.ecac.alta_nao_lidas > 0
              ? "metric metric--rose"
              : resumo.ecac.nao_lidas > 0
              ? "metric metric--amber"
              : "metric metric--emerald"
          }
        >
          <span>eCAC alta relevância</span>
          <strong>{resumo.ecac.alta_nao_lidas}</strong>
          <p>
            {resumo.ecac.nao_lidas > 0
              ? `${resumo.ecac.nao_lidas} não lidas total`
              : "tudo lido"}
          </p>
        </article>
        <article
          className={
            resumo.certificados.vencidos > 0
              ? "metric metric--rose"
              : resumo.certificados.vencendo_60d > 0
              ? "metric metric--amber"
              : resumo.empresas.sem_certificado_a1 > 0
              ? "metric metric--amber"
              : "metric metric--emerald"
          }
        >
          <span>Certificados A1</span>
          <strong>
            {resumo.certificados.vencendo_60d > 0
              ? `${resumo.certificados.vencendo_60d}`
              : resumo.empresas.sem_certificado_a1 > 0
              ? `−${resumo.empresas.sem_certificado_a1}`
              : "✓"}
          </strong>
          <p>
            {resumo.certificados.vencidos > 0
              ? `${resumo.certificados.vencidos} vencidos`
              : resumo.certificados.vencendo_60d > 0
              ? "vencendo em 60 dias"
              : resumo.empresas.sem_certificado_a1 > 0
              ? `${resumo.empresas.sem_certificado_a1} empresa(s) sem cert`
              : "todos válidos"}
          </p>
        </article>
        <article
          className={
            resumo.empresas.sem_focus_token > 0
              ? "metric metric--amber"
              : "metric metric--emerald"
          }
        >
          <span>Focus NFe</span>
          <strong>
            {resumo.empresas.ativas - resumo.empresas.sem_focus_token}/{resumo.empresas.ativas}
          </strong>
          <p>
            {resumo.empresas.sem_focus_token > 0
              ? `${resumo.empresas.sem_focus_token} sem token`
              : "todas integradas"}
          </p>
        </article>
      </section>

      {/* Linha 3 — Fiscal Serpro/Infosimples (DAS / PARCSN / PGFN / DCTFWeb / Robô).
          Só renderiza se backend devolveu os campos novos (proteção contra
          backend antigo sem /dashboard/resumo estendido). */}
      {resumo.das_simples && resumo.parcsn && resumo.dctfweb && resumo.robo_sefaz ? (
        <section className="grid">
          <article
            className={
              resumo.das_simples.atrasadas_qtd > 0
                ? "metric metric--rose"
                : resumo.das_simples.em_aberto_30d > 0
                ? "metric metric--amber"
                : "metric metric--emerald"
            }
          >
            <span>DAS Simples</span>
            <strong>{resumo.das_simples.atrasadas_qtd}</strong>
            <p>
              {resumo.das_simples.atrasadas_qtd > 0
                ? <>atrasadas · {formatBrl(resumo.das_simples.atrasadas_valor)} · <Link href="/das" className="row-link">ver</Link></>
                : resumo.das_simples.em_aberto_30d > 0
                ? <>{resumo.das_simples.em_aberto_30d} vencem em 30d · <Link href="/das" className="row-link">ver</Link></>
                : <>tudo em dia · <Link href="/das" className="row-link">ver</Link></>}
            </p>
          </article>
          <article className="metric metric--cyan">
            <span>PARCSN (Simples)</span>
            <strong>{resumo.parcsn.ativos}</strong>
            <p>
              {resumo.parcsn.ativos > 0
                ? <>{resumo.parcsn.parcelas_restantes_total} parcelas restantes · <Link href="/parcelamentos-simples" className="row-link">ver</Link></>
                : <>nenhum ativo · <Link href="/parcelamentos-simples" className="row-link">ver</Link></>}
            </p>
          </article>
          <article
            className={
              (resumo.pgfn?.ativos ?? 0) > 0
                ? "metric metric--violet"
                : "metric metric--cyan"
            }
          >
            <span>PGFN (Dívida Ativa)</span>
            <strong>{resumo.pgfn?.ativos ?? 0}</strong>
            <p>
              {(resumo.pgfn?.ativos ?? 0) > 0 && resumo.pgfn ? (
                <>
                  {formatBrl(resumo.pgfn.valor_total - resumo.pgfn.valor_pago)} a pagar ·{" "}
                  <Link href="/parcelamentos-pgfn" className="row-link">ver</Link>
                </>
              ) : (
                <>nenhum ativo · <Link href="/parcelamentos-pgfn" className="row-link">ver</Link></>
              )}
            </p>
          </article>
          {resumo.fgts ? (
            <article
              className={
                resumo.fgts.vencidas_qtd > 0
                  ? "metric metric--rose"
                  : resumo.fgts.vencendo_30d_qtd > 0 || resumo.fgts.empresas_sem_guia_mes > 0
                  ? "metric metric--amber"
                  : resumo.fgts.pendentes_qtd > 0
                  ? "metric metric--cyan"
                  : "metric metric--emerald"
              }
            >
              <span>FGTS Digital</span>
              <strong>{resumo.fgts.pendentes_qtd}</strong>
              <p>
                {resumo.fgts.vencidas_qtd > 0 ? (
                  <>
                    {resumo.fgts.vencidas_qtd} vencida(s) · {formatBrl(resumo.fgts.valor_a_pagar)} ·{" "}
                    <Link href="/fgts" className="row-link">ver</Link>
                  </>
                ) : resumo.fgts.vencendo_30d_qtd > 0 ? (
                  <>
                    {resumo.fgts.vencendo_30d_qtd} vencem em 30d · {formatBrl(resumo.fgts.valor_a_pagar)} ·{" "}
                    <Link href="/fgts" className="row-link">ver</Link>
                  </>
                ) : resumo.fgts.empresas_sem_guia_mes > 0 ? (
                  <>
                    {resumo.fgts.empresas_sem_guia_mes} sem guia do mês ·{" "}
                    <Link href="/fgts" className="row-link">emitir</Link>
                  </>
                ) : resumo.fgts.pendentes_qtd > 0 ? (
                  <>
                    {formatBrl(resumo.fgts.valor_a_pagar)} a pagar ·{" "}
                    <Link href="/fgts" className="row-link">ver</Link>
                  </>
                ) : (
                  <>tudo em dia · <Link href="/fgts" className="row-link">ver</Link></>
                )}
              </p>
            </article>
          ) : null}
          <article
            className={
              resumo.dctfweb.empresas_pendentes > 0
                ? "metric metric--amber"
                : "metric metric--emerald"
            }
          >
            <span>DCTFWeb mês</span>
            <strong>{resumo.dctfweb.emitidas_mes}</strong>
            <p>
              {resumo.dctfweb.empresas_pendentes > 0
                ? <>{resumo.dctfweb.empresas_pendentes} empresa(s) sem guia · <Link href="/dctfweb" className="row-link">ver</Link></>
                : <>todas emitidas · <Link href="/dctfweb" className="row-link">ver</Link></>}
            </p>
          </article>
          <article
            className={
              resumo.robo_sefaz.em_andamento > 0
                ? "metric metric--cyan"
                : resumo.robo_sefaz.ultima_execucao_status === "erro"
                ? "metric metric--rose"
                : resumo.robo_sefaz.ultima_execucao_status === "concluido"
                ? "metric metric--emerald"
                : "metric metric--cyan"
            }
          >
            <span>Robô SEFAZ-GO</span>
            <strong>
              {resumo.robo_sefaz.em_andamento > 0
                ? "⏳"
                : resumo.robo_sefaz.ultima_execucao_persistidos || "—"}
            </strong>
            <p>
              {resumo.robo_sefaz.em_andamento > 0
                ? <>{resumo.robo_sefaz.em_andamento} em andamento · <Link href="/robo-sefaz" className="row-link">ver</Link></>
                : resumo.robo_sefaz.ultima_execucao_iniciada_em
                ? <>última {formatDate(resumo.robo_sefaz.ultima_execucao_iniciada_em)} · <Link href="/robo-sefaz" className="row-link">ver</Link></>
                : <>nunca executado · <Link href="/robo-sefaz" className="row-link">rodar</Link></>}
            </p>
          </article>
        </section>
      ) : null}

      {/* Calendário + alertas legados */}
      <section
        style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16 }}
        className="dash-split"
      >
        <CalendarioFiscal />
        <AlertasCard />
      </section>

      <ApuracaoDashboardCard />

      {/* Visão consolidada por empresa */}
      {linhasEmpresa && linhasEmpresa.length > 0 ? (
        <DataTable
          title={`Visão por empresa (${linhasEmpresa.length} ativas)`}
          subtitle="Status fiscal consolidado — NFes do mês, DAS atrasadas, parcelamentos, DCTFWeb, robô."
          headers={[
            "Empresa",
            "UF",
            "NFes mês",
            "DAS atrasadas",
            "PARCSN",
            "PGFN",
            "FGTS",
            "DCTFWeb mês",
            "Cert A1",
            "Último robô",
          ]}
          rows={linhasEmpresa.map((e) => [
            <Link key={`emp-${e.empresa_id}`} href={`/empresas/${e.empresa_id}`} className="row-link">
              {e.razao_social}
            </Link>,
            e.uf || "—",
            e.nfes_mes,
            e.das_atrasadas_qtd > 0 ? (
              <span key={`das-${e.empresa_id}`} className="pill pill-err">
                {e.das_atrasadas_qtd} · {formatBrl(e.das_atrasadas_valor)}
              </span>
            ) : (
              <span key={`das-${e.empresa_id}`} className="pill pill-ok">—</span>
            ),
            e.parcsn_ativos > 0 ? (
              <span key={`p-${e.empresa_id}`} className="pill pill-info">
                {e.parcsn_ativos}
              </span>
            ) : (
              <span key={`p-${e.empresa_id}`} className="muted">—</span>
            ),
            e.pgfn_ativos > 0 ? (
              <span key={`pgfn-${e.empresa_id}`} className="pill pill-warn">
                {e.pgfn_ativos}
              </span>
            ) : (
              <span key={`pgfn-${e.empresa_id}`} className="muted">—</span>
            ),
            // FGTS: pendentes em vermelho/amarelo, mês emitido = ✓, sem nada = pendente
            e.fgts_pendentes > 0 ? (
              <span key={`fgts-${e.empresa_id}`} className="pill pill-err">
                {e.fgts_pendentes} a pagar
              </span>
            ) : e.fgts_mes_emitida ? (
              <span key={`fgts-${e.empresa_id}`} className="pill pill-ok">✓ mês</span>
            ) : (
              <span key={`fgts-${e.empresa_id}`} className="pill pill-warn">pendente</span>
            ),
            e.dctfweb_mes_emitida ? (
              <span key={`d-${e.empresa_id}`} className="pill pill-ok">✓</span>
            ) : (
              <span key={`d-${e.empresa_id}`} className="pill pill-warn">pendente</span>
            ),
            e.cert_a1_status === "ok" ? (
              <span key={`c-${e.empresa_id}`} className="pill pill-ok">válido</span>
            ) : e.cert_a1_status === "vencendo" ? (
              <span key={`c-${e.empresa_id}`} className="pill pill-warn">
                vence {formatDate(e.cert_a1_validade)}
              </span>
            ) : e.cert_a1_status === "vencido" ? (
              <span key={`c-${e.empresa_id}`} className="pill pill-err">vencido</span>
            ) : (
              <span key={`c-${e.empresa_id}`} className="pill pill-warn">ausente</span>
            ),
            e.ultima_execucao_robo ? (
              <span key={`r-${e.empresa_id}`} className="muted">
                {formatDate(e.ultima_execucao_robo.iniciado_em)} ·{" "}
                {e.ultima_execucao_robo.status === "concluido" ? (
                  <span className="pill pill-ok">{e.ultima_execucao_robo.persistidos}</span>
                ) : e.ultima_execucao_robo.status === "erro" ? (
                  <span className="pill pill-err">erro</span>
                ) : (
                  <span className="pill pill-info">{e.ultima_execucao_robo.status}</span>
                )}
              </span>
            ) : (
              <span key={`r-${e.empresa_id}`} className="muted">—</span>
            ),
          ])}
        />
      ) : null}

      {/* Top fornecedores do mês */}
      {fornecedoresRows.length > 0 ? (
        <DataTable
          title={`Top fornecedores do mês (${resumo.mes})`}
          subtitle={`${resumo.top_fornecedores.length} fornecedor(es) — ordenado por valor.`}
          headers={["#", "Razão social", "CNPJ", "NFes", "Valor"]}
          rows={fornecedoresRows}
        />
      ) : null}

      {/* Atalhos pros módulos */}
      <header className="page-header">
        <div>
          <h3>Módulos</h3>
          <p className="muted">Acesso rápido aos módulos do escritório.</p>
        </div>
      </header>

      <section className="card-grid">
        <Link href="/empresas" className="card-link card-link--emerald">
          <h4>Empresas</h4>
          <p>Cadastro, certificados A1, integração Focus.</p>
          <span className="card-link-stat">{resumo.empresas.total}</span>
        </Link>
        <Link href="/documentos" className="card-link card-link--cyan">
          <h4>Documentos</h4>
          <p>NF-e, CT-e, NFSe baixados via DF-e.</p>
          <span className="card-link-stat">{resumo.documentos_mes.geral_acumulado}</span>
        </Link>
        <Link href="/apuracoes" className="card-link card-link--indigo">
          <h4>Apurações</h4>
          <p>PGDAS-D Simples, transmissão SEFAZ + DAS PDF.</p>
          <span className="card-link-stat">
            {resumo.manifestacao.manifestadas > 0
              ? "PGDAS-D"
              : "—"}
          </span>
        </Link>
        <Link href="/prevencao" className="card-link card-link--violet">
          <h4>Prevenção</h4>
          <p>CND, eCAC, SITFIS, DTE, procurações.</p>
          <span className="card-link-stat">
            {resumo.cnds.vencendo_30d + resumo.cnds.vencidas > 0
              ? `${resumo.cnds.vencendo_30d + resumo.cnds.vencidas}!`
              : "✓"}
          </span>
        </Link>
        <Link href="/relatorios" className="card-link card-link--amber">
          <h4>Relatórios</h4>
          <p>Excel consolidado por empresa e período.</p>
        </Link>
      </section>

      {/* Últimos documentos */}
      {docsRows.length > 0 ? (
        <DataTable
          title="Últimos documentos baixados"
          subtitle="8 mais recentes (canceladas ocultas)."
          headers={["Emitente", "Tipo", "Número", "Data", "Valor", "Status"]}
          rows={docsRows}
        />
      ) : (
        <section className="panel">
          <p className="muted">
            Nenhum documento baixado ainda. Cadastre uma empresa, importe o token
            Focus e execute o robô.
          </p>
        </section>
      )}
    </>
  );
}
