"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { CndCard } from "../../../components/cnd-card";
import { ConfigFiscalCard } from "../../../components/config-fiscal-card";
import { PrevencaoCard } from "../../../components/prevencao-card";
import { ProtectedRoute } from "../../../components/protected-route";
import { ApiError } from "../../../lib/api";
import {
  Apuracao,
  currentAnoMes,
  formatAnoMes,
  listarApuracoes,
  previousAnoMes,
  statusLabel,
  statusPillClass,
} from "../../../lib/apuracoes";
import { CaixaPostalResumo, resumoCaixaPostal } from "../../../lib/integra";
import {
  Empresa,
  EmpresaFocusPayload,
  EmpresaUpdatePayload,
  FocusStatus,
  RoboResultado,
  atualizarEmpresa,
  buscarCnpjPublico,
  cadastrarOuAtualizarFocus,
  deletarCertificado,
  executarRoboDistribuicao,
  autoCadastrarFocus,
  importarFocusToken,
  inativarEmpresa,
  obterEmpresa,
  renovarCertificadoFocus,
  statusFocus,
  uploadCertificado,
} from "../../../lib/empresas";

const REGIMES = ["Simples Nacional", "Lucro Presumido", "Lucro Real", "MEI"];
const UFS = [
  "AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT","PA","PB",
  "PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO",
];

function isoDate(daysAgo: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

function isoDateTimeStart(date: string): string {
  return `${date}T00:00:00`;
}

function isoDateTimeEnd(date: string): string {
  return `${date}T23:59:59`;
}

export default function DetalheEmpresaPage() {
  return (
    <ProtectedRoute>
      <DetalheEmpresaContent />
    </ProtectedRoute>
  );
}

function DetalheEmpresaContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const empresaId = Number(params.id);

  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const [focus, setFocus] = useState<FocusStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [emp, fst] = await Promise.all([
        obterEmpresa(empresaId),
        statusFocus(empresaId),
      ]);
      setEmpresa(emp);
      setFocus(fst);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao carregar empresa.");
    }
  }, [empresaId]);

  useEffect(() => {
    if (!Number.isFinite(empresaId)) return;
    reload();
  }, [empresaId, reload]);

  if (error) {
    return (
      <section className="panel">
        <p className="toast toast-error">{error}</p>
        <Link href="/empresas" className="btn-secondary" style={{ marginTop: 16 }}>
          Voltar
        </Link>
      </section>
    );
  }

  if (!empresa) {
    return (
      <section className="panel">
        <p className="muted">Carregando empresa...</p>
      </section>
    );
  }

  async function handleInativar() {
    if (!empresa) return;
    if (!confirm(`Inativar ${empresa.razao_social}?`)) return;
    try {
      await inativarEmpresa(empresa.id);
      router.replace("/empresas");
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="muted" style={{ margin: 0 }}>
            <Link href="/empresas" className="row-link">← Empresas</Link>
          </p>
          <h2>{empresa.razao_social}</h2>
          <p className="muted">
            CNPJ {empresa.cnpj} ·{" "}
            {empresa.ativo ? (
              <span className="pill pill-ok">Ativa</span>
            ) : (
              <span className="pill pill-warn">Inativa</span>
            )}
          </p>
        </div>
        <div className="page-actions">
          {empresa.ativo ? (
            <button type="button" className="btn-danger" onClick={handleInativar}>
              Inativar
            </button>
          ) : null}
        </div>
      </header>

      <DadosGeraisCard empresa={empresa} onSaved={reload} />
      <CertificadoCard empresa={empresa} onChanged={reload} />
      <ConfigFiscalCard empresa={empresa} onSaved={reload} />
      <FocusCard empresa={empresa} focus={focus} onChanged={reload} />
      <RoboCard empresa={empresa} hasToken={!!focus?.tem_token} onRun={reload} />
      <ApuracoesEmpresaCard empresa={empresa} />
      <CaixaPostalLinkCard empresaId={empresa.id} />
      <CndCard empresaId={empresa.id} />
      <PrevencaoCard empresaId={empresa.id} />
    </>
  );
}

// --- Dados gerais (visualizacao em secções + edição completa) ---

const SITUACOES = ["ATIVA", "BAIXADA", "SUSPENSA", "INAPTA", "NULA"];

