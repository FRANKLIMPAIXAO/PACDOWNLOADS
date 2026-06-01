"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";

function formatCidade(empresa: Empresa): string {
  if (empresa.municipio && empresa.uf) return `${empresa.municipio}/${empresa.uf}`;
  return empresa.municipio || empresa.uf || "—";
}

export default function EmpresasPage() {
  return (
    <ProtectedRoute>
      <EmpresasContent />
    </ProtectedRoute>
  );
}

function EmpresasContent() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarEmpresas()
      .then(setEmpresas)
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar empresas.");
      });
  }, []);

  const header = (
    <header className="page-header">
      <div>
        <h2>Empresas</h2>
        <p className="muted">
          Cadastro local + integracao Focus NFe (token + certificado A1) por empresa.
        </p>
      </div>
      <div className="page-actions">
        <Link href="/empresas/novo" className="btn-primary">
          + Nova empresa
        </Link>
      </div>
    </header>
  );

  if (error) {
    return (
      <section className="panel">
        {header}
        <p className="auth-error">{error}</p>
      </section>
    );
  }

  if (empresas === null) {
    return (
      <section className="panel">
        {header}
        <p className="muted">Carregando...</p>
      </section>
    );
  }

  if (empresas.length === 0) {
    return (
      <section className="panel">
        {header}
        <div className="empty-state">
          Nenhuma empresa cadastrada ainda. Clique em <strong>Nova empresa</strong> para comecar.
        </div>
      </section>
    );
  }

  const rows: ReactNode[][] = empresas.map((empresa) => [
    <Link key={empresa.id} href={`/empresas/${empresa.id}`} className="row-link">
      {empresa.razao_social}
    </Link>,
    empresa.cnpj,
    formatCidade(empresa),
    empresa.regime_tributario || "—",
    empresa.ativo ? (
      <span className="pill pill-ok">Ativa</span>
    ) : (
      <span className="pill pill-warn">Inativa</span>
    ),
    empresa.ultimo_nsu_distribuicao ? `NSU ${empresa.ultimo_nsu_distribuicao}` : "—",
  ]);

  return (
    <>
      {header}
      <DataTable
        title=""
        subtitle={`${empresas.length} empresa(s) cadastrada(s).`}
        headers={["Empresa", "CNPJ", "Cidade", "Regime", "Status", "Ultimo NSU"]}
        rows={rows}
      />
    </>
  );
}
