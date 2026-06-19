"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth-context";
import {
  UsuarioAdmin,
  atualizarUsuario,
  criarUsuario,
  listarUsuarios,
  reenviarConvite,
} from "../../lib/usuarios";

export default function UsuariosPage() {
  return (
    <ProtectedRoute>
      <UsuariosContent />
    </ProtectedRoute>
  );
}

function UsuariosContent() {
  const { user } = useAuth();
  const router = useRouter();
  const [usuarios, setUsuarios] = useState<UsuarioAdmin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Form de criação
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [criando, setCriando] = useState(false);

  // Acesso só pra admin
  useEffect(() => {
    if (user && !user.is_admin) {
      router.replace("/");
    }
  }, [user, router]);

  function recarregar() {
    listarUsuarios()
      .then(setUsuarios)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Falha ao carregar usuários."));
  }

  useEffect(() => {
    recarregar();
  }, []);

  async function handleCriar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setToast(null);
    if (password.length < 6) {
      setError("Senha precisa de ao menos 6 caracteres.");
      return;
    }
    setCriando(true);
    try {
      await criarUsuario({ nome, email, password, is_admin: isAdmin });
      setToast(`Usuário ${email} criado com sucesso.`);
      setNome("");
      setEmail("");
      setPassword("");
      setIsAdmin(false);
      recarregar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao criar usuário.");
    } finally {
      setCriando(false);
    }
  }

  async function toggleAtivo(u: UsuarioAdmin) {
    setError(null);
    try {
      await atualizarUsuario(u.id, { ativo: !u.ativo });
      recarregar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao atualizar.");
    }
  }

  async function toggleAdmin(u: UsuarioAdmin) {
    setError(null);
    try {
      await atualizarUsuario(u.id, { is_admin: !u.is_admin });
      recarregar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao atualizar.");
    }
  }

  async function reenviar(u: UsuarioAdmin) {
    setError(null);
    setToast(null);
    try {
      const r = await reenviarConvite(u.id);
      if (r.email_enviado) {
        setToast(`Convite reenviado por e-mail para ${u.email}.`);
      } else {
        setToast(`E-mail não saiu (${r.detalhe}). Copie o link abaixo e mande pro cliente.`);
        if (r.link) window.prompt("Link do convite (válido 7 dias) — copie e mande pro cliente:", r.link);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao reenviar convite.");
    }
  }

  async function resetarSenha(u: UsuarioAdmin) {
    const nova = prompt(`Nova senha para ${u.email} (mín 6 caracteres):`);
    if (!nova) return;
    if (nova.length < 6) {
      setError("Senha precisa de ao menos 6 caracteres.");
      return;
    }
    try {
      await atualizarUsuario(u.id, { password: nova });
      setToast(`Senha de ${u.email} redefinida.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao redefinir senha.");
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Usuários</h2>
          <p className="muted">
            Gerencie quem acessa o sistema. Operadores podem usar tudo (subir
            cert, rodar robô, ver dados) mas só admins gerenciam usuários e
            excluem empresas.
          </p>
        </div>
      </header>

      {toast ? <p className="toast toast-ok">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      {/* Form de criação */}
      <section className="panel" style={{ marginBottom: 16 }}>
        <h3>Criar novo usuário</h3>
        <form
          onSubmit={handleCriar}
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}
        >
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Nome completo</span>
            <input value={nome} onChange={(e) => setNome(e.target.value)} required />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>E-mail</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Senha (mín 6)</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, alignSelf: "end", paddingBottom: 8 }}>
            <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
            <span>É administrador (acesso total)</span>
          </label>
          <div style={{ gridColumn: "1 / -1", textAlign: "right" }}>
            <button type="submit" className="btn-primary" disabled={criando}>
              {criando ? "Criando..." : "+ Criar usuário"}
            </button>
          </div>
        </form>
      </section>

      {/* Lista de usuários */}
      <section className="panel">
        <h3>Usuários cadastrados</h3>
        {usuarios === null ? (
          <p className="muted">Carregando...</p>
        ) : (
          <table className="data-table" style={{ width: "100%", marginTop: 12 }}>
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Papel</th>
                <th>Status</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id}>
                  <td>{u.nome}{u.id === user?.id ? " (você)" : ""}</td>
                  <td>{u.email}</td>
                  <td>
                    {u.is_cliente ? (
                      <span className="pill pill-violet">Cliente</span>
                    ) : (
                      <span className={u.is_admin ? "pill pill-info" : "pill"}>
                        {u.is_admin ? "Admin" : "Operador"}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={u.ativo ? "pill pill-ok" : "pill pill-warn"}>
                      {u.ativo ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button type="button" className="btn-ghost" onClick={() => toggleAtivo(u)}>
                      {u.ativo ? "Desativar" : "Ativar"}
                    </button>
                    {u.is_cliente ? (
                      <button type="button" className="btn-ghost" onClick={() => reenviar(u)}>
                        ✉️ Reenviar convite
                      </button>
                    ) : (
                      <>
                        <button type="button" className="btn-ghost" onClick={() => toggleAdmin(u)}>
                          {u.is_admin ? "→ Operador" : "→ Admin"}
                        </button>
                        <button type="button" className="btn-ghost" onClick={() => resetarSenha(u)}>
                          Redefinir senha
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