function DadosGeraisCard({
  empresa,
  onSaved,
}: {
  empresa: Empresa;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);

  if (!editing) {
    return (
      <section className="panel info-card">
        <header className="page-header" style={{ alignItems: "center" }}>
          <h3>Dados cadastrais</h3>
          <div className="page-actions">
            <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>
              Editar
            </button>
          </div>
        </header>

        <p className="section-divider">Identificação</p>
        <dl className="kv-grid">
          <dt>Razão social</dt><dd>{empresa.razao_social}</dd>
          <dt>Nome fantasia</dt><dd>{empresa.nome_fantasia || "—"}</dd>
          <dt>CNPJ</dt><dd>{empresa.cnpj}</dd>
          <dt>Inscrição estadual</dt><dd>{empresa.inscricao_estadual || "—"}</dd>
          <dt>Inscrição municipal</dt><dd>{empresa.inscricao_municipal || "—"}</dd>
          <dt>Natureza jurídica</dt>
          <dd>
            {empresa.natureza_juridica_descricao || "—"}
            {empresa.natureza_juridica_codigo
              ? ` (${empresa.natureza_juridica_codigo})`
              : ""}
          </dd>
          <dt>Situação cadastral</dt>
          <dd>
            {empresa.situacao_cadastral === "ATIVA" ? (
              <span className="pill pill-ok">ATIVA</span>
            ) : empresa.situacao_cadastral ? (
              <span className="pill pill-warn">{empresa.situacao_cadastral}</span>
            ) : "—"}
          </dd>
          <dt>Data de abertura</dt><dd>{empresa.data_abertura || "—"}</dd>
        </dl>

        <p className="section-divider">Tributação</p>
        <dl className="kv-grid">
          <dt>Regime tributário</dt><dd>{empresa.regime_tributario || "—"}</dd>
          <dt>Tributação</dt><dd>{empresa.tributacao || "—"}</dd>
          <dt>Anexo Simples</dt><dd>{empresa.anexo_simples || "—"}</dd>
        </dl>

        <p className="section-divider">Endereço</p>
        <dl className="kv-grid">
          <dt>CEP</dt><dd>{empresa.cep || "—"}</dd>
          <dt>Logradouro</dt>
          <dd>
            {[empresa.logradouro_tipo, empresa.logradouro, empresa.numero]
              .filter(Boolean)
              .join(" ") || "—"}
            {empresa.complemento ? ` · ${empresa.complemento}` : ""}
          </dd>
          <dt>Bairro</dt><dd>{empresa.bairro || "—"}</dd>
          <dt>Município / UF</dt>
          <dd>
            {empresa.municipio || "—"}
            {empresa.uf ? ` / ${empresa.uf}` : ""}
          </dd>
        </dl>

        <p className="section-divider">Contato</p>
        <dl className="kv-grid">
          <dt>Telefone</dt><dd>{empresa.telefone || "—"}</dd>
          <dt>WhatsApp</dt><dd>{empresa.whatsapp || "—"}</dd>
          <dt>E-mail</dt><dd>{empresa.email_contato || "—"}</dd>
        </dl>

        <p className="section-divider">Sistema</p>
        <dl className="kv-grid">
          <dt>Data cadastro PAC</dt>
          <dd>{empresa.data_cadastro?.slice(0, 10) || "—"}</dd>
          <dt>Último NSU baixado</dt><dd>{empresa.ultimo_nsu_distribuicao || "—"}</dd>
        </dl>
      </section>
    );
  }

  return <DadosGeraisForm empresa={empresa} onDone={() => { setEditing(false); onSaved(); }} />;
}

