"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import {
  PortalBloqueio,
  adicionarBloqueio,
  listarBloqueios,
  removerBloqueio,
} from "../lib/portal-bloqueios";

function fmtCnpj(c: string): string {
  const d = (c || "").replace(/\D/g, "");
  if (d.length !== 14) return c;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

/** Card (tela da empresa) pra o escritório ESCONDER notas de CNPJs específicos
 * no portal do cliente. Vale pra TODOS os logins da empresa; o escritório
 * continua vendo tudo. Bloqueio aplicado no backend em todos os caminhos. */
export function PortalBloqueioCard({ empresaId }: { empresaId: number }) {
  const [itens, setItens] = useState<PortalBloqueio[] | null>(null);
  const [cnpj, setCnpj] = useState("");
  const [rotulo, setRotulo] = useState("");
  const [reciproco, setReciproco] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setItens(await listarBloqueios(empresaId));
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar a lista.");
    }
  }, [empresaId]);

  useEffect(() => { carregar(); }, [carregar]);

  async function adicionar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setAviso(null);
    setBusy(true);
    try {
      const r = await adicionarBloqueio(empresaId, cnpj, rotulo.trim() || undefined, reciproco);
      setCnpj("");
      setRotulo("");
      if (r.reciproco_criado_para) {
        setAviso(`Ocultado também no portal de ${r.reciproco_criado_para} (nos dois sentidos).`);
      } else if (reciproco) {
        setAviso("Bloqueado aqui. (O recíproco só vale se o CNPJ for uma empresa cadastrada com portal.)");
      }
      await carregar();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao adicionar o CNPJ.");
    } finally {
      setBusy(false);
    }
  }

  async function remover(id: number) {
    setBusy(true);
    setErro(null);
    try {
      await removerBloqueio(id);
      await carregar();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao remover.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>🚫 Notas ocultas no portal do cliente</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Esconde do <strong>portal do cliente</strong> qualquer nota em que o CNPJ apareça
        (como emitente ou destinatário). Vale para <strong>todos os logins</strong> desta
        empresa. Aqui no escritório você continua vendo tudo — o filtro é só do portal.
      </p>

      <form
        onSubmit={adicionar}
        className="form-grid"
        style={{ gridTemplateColumns: "1.5fr 1fr auto", gap: 10, alignItems: "end" }}
      >
        <label>
          <span>CNPJ a ocultar</span>
          <input
            value={cnpj}
            onChange={(e) => setCnpj(e.target.value)}
            placeholder="00.000.000/0000-00"
            inputMode="numeric"
            required
          />
        </label>
        <label>
          <span>Apelido (opcional)</span>
          <input value={rotulo} onChange={(e) => setRotulo(e.target.value)} placeholder="Ex.: RCM" />
        </label>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "..." : "Adicionar"}
        </button>
      </form>

      <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: "0.86rem", cursor: "pointer" }}>
        <input type="checkbox" checked={reciproco} onChange={(e) => setReciproco(e.target.checked)} style={{ width: "auto" }} />
        <span>Bloquear nos <strong>dois sentidos</strong> — se o CNPJ for uma empresa nossa, esconde também no portal dela as notas desta empresa.</span>
      </label>

      {aviso ? <p className="toast toast-ok" style={{ marginTop: 10 }}>{aviso}</p> : null}
      {erro ? <p className="toast toast-error" style={{ marginTop: 10 }}>{erro}</p> : null}

      <div style={{ marginTop: 14 }}>
        {!itens ? (
          <p className="muted">Carregando…</p>
        ) : itens.length === 0 ? (
          <p className="muted">Nenhum CNPJ bloqueado — o cliente vê todas as notas.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
            {itens.map((b) => (
              <li
                key={b.id}
                style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
                  border: "1px solid var(--border)", borderRadius: 8,
                }}
              >
                <span style={{ fontWeight: 600 }}>{b.rotulo || "CNPJ"}</span>
                <code style={{ color: "var(--muted-strong)" }}>{fmtCnpj(b.cnpj)}</code>
                <button
                  type="button"
                  className="btn-ghost"
                  style={{ marginLeft: "auto", color: "#c0392b" }}
                  disabled={busy}
                  onClick={() => remover(b.id)}
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
