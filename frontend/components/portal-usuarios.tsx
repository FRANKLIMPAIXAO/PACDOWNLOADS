"use client";

import { CSSProperties, FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import {
  PortalUsuario,
  portalAtualizarUsuario,
  portalCriarUsuario,
  portalListarUsuarios,
} from "../lib/portal";

const labelSt: CSSProperties = { display: "grid", gap: 4, fontSize: "0.8rem" };
const inpSt: CSSProperties = {
  padding: "9px 11px", borderRadius: 8, border: "1px solid #d8dee8", font: "inherit", fontSize: "0.95rem",
};

/** Área "Usuários" do PORTAL — só o gestor (usuário principal) vê. Cria e
 * gerencia os acessos da própria equipe. Tudo escopado à empresa no backend. */
export function PortalUsuarios() {
  const [itens, setItens] = useState<PortalUsuario[] | null>(null);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      setItens(await portalListarUsuarios());
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar a equipe.");
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  async function criar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    setOk(null);
    setBusy(true);
    try {
      const n = nome.trim();
      const em = email.trim();
      await portalCriarUsuario({ nome: n, email: em, senha });
      setOk(`Acesso criado! Passe para ${n} o e-mail ${em} e a senha provisória "${senha}". No 1º acesso ele define a própria senha.`);
      setNome(""); setEmail(""); setSenha("");
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao criar o acesso.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleAtivo(u: PortalUsuario) {
    setBusy(true); setErro(null); setOk(null);
    try {
      await portalAtualizarUsuario(u.id, { ativo: !u.ativo });
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao atualizar o acesso.");
    } finally {
      setBusy(false);
    }
  }

  async function resetarSenha(u: PortalUsuario) {
    const nova = window.prompt(`Nova senha provisória para ${u.nome} (mín. 6 caracteres):`);
    if (nova === null) return;
    if (nova.length < 6) { setErro("A senha precisa de ao menos 6 caracteres."); return; }
    setBusy(true); setErro(null); setOk(null);
    try {
      await portalAtualizarUsuario(u.id, { nova_senha: nova });
      setOk(`Senha de ${u.nome} redefinida. Passe a nova senha "${nova}" — ele troca no próximo acesso.`);
      await carregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao redefinir a senha.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pac-card">
      <h2 style={{ marginTop: 0 }}>Usuários da sua empresa</h2>
      <p style={{ color: "#6b7488", marginTop: 0 }}>
        Crie acessos para a sua equipe. Cada pessoa entra com o próprio e-mail e vê as notas e
        documentos desta empresa. Você controla quem tem acesso — ative, desative ou redefina a
        senha quando quiser.
      </p>

      <form
        onSubmit={criar}
        style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 10, alignItems: "end", marginBottom: 14 }}
      >
        <label style={labelSt}>Nome
          <input style={inpSt} value={nome} onChange={(e) => setNome(e.target.value)} required />
        </label>
        <label style={labelSt}>E-mail
          <input style={inpSt} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label style={labelSt}>Senha provisória
          <input style={inpSt} value={senha} onChange={(e) => setSenha(e.target.value)} minLength={6} required />
        </label>
        <button type="submit" className="pac-btn pac-btn-primary" disabled={busy}>
          {busy ? "..." : "Criar acesso"}
        </button>
      </form>

      {ok ? <p className="pac-toast pac-toast-ok">{ok}</p> : null}
      {erro ? <p className="pac-toast pac-toast-err">{erro}</p> : null}

      {!itens ? (
        <p>Carregando…</p>
      ) : (
        <table className="pac-table" style={{ width: "100%", marginTop: 8 }}>
          <thead>
            <tr>
              <th>Usuário</th>
              <th>Situação</th>
              <th style={{ textAlign: "right" }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {itens.map((u) => (
              <tr key={u.id}>
                <td>
                  <strong>{u.nome}</strong>
                  {u.sou_eu ? <span className="pac-tag" style={{ marginLeft: 6 }}>você</span> : null}
                  {u.principal ? <span className="pac-tag" style={{ marginLeft: 6 }}>principal</span> : null}
                  <div style={{ fontSize: "0.82rem", opacity: 0.7 }}>{u.email}</div>
                </td>
                <td>
                  {u.ativo
                    ? <span className="pac-badge">Ativo</span>
                    : <span className="pac-badge" style={{ opacity: 0.55 }}>Inativo</span>}
                  {u.senha_provisoria ? <span className="pac-tag" style={{ marginLeft: 6 }}>trocar senha</span> : null}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {u.sou_eu ? (
                    <span style={{ opacity: 0.5, fontSize: "0.82rem" }}>—</span>
                  ) : (
                    <>
                      <button type="button" className="pac-btn pac-btn-ghost" disabled={busy} onClick={() => resetarSenha(u)}>
                        Resetar senha
                      </button>{" "}
                      <button type="button" className="pac-btn pac-btn-ghost" disabled={busy} onClick={() => toggleAtivo(u)}>
                        {u.ativo ? "Desativar" : "Ativar"}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