function DadosGeraisForm({
  empresa,
  onDone,
}: {
  empresa: Empresa;
  onDone: () => void;
}) {
  // Identificação
  const [razaoSocial, setRazaoSocial] = useState(empresa.razao_social);
  const [nomeFantasia, setNomeFantasia] = useState(empresa.nome_fantasia ?? "");
  const [inscricaoEstadual, setInscricaoEstadual] = useState(empresa.inscricao_estadual ?? "");
  const [inscricaoMunicipal, setInscricaoMunicipal] = useState(empresa.inscricao_municipal ?? "");
  const [naturezaCod, setNaturezaCod] = useState(empresa.natureza_juridica_codigo ?? "");
  const [naturezaDesc, setNaturezaDesc] = useState(empresa.natureza_juridica_descricao ?? "");
  const [situacao, setSituacao] = useState(empresa.situacao_cadastral ?? "");
  const [dataAbertura, setDataAbertura] = useState(empresa.data_abertura ?? "");
  // Tributação
  const [regime, setRegime] = useState(empresa.regime_tributario ?? "");
  const [tributacao, setTributacao] = useState(empresa.tributacao ?? "");
  // Endereço
  const [cep, setCep] = useState(empresa.cep ?? "");
  const [logradouroTipo, setLogradouroTipo] = useState(empresa.logradouro_tipo ?? "");
  const [logradouro, setLogradouro] = useState(empresa.logradouro ?? "");
  const [numero, setNumero] = useState(empresa.numero ?? "");
  const [complemento, setComplemento] = useState(empresa.complemento ?? "");
  const [bairro, setBairro] = useState(empresa.bairro ?? "");
  const [municipio, setMunicipio] = useState(empresa.municipio ?? "");
  const [uf, setUf] = useState(empresa.uf ?? "");
  // Contato
  const [telefone, setTelefone] = useState(empresa.telefone ?? "");
  const [whatsapp, setWhatsapp] = useState(empresa.whatsapp ?? "");
  const [emailContato, setEmailContato] = useState(empresa.email_contato ?? "");

  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  async function handleRefreshFromCnpj() {
    setRefreshing(true);
    setError(null);
    setToast(null);
    try {
      const r = await buscarCnpjPublico(empresa.cnpj);
      // Atualiza apenas campos vazios — preserva edicoes manuais
      const so = <T,>(atual: T, novo: T | null | undefined, setter: (v: T) => void) => {
        if ((atual === "" || atual === null || atual === undefined) && novo) {
          setter(novo as T);
        }
      };
      so(razaoSocial, r.razao_social, setRazaoSocial);
      so(nomeFantasia, r.nome_fantasia, setNomeFantasia);
      so(naturezaCod, r.natureza_juridica_codigo, setNaturezaCod);
      so(naturezaDesc, r.natureza_juridica_descricao, setNaturezaDesc);
      so(dataAbertura, r.data_abertura, setDataAbertura);
      so(situacao, r.situacao_cadastral, setSituacao);
      so(regime, r.regime_tributario, setRegime);
      so(telefone, r.telefone, setTelefone);
      so(emailContato, r.email_contato, setEmailContato);
      so(cep, r.cep, setCep);
      so(logradouroTipo, r.logradouro_tipo, setLogradouroTipo);
      so(logradouro, r.logradouro, setLogradouro);
      so(numero, r.numero, setNumero);
      so(complemento, r.complemento, setComplemento);
      so(bairro, r.bairro, setBairro);
      so(municipio, r.municipio, setMunicipio);
      so(uf, r.uf, setUf);
      setToast(`Receita: ${r.razao_social} · ${r._raw.cnae_principal.descricao || ""}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao buscar CNPJ.");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    const payload: EmpresaUpdatePayload = {
      razao_social: razaoSocial.trim() || undefined,
      nome_fantasia: nomeFantasia.trim() || undefined,
      inscricao_estadual: inscricaoEstadual.trim() || undefined,
      inscricao_municipal: inscricaoMunicipal.trim() || undefined,
      natureza_juridica_codigo: naturezaCod.trim() || undefined,
      natureza_juridica_descricao: naturezaDesc.trim() || undefined,
      situacao_cadastral: situacao || undefined,
      data_abertura: dataAbertura || undefined,
      regime_tributario: regime || undefined,
      tributacao: tributacao.trim() || undefined,
      cep: cep.replace(/\D+/g, "") || undefined,
      logradouro_tipo: logradouroTipo.trim() || undefined,
      logradouro: logradouro.trim() || undefined,
      numero: numero.trim() || undefined,
      complemento: complemento.trim() || undefined,
      bairro: bairro.trim() || undefined,
      municipio: municipio.trim() || undefined,
      uf: uf || undefined,
      telefone: telefone.trim() || undefined,
      whatsapp: whatsapp.trim() || undefined,
      email_contato: emailContato.trim() || undefined,
    };
    try {
      await atualizarEmpresa(empresa.id, payload);
      onDone();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel form-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Editar dados cadastrais</h3>
        <div className="page-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleRefreshFromCnpj}
            disabled={refreshing}
            title="Busca dados publicos na BrasilAPI e preenche campos vazios"
          >
            {refreshing ? "..." : "🔄 Buscar Receita"}
          </button>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="form-stack">
        {toast ? <p className="toast">{toast}</p> : null}
        {error ? <p className="toast toast-error">{error}</p> : null}

        <p className="section-divider">Identificação</p>
        <div className="form-grid">
          <label style={{ gridColumn: "span 2" }}>
            <span>Razão social</span>
            <input value={razaoSocial} onChange={(e) => setRazaoSocial(e.target.value)} required />
          </label>
          <label>
            <span>Nome fantasia</span>
            <input value={nomeFantasia} onChange={(e) => setNomeFantasia(e.target.value)} />
          </label>
          <label>
            <span>Inscrição estadual</span>
            <input value={inscricaoEstadual} onChange={(e) => setInscricaoEstadual(e.target.value)} />
          </label>
          <label>
            <span>Inscrição municipal</span>
            <input value={inscricaoMunicipal} onChange={(e) => setInscricaoMunicipal(e.target.value)} />
          </label>
          <label>
            <span>Natureza jurídica (código)</span>
            <input value={naturezaCod} onChange={(e) => setNaturezaCod(e.target.value)} />
          </label>
          <label style={{ gridColumn: "span 2" }}>
            <span>Natureza jurídica (descrição)</span>
            <input value={naturezaDesc} onChange={(e) => setNaturezaDesc(e.target.value)} />
          </label>
          <label>
            <span>Situação cadastral</span>
            <select value={situacao} onChange={(e) => setSituacao(e.target.value)}>
              <option value="">Selecione</option>
              {SITUACOES.map((s) => (<option key={s} value={s}>{s}</option>))}
            </select>
          </label>
          <label>
            <span>Data de abertura</span>
            <input type="date" value={dataAbertura} onChange={(e) => setDataAbertura(e.target.value)} />
          </label>
        </div>

        <p className="section-divider">Tributação</p>
        <div className="form-grid">
          <label>
            <span>Regime tributário</span>
            <select value={regime} onChange={(e) => setRegime(e.target.value)}>
              <option value="">Selecione</option>
              {REGIMES.map((r) => (<option key={r} value={r}>{r}</option>))}
            </select>
          </label>
          <label>
            <span>Tributação</span>
            <input
              value={tributacao}
              onChange={(e) => setTributacao(e.target.value)}
              placeholder="ICMS Normal, Imune..."
            />
          </label>
        </div>

        <p className="section-divider">Endereço</p>
        <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr 2fr" }}>
          <label>
            <span>CEP</span>
            <input value={cep} onChange={(e) => setCep(e.target.value)} placeholder="00000-000" />
          </label>
          <label>
            <span>Tipo logradouro</span>
            <input value={logradouroTipo} onChange={(e) => setLogradouroTipo(e.target.value)} placeholder="Rua, Av..." />
          </label>
          <label>
            <span>Logradouro</span>
            <input value={logradouro} onChange={(e) => setLogradouro(e.target.value)} />
          </label>
        </div>
        <div className="form-grid" style={{ gridTemplateColumns: "1fr 2fr 2fr" }}>
          <label>
            <span>Número</span>
            <input value={numero} onChange={(e) => setNumero(e.target.value)} />
          </label>
          <label>
            <span>Complemento</span>
            <input value={complemento} onChange={(e) => setComplemento(e.target.value)} />
          </label>
          <label>
            <span>Bairro</span>
            <input value={bairro} onChange={(e) => setBairro(e.target.value)} />
          </label>
        </div>
        <div className="form-grid" style={{ gridTemplateColumns: "3fr 1fr" }}>
          <label>
            <span>Município</span>
            <input value={municipio} onChange={(e) => setMunicipio(e.target.value)} />
          </label>
          <label>
            <span>UF</span>
            <select value={uf} onChange={(e) => setUf(e.target.value)}>
              <option value="">--</option>
              {UFS.map((u) => (<option key={u} value={u}>{u}</option>))}
            </select>
          </label>
        </div>

        <p className="section-divider">Contato</p>
        <div className="form-grid">
          <label>
            <span>Telefone</span>
            <input value={telefone} onChange={(e) => setTelefone(e.target.value)} />
          </label>
          <label>
            <span>WhatsApp</span>
            <input value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
          </label>
          <label style={{ gridColumn: "span 2" }}>
            <span>E-mail de contato</span>
            <input type="email" value={emailContato} onChange={(e) => setEmailContato(e.target.value)} />
          </label>
        </div>

        <div className="form-actions">
          <button type="button" className="btn-secondary" onClick={onDone}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Salvando..." : "Salvar"}
          </button>
        </div>
      </form>
    </section>
  );
}

// --- Certificado A1 local (independente da Focus) ---

function CertificadoCard({
  empresa,
  onChanged,
}: {
  empresa: Empresa;
  onChanged: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [senha, setSenha] = useState("");
  const [permitirDif, setPermitirDif] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setToast(null);
    if (!arquivo) { setError("Selecione o arquivo .pfx."); return; }
    if (!senha) { setError("Informe a senha."); return; }
    setUploading(true);
    try {
      const info = await uploadCertificado(empresa.id, arquivo, senha, permitirDif);
      setToast(
        `Certificado salvo: ${info.subject.slice(0, 60)}... · vence ${info.validade_ate}`
      );
      setArquivo(null);
      setSenha("");
      setShowForm(false);
      onChanged();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao salvar certificado.");
    } finally {
      setUploading(false);
    }
  }

  async function handleRemover() {
    if (!confirm("Remover o certificado A1 desta empresa?")) return;
    setRemoving(true);
    setError(null);
    setToast(null);
    try {
      await deletarCertificado(empresa.id);
      onChanged();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao remover.");
    } finally {
      setRemoving(false);
    }
  }

  const vencendo = empresa.cert_a1_validade_ate
    ? Math.floor(
        (new Date(empresa.cert_a1_validade_ate).getTime() - Date.now()) /
          (1000 * 60 * 60 * 24),
      )
    : null;

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Certificado Digital A1</h3>
        <div className="page-actions">
          {empresa.tem_certificado_a1 ? (
            vencendo !== null && vencendo < 30 ? (
              <span className="pill pill-warn">Vence em {vencendo}d</span>
            ) : (
              <span className="pill pill-ok">Configurado</span>
            )
          ) : (
            <span className="pill pill-warn">Não configurado</span>
          )}
        </div>
      </header>

      {empresa.tem_certificado_a1 ? (
        <>
          <dl className="kv-grid">
            <dt>Subject</dt>
            <dd style={{ fontSize: "0.78rem", wordBreak: "break-all" }}>
              {empresa.cert_a1_subject || "—"}
            </dd>
            <dt>Validade até</dt>
            <dd>
              {empresa.cert_a1_validade_ate || "—"}
              {vencendo !== null
                ? vencendo < 0
                  ? ` · há ${Math.abs(vencendo)}d (VENCIDO)`
                  : ` · em ${vencendo}d`
                : ""}
            </dd>
          </dl>
          <div className="page-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowForm((v) => !v)}
            >
              {showForm ? "Cancelar" : "Substituir certificado"}
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={handleRemover}
              disabled={removing}
            >
              {removing ? "Removendo..." : "Remover"}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="muted">
            Faça upload do arquivo .pfx (e-CNPJ A1) da empresa.
            Validamos com a senha e o CNPJ do certificado bate com o da empresa.
          </p>
          <div className="page-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => setShowForm((v) => !v)}
            >
              {showForm ? "Cancelar" : "Subir certificado"}
            </button>
          </div>
        </>
      )}

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      {showForm ? (
        <form onSubmit={handleUpload} className="form-stack" style={{ marginTop: 12 }}>
          <div className="form-grid" style={{ gridTemplateColumns: "2fr 1fr" }}>
            <label>
              <span>Arquivo .pfx</span>
              <input
                type="file"
                accept=".pfx,.p12"
                onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                required
              />
              {arquivo ? (
                <small className="muted">
                  {arquivo.name} ({(arquivo.size / 1024).toFixed(1)} KB)
                </small>
              ) : null}
            </label>
            <label>
              <span>Senha</span>
              <input
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                autoComplete="new-password"
                required
              />
            </label>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox"
              checked={permitirDif}
              onChange={(e) => setPermitirDif(e.target.checked)}
            />
            <small className="muted">
              Permitir CNPJ diferente (matriz/filial intencional)
            </small>
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={uploading}>
              {uploading ? "Enviando..." : "Salvar certificado"}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}

// --- Integracao Focus NFe ---

type FocusMode = "view" | "import" | "cadastro" | "renovar";

function FocusCard({
  empresa,
  focus,
  onChanged,
}: {
  empresa: Empresa;
  focus: FocusStatus | null;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<FocusMode>("view");
  const [autoBusy, setAutoBusy] = useState(false);
  const [autoMsg, setAutoMsg] = useState<{
    ok: boolean;
    text: string;
  } | null>(null);

  // Empresa elegível pro auto-cadastro: tem cert A1 no PAC + não tem focus_token
  const podeAutoCadastrar = !!empresa.tem_certificado_a1 && !focus?.tem_token;

  async function handleAutoCadastrar() {
    const ok = confirm(
      `Auto-cadastrar ${empresa.razao_social} no Focus NFe?\n\n` +
      `Vai usar o cert A1 já salvo no PAC + dados cadastrais (CNPJ, endereço, ` +
      `IE/IM) pra cadastrar via POST /v2/empresas com o FOCUS_MASTER_TOKEN do ` +
      `escritório. O token retornado fica salvo automaticamente (cifrado).\n\n` +
      `Não precisa subir certificado nem preencher endereço — o sistema já tem.\n\n` +
      `Continuar?`,
    );
    if (!ok) return;
    setAutoBusy(true);
    setAutoMsg(null);
    try {
      const r = await autoCadastrarFocus(empresa.id);
      if (r.token_salvo) {
        setAutoMsg({
          ok: true,
          text: r.ja_tinha_token
            ? "Empresa já tinha token Focus salvo."
            : "✅ Empresa cadastrada na Focus + token salvo automaticamente.",
        });
        onChanged();
      } else {
        setAutoMsg({
          ok: false,
          text: r.mensagem || "Cadastro feito mas token não foi salvo.",
        });
      }
    } catch (err) {
      const msg = err instanceof ApiError
        ? err.message
        : err instanceof Error
        ? err.message
        : "Falha desconhecida no auto-cadastro.";
      setAutoMsg({ ok: false, text: msg });
    } finally {
      setAutoBusy(false);
    }
  }

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Integracao Focus NFe</h3>
        <div className="page-actions">
          {focus?.tem_token ? (
            <span className="pill pill-ok">Token configurado</span>
          ) : (
            <span className="pill pill-warn">Sem token</span>
          )}
        </div>
      </header>

      {focus?.empresa_focus ? (
        <dl className="kv-grid">
          <dt>Habilita NFe</dt>
          <dd>{focus.empresa_focus["habilita_nfe"] ? "sim" : "nao"}</dd>
          <dt>Habilita CTe</dt>
          <dd>{focus.empresa_focus["habilita_cte"] ? "sim" : "nao"}</dd>
          <dt>Habilita NFSe</dt>
          <dd>{focus.empresa_focus["habilita_nfse"] ? "sim" : "nao"}</dd>
          <dt>Cert. valido de</dt>
          <dd>{(focus.empresa_focus["certificado_valido_de"] as string) || "—"}</dd>
          <dt>Cert. valido ate</dt>
          <dd>{(focus.empresa_focus["certificado_valido_ate"] as string) || "—"}</dd>
        </dl>
      ) : (
        <p className="muted">
          {focus?.tem_token
            ? "Token presente, mas nao foi possivel consultar a Focus (verifique conectividade)."
            : "Esta empresa ainda nao tem integracao com a Focus NFe. Use uma das opcoes abaixo."}
        </p>
      )}

      {/* Botão DESTAQUE: auto-cadastro reusando cert + dados que já estão no PAC.
          Só aparece se faz sentido (tem cert + não tem token). */}
      {podeAutoCadastrar ? (
        <div
          style={{
            background: "rgba(16, 185, 129, 0.08)",
            border: "1px solid rgba(16, 185, 129, 0.25)",
            borderRadius: 8,
            padding: 12,
            marginTop: 12,
            marginBottom: 8,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div>
              <strong>🔗 Auto-cadastrar (recomendado)</strong>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
                Reusa o cert A1 + endereço + CNPJ que já estão no PAC. Sem
                redigitar nada.
              </p>
            </div>
            <button
              type="button"
              className="btn-primary"
              onClick={handleAutoCadastrar}
              disabled={autoBusy}
            >
              {autoBusy ? "Cadastrando..." : "▶ Auto-cadastrar agora"}
            </button>
          </div>
          {autoMsg ? (
            <div
              className={autoMsg.ok ? "toast toast-ok" : "toast toast-error"}
              style={{ marginTop: 10, fontSize: 13 }}
            >
              {autoMsg.text}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="page-actions">
        <button type="button" className="btn-secondary" onClick={() => setMode(mode === "import" ? "view" : "import")}>
          {mode === "import" ? "Cancelar import" : "Importar token Focus"}
        </button>
        <button type="button" className="btn-secondary" onClick={() => setMode(mode === "cadastro" ? "view" : "cadastro")}>
          {mode === "cadastro"
            ? "Cancelar cadastro"
            : focus?.tem_token
            ? "Atualizar empresa + cert"
            : "Cadastrar manualmente (subir cert novo)"}
        </button>
        {focus?.tem_token ? (
          <button type="button" className="btn-secondary" onClick={() => setMode(mode === "renovar" ? "view" : "renovar")}>
            {mode === "renovar" ? "Cancelar renovacao" : "Renovar so o certificado"}
          </button>
        ) : null}
      </div>

      {mode === "import" ? <ImportTokenForm empresa={empresa} onDone={() => { setMode("view"); onChanged(); }} /> : null}
      {mode === "cadastro" ? <CadastroFocusForm empresa={empresa} onDone={() => { setMode("view"); onChanged(); }} /> : null}
      {mode === "renovar" ? <RenovarCertForm empresa={empresa} onDone={() => { setMode("view"); onChanged(); }} /> : null}
    </section>
  );
}

function ImportTokenForm({ empresa, onDone }: { empresa: Empresa; onDone: () => void }) {
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (token.trim().length < 10) {
      setError("Token muito curto (minimo 10 caracteres).");
      return;
    }
    setSaving(true);
    try {
      await importarFocusToken(empresa.id, token.trim());
      onDone();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao importar token.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form-stack" style={{ marginTop: 12 }}>
      <p className="section-divider">Importar token gerado no painel Focus</p>
      <label>
        <span>Token (producao ou homologacao)</span>
        <input
          type="text"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="cole o token aqui"
          required
        />
      </label>
      {error ? <p className="toast toast-error">{error}</p> : null}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Salvando..." : "Salvar token"}
        </button>
      </div>
    </form>
  );
}

function CadastroFocusForm({ empresa, onDone }: { empresa: Empresa; onDone: () => void }) {
  const [logradouro, setLogradouro] = useState("");
  const [numero, setNumero] = useState("");
  const [bairro, setBairro] = useState("");
  const [cep, setCep] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [senha, setSenha] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!arquivo) {
      setError("Selecione o arquivo .pfx do certificado.");
      return;
    }
    if (!senha) {
      setError("Senha do certificado obrigatoria.");
      return;
    }
    if (!logradouro || !numero) {
      setError("Endereco (logradouro + numero) obrigatorio.");
      return;
    }
    const payload: EmpresaFocusPayload = {
      cnpj: empresa.cnpj,
      nome: empresa.razao_social,
      nome_fantasia: empresa.nome_fantasia ?? undefined,
      regime_tributario: empresa.regime_tributario ?? undefined,
      endereco: {
        logradouro,
        numero,
        bairro: bairro || undefined,
        cidade: empresa.municipio ?? undefined,
        uf: empresa.uf ?? undefined,
        cep: cep || undefined,
      },
    };
    setSaving(true);
    try {
      await cadastrarOuAtualizarFocus(empresa.id, payload, arquivo, senha);
      onDone();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao cadastrar empresa na Focus.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form-stack" style={{ marginTop: 12 }}>
      <p className="section-divider">Cadastrar / atualizar empresa na Focus NFe</p>
      <p className="muted" style={{ marginTop: 0 }}>
        Os dados gerais da empresa (CNPJ, razao social, cidade, UF) ja sao usados.
        Informe o endereco completo + arquivo de certificado A1 + senha.
      </p>
      <div className="form-grid">
        <label>
          <span>Logradouro</span>
          <input value={logradouro} onChange={(e) => setLogradouro(e.target.value)} required />
        </label>
        <label>
          <span>Numero</span>
          <input value={numero} onChange={(e) => setNumero(e.target.value)} required />
        </label>
        <label>
          <span>Bairro</span>
          <input value={bairro} onChange={(e) => setBairro(e.target.value)} />
        </label>
        <label>
          <span>CEP</span>
          <input value={cep} onChange={(e) => setCep(e.target.value)} />
        </label>
        <label>
          <span>Certificado A1 (.pfx ou .p12)</span>
          <input
            type="file"
            accept=".pfx,.p12"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            required
          />
        </label>
        <label>
          <span>Senha do certificado</span>
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
      </div>
      {error ? <p className="toast toast-error">{error}</p> : null}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Enviando..." : "Enviar para Focus"}
        </button>
      </div>
    </form>
  );
}

function RenovarCertForm({ empresa, onDone }: { empresa: Empresa; onDone: () => void }) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [senha, setSenha] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!arquivo) { setError("Selecione o arquivo .pfx."); return; }
    if (!senha) { setError("Senha obrigatoria."); return; }
    setSaving(true);
    try {
      await renovarCertificadoFocus(empresa.id, arquivo, senha);
      onDone();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao renovar certificado.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form-stack" style={{ marginTop: 12 }}>
      <p className="section-divider">Renovar somente o certificado A1</p>
      <div className="form-grid">
        <label>
          <span>Novo certificado .pfx</span>
          <input
            type="file"
            accept=".pfx,.p12"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            required
          />
        </label>
        <label>
          <span>Senha</span>
          <input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
      </div>
      {error ? <p className="toast toast-error">{error}</p> : null}
      <div className="form-actions">
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Enviando..." : "Renovar"}
        </button>
      </div>
    </form>
  );
}

// --- Robo de download ---

function RoboCard({
  empresa,
  hasToken,
  onRun,
}: {
  empresa: Empresa;
  hasToken: boolean;
  onRun: () => void;
}) {
  const [dataInicio, setDataInicio] = useState(isoDate(30));
  const [dataFim, setDataFim] = useState(isoDate(0));
  const [running, setRunning] = useState(false);
  const [resultado, setResultado] = useState<RoboResultado | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRun(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setResultado(null);
    setRunning(true);
    try {
      const res = await executarRoboDistribuicao(
        empresa.id,
        isoDateTimeStart(dataInicio),
        isoDateTimeEnd(dataFim),
      );
      setResultado(res);
      onRun();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao executar robo.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Robo de download (NFe recebidas)</h3>
        {hasToken ? (
          <span className="pill pill-ok">Pronto</span>
        ) : (
          <span className="pill pill-warn">Configure token primeiro</span>
        )}
      </header>

      <form onSubmit={handleRun} className="form-stack">
        <div className="form-grid">
          <label>
            <span>Data inicio</span>
            <input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} required />
          </label>
          <label>
            <span>Data fim</span>
            <input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} required />
          </label>
        </div>
        {error ? <p className="toast toast-error">{error}</p> : null}
        {resultado ? (
          <p className="toast">
            Resultado: processados {resultado.processados} · baixados {resultado.baixados} ·
            duplicados {resultado.duplicados} · erros {resultado.erros}
          </p>
        ) : null}
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={running || !hasToken}>
            {running ? "Executando..." : "Executar agora"}
          </button>
        </div>
      </form>
    </section>
  );
}


// --- Card de link rapido pra caixa postal eCAC ---

function CaixaPostalLinkCard({ empresaId }: { empresaId: number }) {
  const [resumo, setResumo] = useState<CaixaPostalResumo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let canceled = false;
    resumoCaixaPostal(empresaId)
      .then((r) => { if (!canceled) setResumo(r); })
      .catch((err) => {
        if (canceled) return;
        if (err instanceof ApiError) setError(err.message);
      });
    return () => { canceled = true; };
  }, [empresaId]);

  if (error) return null;

  const naoLidas = resumo?.nao_lidas ?? 0;
  const altaNaoLidas = resumo?.alta_relevancia_nao_lidas ?? 0;

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Caixa Postal eCAC</h3>
        <div className="page-actions">
          {altaNaoLidas > 0 ? (
            <span className="pill pill-err">
              {altaNaoLidas} alta NAO lida{altaNaoLidas === 1 ? "" : "s"}
            </span>
          ) : naoLidas > 0 ? (
            <span className="pill pill-warn">{naoLidas} nao lida{naoLidas === 1 ? "" : "s"}</span>
          ) : resumo ? (
            <span className="pill pill-ok">Tudo lido</span>
          ) : null}
        </div>
      </header>

      {resumo ? (
        <p className="muted" style={{ margin: 0, fontSize: "0.86rem" }}>
          {resumo.total} mensagem(s) sincronizadas da Receita Federal.{" "}
          {resumo.alta_relevancia > 0
            ? `${resumo.alta_relevancia} de alta relevancia.`
            : ""}
        </p>
      ) : (
        <p className="muted">Carregando resumo...</p>
      )}

      <div className="page-actions">
        <Link
          href={`/empresas/${empresaId}/caixa-postal`}
          className="btn-primary"
        >
          Abrir caixa postal
        </Link>
      </div>
    </section>
  );
}



// --- Card de apuracoes PGDAS-D da empresa ---

function ApuracoesEmpresaCard({ empresa }: { empresa: Empresa }) {
  const [apuracoes, setApuracoes] = useState<Apuracao[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let canceled = false;
    listarApuracoes({ empresaId: empresa.id })
      .then((arr) => { if (!canceled) setApuracoes(arr); })
      .catch((err) => {
        if (canceled) return;
        if (err instanceof ApiError) setError(err.message);
      });
    return () => { canceled = true; };
  }, [empresa.id]);

  if (error) return null;

  const mesAnterior = previousAnoMes();
  const mesAtual = currentAnoMes();
  const apurAnterior = apuracoes?.find((a) => a.ano_mes === mesAnterior);
  const apurAtual = apuracoes?.find((a) => a.ano_mes === mesAtual);
  const ehSimples = (empresa.regime_tributario || "").toLowerCase().includes("simples");

  // Empresas fora do Simples nao tem PGDAS-D — esconde o card
  if (!ehSimples && empresa.regime_tributario) {
    return null;
  }

  const renderApur = (a: Apuracao | undefined, label: string) => {
    if (!a) {
      return (
        <div style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 10, background: "var(--bg-1)" }}>
          <strong style={{ display: "block", marginBottom: 6 }}>{label}</strong>
          <small className="muted">Sem apuracao</small>
          <div style={{ marginTop: 8 }}>
            <Link
              href={`/apuracoes?empresa_id=${empresa.id}`}
              className="btn-secondary"
              style={{ padding: "4px 10px", fontSize: "0.78rem" }}
            >
              Criar / calcular
            </Link>
          </div>
        </div>
      );
    }
    return (
      <div style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 10, background: "var(--bg-1)" }}>
        <strong style={{ display: "block", marginBottom: 6 }}>{label}</strong>
        <span className={statusPillClass(a.status)} style={{ fontSize: "0.74rem" }}>
          {statusLabel(a.status)}
        </span>
        <dl className="kv-grid" style={{ marginTop: 8, fontSize: "0.82rem" }}>
          <dt>Receita bruta</dt>
          <dd>
            {a.receita_bruta
              ? Number(a.receita_bruta).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
              : "—"}
          </dd>
          <dt>Valor devido</dt>
          <dd>
            {a.valor_devido
              ? Number(a.valor_devido).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
              : "—"}
          </dd>
          {a.das_data_vencimento ? (
            <>
              <dt>Vencto DAS</dt>
              <dd>{a.das_data_vencimento}</dd>
            </>
          ) : null}
        </dl>
        <div style={{ marginTop: 8 }}>
          <Link
            href={`/apuracoes?empresa_id=${empresa.id}`}
            className="btn-secondary"
            style={{ padding: "4px 10px", fontSize: "0.78rem" }}
          >
            Gerenciar
          </Link>
        </div>
      </div>
    );
  };

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Apuracoes PGDAS-D · Simples Nacional</h3>
        <div className="page-actions">
          <Link
            href={`/apuracoes?empresa_id=${empresa.id}`}
            className="btn-secondary"
          >
            Abrir apuracoes
          </Link>
        </div>
      </header>

      <p className="muted" style={{ margin: 0, fontSize: "0.86rem" }}>
        Anexo <strong>{empresa.anexo_simples || "?"}</strong> ·{" "}
        atividade <strong>{empresa.atividade || "?"}</strong>. Calculo automatico
        a partir das NFes emitidas (ainda nao implementado download de emitidas
        — use modo manual por enquanto).
      </p>

      <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 12 }}>
        {renderApur(apurAnterior, `Competencia ${formatAnoMes(mesAnterior)}`)}
        {renderApur(apurAtual, `Competencia ${formatAnoMes(mesAtual)}`)}
      </div>
    </section>
  );
}

