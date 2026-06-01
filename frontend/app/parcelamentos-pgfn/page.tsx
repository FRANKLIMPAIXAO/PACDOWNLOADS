"use client";

import { useEffect, useState } from "react";

import { DataTable } from "../../components/data-table";
import { ProtectedRoute } from "../../components/protected-route";
import { ApiError } from "../../lib/api";
import { Empresa, listarEmpresas } from "../../lib/empresas";
import {
  MODALIDADES_PGFN,
  ParcelamentoPgfn,
  ParcelamentoPgfnComEmpresa,
  PgfnPayload,
  atualizarPgfn,
  criarPgfn,
  deletarPgfn,
  formatarDataBR,
  formatarReal,
  listarParcelamentosPgfn,
  listarTodosPgfnAtivos,
  marcarBaixadoPgfn,
  situacaoPgfnPill,
} from "../../lib/parcelamentos-pgfn";

export default function ParcelamentosPgfnPage() {
  return (
    <ProtectedRoute>
      <Conteudo />
    </ProtectedRoute>
  );
}

type FormState = PgfnPayload & { _editingId?: number | null };

const FORM_EMPTY: FormState = {
  numero: "",
  modalidade: "Parcelamento Ordinário",
  data_pedido: null,
  situacao: "Ativo",
  valor_total: null,
  valor_total_pago: null,
  quantidade_parcelas: null,
  parcelas_pagas: null,
  _editingId: null,
};

