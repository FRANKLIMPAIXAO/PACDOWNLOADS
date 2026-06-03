"use client";

import Link from "next/link";
import { useState } from "react";

import { ProtectedRoute } from "../../../components/protected-route";
import { ApiError } from "../../../lib/api";
import {
  ImportXlsxResultado,
  importarXlsxJettax,
} from "../../../lib/empresas";

export default function ImportarPage() {
  return (
    <ProtectedRoute>
      <ImportarContent />
    </ProtectedRoute>
  );
}

function ImportarContent() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true); // default ON pra primeira execucao
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ImportXlsxResultado | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleImportar() {
    if (!arquivo) {
      setErro("Selecione um arquivo .xlsx.");
      return;
    }
    setBusy(true);
    setErro(null);
    setResultado(null);
    try {
      const r = await importarXlsxJettax(arquivo, dryRun);
      setResultado(r);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha na importação");
    } finally {
      setBusy(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.toLowerCase().endsWith(".xlsx")) {
      setArquivo(f);
      setResultado(null);
    } else {
      setErro("Apenas arquivos .xlsx são aceitos.");
    }
  }

  const errosLista = resultado?.detalhes.filter((d) => d.status === "erro") ?? [];
  const criadasLista = resultado?.detalhes.filter((d) => d.status === "criada") ?? [];
  const atualizadasLista = resultado?.detalhes.filter((d) => d.status === "atualizada") ?? [];

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Importar carteira (Jettax 360 XLSX)</h2>
          <p className="muted">
            Importa o XLSX exportado do Jettax. UPSERT por CNPJ — re-rodar
            atualiza dados sem duplicar. NÃO importa cert .pfx em si (só
            valida data de vencimento). Use o dry-run primeiro.
          </p>
        </div>
        <div className="page-actions">
          <Link href="/empresas" className="btn-ghost">
            ← Voltar para Empresas
          </Link>
        </div>
      </header>

      <section className="panel" style={{ display: "grid", gap: 16 }}>
        {/* Drag-drop area */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          style={{
            border: `2px dashed ${dragOver ? "rgb(59,130,246)" : "rgba(255,255,255,0.2)"}`,
            background: dragOver ? "rgba(59,130,246,0.1)" : "rgba(255,255,255,0.02)",
            borderRadius: 8,
            padding: 32,
            textAlign: "center",
            transition: "all 0.2s",
          }}
        >
          {arquivo ? (
            <div>
              <p style={{ fontSize: 16, marginBottom: 4 }}>📄 <strong>{arquivo.name}</strong></p>
              <p className="muted" style={{ fontSize: 13 }}>
                {(arquivo.size / 1024).toFixed(1)} KB
              </p>
              <button
                type="button"
                className="btn-ghost"
                style={{ marginTop: 8 }}
                onClick={() => { setArquivo(null); setResultado(null); }}
                disabled={busy}
              >
                Trocar arquivo
              </button>
            </div>
          ) : (
            <div>
              <p style={{ fontSize: 16, marginBottom: 8 }}>
                Arraste o XLSX aqui ou:
              </p>
              <label
                className="btn-primary"
                style={{ cursor: "pointer", display: "inline-block" }}
              >
                Selecionar arquivo .xlsx
                <input
                  type="file"
                  accept=".xlsx"
                  style={{ display: "none" }}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) { setArquivo(f); setResultado(null); setErro(null); }
                  }}
                />
              </label>
            </div>
          )}
        </div>

        {/* Toggle dry-run */}
        <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            disabled={busy}
          />
          <span>
            <strong>Dry-run</strong>{" "}
            <span className="muted">
              (simula sem salvar — recomendado pra primeira execução)
            </span>
          </span>
        </label>

        {erro ? <div className="toast toast-error">{erro}</div> : null}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            type="button"
            className="btn-primary"
            onClick={handleImportar}
            disabled={busy || !arquivo}
          >
            {busy
              ? "Importando..."
              : dryRun
              ? "▶ Simular (dry-run)"
              : "▶ Importar de verdade"}
          </button>
        </div>
      </section>

      {/* Resultado */}
      {resultado ? (
        <section className="panel" style={{ marginTop: 16 }}>
          <h3>
            {resultado.dry_run ? "📋 Preview (dry-run)" : "✅ Importação concluída"}
          </h3>
          <p className="muted">
            {resultado.dry_run
              ? "Nenhum dado foi salvo. Desmarque 'Dry-run' e clique de novo pra importar de verdade."
              : "Empresas criadas/atualizadas no banco. Próximo passo: subir certs A1 e auto-cadastrar Focus."}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: 12,
              marginTop: 12,
            }}
          >
            <Stat label="Linhas lidas" value={resultado.linhas_lidas} color="rgb(148,163,184)" />
            <Stat label="Criadas" value={resultado.criadas} color="rgb(34,197,94)" />
            <Stat label="Atualizadas" value={resultado.atualizadas} color="rgb(59,130,246)" />
            <Stat label="Erros" value={resultado.erros} color={resultado.erros > 0 ? "rgb(239,68,68)" : "rgb(148,163,184)"} />
          </div>

          {/* Erros (se houver) */}
          {errosLista.length > 0 ? (
            <details open style={{ marginTop: 16 }}>
              <summary style={{ cursor: "pointer", color: "rgb(239,68,68)" }}>
                <strong>{errosLista.length} erro(s)</strong> — clique pra ver
              </summary>
              <ul style={{ margin: 8, fontSize: 13 }}>
                {errosLista.map((d, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>
                    <code>{d.cnpj}</code> · {d.razao_social} →{" "}
                    <span style={{ color: "rgb(239,68,68)" }}>{d.mensagem}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {/* Lista de criadas */}
          {criadasLista.length > 0 ? (
            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", fontSize: 13 }}>
                {criadasLista.length} empresa(s) {resultado.dry_run ? "seriam" : "foram"} criadas
              </summary>
              <ul style={{ margin: 8, fontSize: 12, columns: 2 }}>
                {criadasLista.map((d, i) => (
                  <li key={i}>
                    <code>{d.cnpj}</code> · {d.razao_social}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {/* Lista de atualizadas */}
          {atualizadasLista.length > 0 ? (
            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", fontSize: 13 }}>
                {atualizadasLista.length} empresa(s) {resultado.dry_run ? "seriam" : "foram"} atualizadas
              </summary>
              <ul style={{ margin: 8, fontSize: 12, columns: 2 }}>
                {atualizadasLista.map((d, i) => (
                  <li key={i}>
                    <code>{d.cnpj}</code> · {d.razao_social}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {!resultado.dry_run ? (
            <div style={{ marginTop: 16, textAlign: "right" }}>
              <Link href="/empresas" className="btn-primary">
                Ver empresas ({resultado.criadas + resultado.atualizadas})
              </Link>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.05)",
        borderRadius: 8,
        padding: 12,
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 24, fontWeight: 600, color }}>{value}</div>
      <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{label}</div>
    </div>
  );
}
