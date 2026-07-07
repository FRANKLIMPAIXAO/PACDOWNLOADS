"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth-context";
import {
  SegurancaDiag,
  UsuarioAdmin,
  ClienteAcesso,
  atualizarUsuario,
  clientesAcesso,
  criarUsuario,
  definirAtivoCliente,
  definirEmpresasCliente,
  listarEmpresasCliente,
  listarUsuarios,
  reenviarConvite,
  segurancaDiagnostico,
} from "../../lib/usuarios";
import { listarEmpresas, type Empresa } from "../../lib/empresas";

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
  const [seg, setSeg] = useState<SegurancaDiag | null>(null);
  const [acessos, setAcessos] = useState<ClienteAcesso[] | null>(null);
  const [gerenciar, setGerenciar] = useState<ClienteAcesso | null>(null);

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

  function recarregarAcessos() {
    clientesAcesso().then((r) => setAcessos(r.clientes)).catch(() => setAcessos([]));
  }

  async function toggleAtivoCliente(c: ClienteAcesso) {
    setError(null); setToast(null);
    let motivo: string | undefined;
    if (c.ativo) {
      // Inativando: pergunta o motivo (inadimplente / saiu do escritório...).
      const r = window.prompt(
        `Inativar o acesso de ${c.nome} ao portal?\nEle não conseguirá mais entrar (o token cai na hora).\n\nMotivo (opcional):`,
        "Inadimplente",
      );
      if (r === null) return; // cancelou
      motivo = r.trim() || undefined;
    } else {
      if (!window.confirm(`Reativar o acesso de ${c.nome} ao portal?`)) return;
    }
    try {
      await definirAtivoCliente(c.id, !c.ativo, motivo);
      setToast(c.ativo ? `Acesso de ${c.nome} inativado.` : `Acesso de ${c.nome} reativado.`);
      recarregarAcessos();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao atualizar o acesso do cliente.");
    }
  }

  useEffect(() => {
    recarregar();
    recarregarAcessos();
    segurancaDiagnostico().then(setSeg).catch(() => setSeg(null));
  }, []);

  function dataHora(iso: string | null): string {
    if (!iso) return "Nunca acessou";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

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

      {seg ? <SegurancaBanner seg={seg} /> : null}

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

      {/* Controle de acessos dos CLIENTES (portal) */}
      <section className="panel" style={{ marginTop: 16 }}>
        <h3>Acesso dos clientes ao portal</h3>
        <p className="muted" style={{ margin: "4px 0 12px", fontSize: 13 }}>
          Quem está acessando o portal e com que frequência. Um mesmo e-mail pode acessar
          várias empresas — use <strong>Empresas</strong> pra liberar as empresas de cada cliente.
        </p>
        {acessos === null ? (
          <p className="muted">Carregando...</p>
        ) : acessos.length === 0 ? (
          <p className="muted">Nenhum acesso de cliente cadastrado ainda.</p>
        ) : (
          <table className="data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Cliente</th><th>Empresas</th><th>Último acesso</th><th>Acessos</th><th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {acessos.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.nome}{!c.ativo ? <span className="pill pill-warn" style={{ marginLeft: 6 }}>inativo</span> : null}
                    <div className="muted" style={{ fontSize: 12 }}>{c.email}</div>
                    {!c.ativo && c.motivo_inativacao ? (
                      <div style={{ fontSize: 11, color: "rgb(239,68,68)" }}>🚫 {c.motivo_inativacao}</div>
                    ) : null}
                  </td>
                  <td style={{ display: "flex", flexWrap: "wrap", gap: 4, maxWidth: 320 }}>
                    {c.empresas.map((e) => (
                      <span key={e.id} className="pill pill-violet" style={{ fontSize: 11 }}>{e.razao_social || `#${e.id}`}</span>
                    ))}
                  </td>
                  <td style={{ color: c.ultimo_acesso ? undefined : "rgb(245,158,11)" }}>{dataHora(c.ultimo_acesso)}</td>
                  <td>{c.total_acessos}</td>
                  <td style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    <button type="button" className="btn-ghost" onClick={() => setGerenciar(c)}>🏢 Empresas</button>
                    <button
                      type="button"
                      className="btn-ghost"
                      style={{ color: c.ativo ? "rgb(239,68,68)" : "rgb(16,185,129)" }}
                      onClick={() => toggleAtivoCliente(c)}
                      title={c.ativo ? "Cortar o acesso deste cliente ao portal" : "Liberar o acesso deste cliente ao portal"}
                    >
                      {c.ativo ? "🚫 Inativar" : "✅ Ativar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {gerenciar ? (
        <GerenciarEmpresasModal
          cliente={gerenciar}
          onClose={() => setGerenciar(null)}
          onSaved={() => { setGerenciar(null); recarregarAcessos(); setToast("Empresas do cliente atualizadas."); }}
        />
      ) : null}
    </>
  );
}