function Conteudo() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [empresaId, setEmpresaId] = useState<number | "">("");
  const [parcs, setParcs] = useState<ParcelamentoPgfn[] | null>(null);
  const [ativos, setAtivos] = useState<ParcelamentoPgfnComEmpresa[] | null>(null);
  const [form, setForm] = useState<FormState>(FORM_EMPTY);
  const [busy, setBusy] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    carregar();
  }, []);

  async function carregar() {
    setBusy("carregar");
    try {
      const [e, a] = await Promise.all([listarEmpresas(), listarTodosPgfnAtivos()]);
      setEmpresas(e);
      setAtivos(a);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar");
    } finally {
      setBusy(null);
    }
  }

  async function recarregarLista(eid: number) {
    setParcs(await listarParcelamentosPgfn(eid));
    setAtivos(await listarTodosPgfnAtivos());
  }

  async function handleSelecionar(id: number) {
    setEmpresaId(id);
    setForm(FORM_EMPTY);
    if (id) {
      setBusy("listar");
      try {
        await recarregarLista(id);
      } catch (e) {
        setErro(e instanceof ApiError ? e.message : "Falha ao listar");
      } finally {
        setBusy(null);
      }
    } else {
      setParcs(null);
    }
  }

  async function handleSalvar() {
    if (empresaId === "") {
      setErro("Selecione uma empresa antes de salvar.");
      return;
    }
    if (!form.numero.trim()) {
      setErro("Número do parcelamento é obrigatório.");
      return;
    }
    setBusy("salvar");
    setErro(null);
    try {
      const payload: PgfnPayload = {
        numero: form.numero.trim(),
        modalidade: form.modalidade,
        data_pedido: form.data_pedido || null,
        situacao: form.situacao,
        valor_total: form.valor_total || null,
        valor_total_pago: form.valor_total_pago || null,
        quantidade_parcelas: form.quantidade_parcelas || null,
        parcelas_pagas: form.parcelas_pagas || null,
      };
      if (form._editingId) {
        await atualizarPgfn(form._editingId, payload);
        setToast(`Parcelamento #${form._editingId} atualizado.`);
      } else {
        const novo = await criarPgfn(empresaId as number, payload);
        setToast(`Parcelamento criado (id=${novo.id}).`);
      }
      setForm(FORM_EMPTY);
      await recarregarLista(empresaId as number);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao salvar");
    } finally {
      setBusy(null);
    }
  }

  function editarLinha(p: ParcelamentoPgfn) {
    setForm({
      numero: p.numero,
      modalidade: p.modalidade,
      data_pedido: p.data_pedido?.split("T")[0] ?? null,
      situacao: p.situacao ?? "Ativo",
      valor_total: p.valor_total,
      valor_total_pago: p.valor_total_pago,
      quantidade_parcelas: p.quantidade_parcelas,
      parcelas_pagas: p.parcelas_pagas,
      _editingId: p.id,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function deletar(p: ParcelamentoPgfn) {
    if (!confirm(`Deletar parcelamento ${p.numero}? Essa ação não pode ser desfeita.`)) {
      return;
    }
    setBusy(`del-${p.id}`);
    try {
      await deletarPgfn(p.id);
      await recarregarLista(empresaId as number);
      setToast(`Parcelamento ${p.numero} deletado.`);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao deletar");
    } finally {
      setBusy(null);
    }
  }

  async function baixar(p: ParcelamentoPgfn) {
    if (!confirm(`Marcar ${p.numero} como BAIXADO/PAGO? Sai dos ativos mas fica no histórico.`)) {
      return;
    }
    setBusy(`baixar-${p.id}`);
    try {
      await marcarBaixadoPgfn(p.id);
      await recarregarLista(empresaId as number);
      setToast(`Parcelamento ${p.numero} baixado.`);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao baixar");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Parcelamentos PGFN (Dívida Ativa)</h1>
          <p className="muted">
            Cadastro manual de parcelamentos PGFN — não há API automatizada disponível
            (sem produto Infosimples / sem endpoint Serpro). Copie os dados do extrato
            REGULARIZE do cliente e mantenha aqui pra controle + alertas.
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
          <h2>{form._editingId ? `Editar parcelamento #${form._editingId}` : "Novo parcelamento"}</h2>
        </header>
        <div style={{ padding: 16, display: "grid", gap: 12 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>Empresa *</span>
            <select
              value={empresaId}
              onChange={(e) => handleSelecionar(e.target.value === "" ? 0 : Number(e.target.value))}
              disabled={busy !== null || form._editingId != null}
            >
              <option value="">— Selecione —</option>
              {empresas?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.razao_social} ({e.cnpj})
                </option>
              ))}
            </select>
          </label>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Número *</span>
              <input
                type="text"
                value={form.numero}
                onChange={(e) => setForm({ ...form, numero: e.target.value })}
                placeholder="Ex: PGFN-2024-001"
                disabled={busy !== null}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Modalidade</span>
              <select
                value={form.modalidade}
                onChange={(e) => setForm({ ...form, modalidade: e.target.value })}
                disabled={busy !== null}
              >
                {MODALIDADES_PGFN.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Data do pedido</span>
              <input
                type="date"
                value={form.data_pedido || ""}
                onChange={(e) => setForm({ ...form, data_pedido: e.target.value || null })}
                disabled={busy !== null}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Situação</span>
              <select
                value={form.situacao}
                onChange={(e) => setForm({ ...form, situacao: e.target.value })}
                disabled={busy !== null}
              >
                <option value="Ativo">Ativo</option>
                <option value="Suspenso">Suspenso</option>
                <option value="Rescindido">Rescindido</option>
              </select>
            </label>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Valor total (R$)</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.valor_total ?? ""}
                onChange={(e) => setForm({ ...form, valor_total: e.target.value || null })}
                placeholder="85000.00"
                disabled={busy !== null}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Valor pago (R$)</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.valor_total_pago ?? ""}
                onChange={(e) => setForm({ ...form, valor_total_pago: e.target.value || null })}
                placeholder="15000.00"
                disabled={busy !== null}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Qtd parcelas</span>
              <input
                type="number"
                min="1"
                max="999"
                value={form.quantidade_parcelas ?? ""}
                onChange={(e) => setForm({
                  ...form,
                  quantidade_parcelas: e.target.value ? Number(e.target.value) : null,
                })}
                placeholder="60"
                disabled={busy !== null}
              />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="muted" style={{ fontSize: 12 }}>Parcelas pagas</span>
              <input
                type="number"
                min="0"
                max="999"
                value={form.parcelas_pagas ?? ""}
                onChange={(e) => setForm({
                  ...form,
                  parcelas_pagas: e.target.value ? Number(e.target.value) : null,
                })}
                placeholder="10"
                disabled={busy !== null}
              />
            </label>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSalvar}
              disabled={busy !== null || empresaId === ""}
            >
              {busy === "salvar" ? "Salvando..." : form._editingId ? "Atualizar" : "Criar parcelamento"}
            </button>
            {form._editingId ? (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setForm(FORM_EMPTY)}
                disabled={busy !== null}
              >
                Cancelar edição
              </button>
            ) : null}
          </div>
        </div>
      </section>

      {parcs && parcs.length > 0 ? (
        <DataTable
          title={`Parcelamentos da empresa (${parcs.length})`}
          headers={[
            "Nº", "Modalidade", "Pedido", "Situação", "Valor total", "Pago",
            "Parcelas", "Restantes", "% concluído", "Ações",
          ]}
          rows={parcs.map((p) => [
            p.numero,
            p.modalidade,
            formatarDataBR(p.data_pedido),
            <span key={`sit-${p.id}`} className={situacaoPgfnPill(p.situacao)}>
              {p.situacao ?? "—"}
            </span>,
            formatarReal(p.valor_total),
            formatarReal(p.valor_total_pago),
            String(p.quantidade_parcelas ?? "—"),
            String(p.parcelas_restantes ?? "—"),
            p.percentual_concluido !== null ? `${p.percentual_concluido}%` : "—",
            <div key={`act-${p.id}`} style={{ display: "flex", gap: 4 }}>
              <button
                className="btn-ghost"
                onClick={() => editarLinha(p)}
                disabled={busy !== null}
                title="Editar"
              >
                ✎
              </button>
              {p.situacao !== "nao_listado_mais" ? (
                <button
                  className="btn-ghost"
                  onClick={() => baixar(p)}
                  disabled={busy !== null}
                  title="Marcar como pago/baixado"
                >
                  ✓
                </button>
              ) : null}
              <button
                className="btn-ghost"
                onClick={() => deletar(p)}
                disabled={busy !== null}
                title="Deletar"
              >
                ✕
              </button>
            </div>,
          ])}
        />
      ) : empresaId !== "" && parcs && parcs.length === 0 ? (
        <section className="panel">
          <p className="muted">
            Nenhum parcelamento PGFN cadastrado pra essa empresa. Use o formulário
            acima pra adicionar (copie os dados do extrato REGULARIZE do cliente).
          </p>
        </section>
      ) : null}

      <DataTable
        title={`Dashboard global — PGFN ativos (${ativos?.length ?? 0})`}
        subtitle="Todos os parcelamentos PGFN em situação ativa no PAC."
        headers={[
          "Empresa", "CNPJ", "Nº", "Modalidade", "Situação", "Restantes", "% concluído",
        ]}
        rows={
          ativos?.map((p) => [
            p.empresa_razao_social ?? `#${p.empresa_id}`,
            p.empresa_cnpj ?? "—",
            p.numero,
            p.modalidade,
            <span key={`sit-d-${p.id}`} className={situacaoPgfnPill(p.situacao)}>
              {p.situacao ?? "—"}
            </span>,
            String(p.parcelas_restantes ?? "—"),
            p.percentual_concluido !== null ? `${p.percentual_concluido}%` : "—",
          ]) ?? []
        }
      />
    </main>
  );
}