function GerenciarEmpresasModal({
  cliente, onClose, onSaved,
}: { cliente: ClienteAcesso; onClose: () => void; onSaved: () => void }) {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [primariaId, setPrimariaId] = useState<number | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [filtro, setFiltro] = useState("");

  useEffect(() => {
    Promise.all([listarEmpresas(), listarEmpresasCliente(cliente.id)])
      .then(([todas, atual]) => {
        setEmpresas(todas);
        setPrimariaId(atual.primaria_id);
        // marca as ADICIONAIS (a primária fica fixa, fora do conjunto editável)
        setSel(new Set(atual.empresas.filter((e) => !e.primaria).map((e) => e.id)));
      })
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Falha ao carregar empresas."));
  }, [cliente.id]);

  function toggle(id: number) {
    setSel((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  async function salvar() {
    setBusy(true); setErro(null);
    try {
      await definirEmpresasCliente(cliente.id, Array.from(sel));
      onSaved();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao salvar.");
    } finally { setBusy(false); }
  }

  const lista = (empresas || [])
    .filter((e) => e.id !== primariaId)
    .filter((e) => !filtro || (e.razao_social || "").toLowerCase().includes(filtro.toLowerCase()) || (e.cnpj || "").includes(filtro));

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <header className="modal-header">
          <h2>🏢 Empresas de {cliente.nome}</h2>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>✕</button>
        </header>
        <div className="modal-body" style={{ display: "grid", gap: 12 }}>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Marque TODAS as empresas que este e-mail (<strong>{cliente.email}</strong>) pode acessar no portal.
            A empresa principal já vem liberada e não sai.
          </p>
          {erro ? <p className="toast toast-error">{erro}</p> : null}
          {empresas === null ? (
            <p className="muted">Carregando empresas...</p>
          ) : (
            <>
              <input placeholder="Filtrar por razão social ou CNPJ..." value={filtro} onChange={(e) => setFiltro(e.target.value)} />
              <div style={{ maxHeight: 320, overflowY: "auto", display: "grid", gap: 4, border: "1px solid #e6e9f0", borderRadius: 8, padding: 8 }}>
                {primariaId ? (
                  <label style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 6px", opacity: 0.7 }}>
                    <input type="checkbox" checked disabled />
                    <span>{(empresas.find((e) => e.id === primariaId)?.razao_social) || `Empresa #${primariaId}`} <span className="pill pill-violet" style={{ fontSize: 10 }}>principal</span></span>
                  </label>
                ) : null}
                {lista.map((e) => (
                  <label key={e.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 6px", cursor: "pointer" }}>
                    <input type="checkbox" checked={sel.has(e.id)} onChange={() => toggle(e.id)} />
                    <span>{e.razao_social} <span className="muted" style={{ fontSize: 11 }}>{e.cnpj}</span></span>
                  </label>
                ))}
                {lista.length === 0 ? <p className="muted" style={{ margin: 6 }}>Nenhuma empresa encontrada.</p> : null}
              </div>
            </>
          )}
          <div className="form-actions" style={{ display: "flex", justifyContent: "space-between" }}>
            <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>{sel.size + 1} empresa(s) no total</span>
            <button type="button" className="btn-primary" onClick={salvar} disabled={busy || empresas === null}>
              {busy ? "Salvando..." : "Salvar empresas"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SegurancaBanner({ seg }: { seg: SegurancaDiag }) {
  const problemas: string[] = [];
  if (seg.secret_key_default_ou_fraco)
    problemas.push("SECRET_KEY fraco/default — assina os logins E cifra as senhas dos certificados. Troque no Easypanel JÁ (e re-cadastre as senhas dos certs depois, pois a chave muda).");
  if (seg.senha_admin_default)
    problemas.push("Senha do admin no default 'admin123' — troque agora.");
  if (seg.cors_wildcard)
    problemas.push("CORS liberado pra qualquer origem (*) — restrinja ao domínio.");
  if (seg.mock_ligado_em_producao)
    problemas.push("Algum provedor (Focus/Integra/SEFAZ/Infosimples) está em MOCK em produção.");

  const critico = seg.secret_key_default_ou_fraco || seg.senha_admin_default || seg.cors_wildcard;

  if (problemas.length === 0) {
    return (
      <section className="panel" style={{ border: "1px solid rgba(34,197,94,0.4)", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: "rgb(16,185,129)" }}>🔒 Segurança: config OK</h3>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
          SECRET_KEY forte, senha admin trocada, CORS restrito{seg.is_production ? "" : " (ambiente: " + seg.ambiente + ")"}.
          Certificados protegidos com a chave atual.
        </p>
      </section>
    );
  }

  return (
    <section
      className="panel"
      style={{
        border: critico ? "1px solid rgba(248,113,113,0.6)" : "1px solid rgba(245,158,11,0.5)",
        marginBottom: 16,
      }}
    >
      <h3 style={{ margin: 0, color: critico ? "rgb(248,113,113)" : "rgb(245,158,11)" }}>
        {critico ? "🔴 Segurança: AÇÃO NECESSÁRIA" : "⚠️ Segurança: revisar"}
      </h3>
      <p className="muted" style={{ margin: "6px 0 10px", fontSize: 13 }}>
        Config do servidor (ambiente: {seg.ambiente}). Corrija no env do Easypanel e rebuilde.
      </p>
      <ul style={{ display: "grid", gap: 6, listStyle: "none", padding: 0, margin: 0 }}>
        {problemas.map((p, i) => (
          <li key={i} className="toast toast-error" style={{ fontSize: 13 }}>{p}</li>
        ))}
      </ul>
    </section>
  );
}
