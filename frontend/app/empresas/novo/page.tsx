"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import { ProtectedRoute } from "../../../components/protected-route";
import { ApiError } from "../../../lib/api";
import {
  buscarCnpjPublico,
  criarEmpresa,
  EmpresaCreatePayload,
  uploadCertificado,
} from "../../../lib/empresas";

const REGIMES = [
  "Simples Nacional",
  "Lucro Presumido",
  "Lucro Real",
  "MEI",
];

const SITUACOES = ["ATIVA", "BAIXADA", "SUSPENSA", "INAPTA", "NULA"];

const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
  "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
  "SE", "SP", "TO",
];

type Tab = "cadastrais" | "endereco" | "credenciais";

function onlyDigits(value: string): string {
  return value.replace(/\D+/g, "");
}

/**
 * Trim defensivo: aceita string, number, null ou undefined.
 * Necessário porque a BrasilAPI às vezes devolve campos numéricos
 * (ex: natureza_juridica_codigo como Number 2062 em vez de String "2062").
 */
function safeTrim(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function isValidCnpj(cnpj: string): boolean {
  return cnpj.length === 14 && /^\d+$/.test(cnpj);
}

export default function NovaEmpresaPage() {
  return (
    <ProtectedRoute>
      <NovaEmpresaContent />
    </ProtectedRoute>
  );
}

function NovaEmpresaContent() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("cadastrais");
  const [submitting, setSubmitting] = useState(false);
  const [buscandoCnpj, setBuscandoCnpj] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // Marca quando o auto-fill ja rodou pra evitar sobrescrever edicoes manuais
  const cnpjJaPesquisado = useRef<string | null>(null);

  // --- Estado: dados cadastrais ---
  const [cnpj, setCnpj] = useState("");
  const [razaoSocial, setRazaoSocial] = useState("");
  const [nomeFantasia, setNomeFantasia] = useState("");
  const [inscricaoEstadual, setInscricaoEstadual] = useState("");
  const [inscricaoMunicipal, setInscricaoMunicipal] = useState("");
  const [naturezaJuridicaCodigo, setNaturezaJuridicaCodigo] = useState("");
  const [naturezaJuridicaDescricao, setNaturezaJuridicaDescricao] = useState("");
  const [regime, setRegime] = useState("");
  const [tributacao, setTributacao] = useState("");
  const [dataAbertura, setDataAbertura] = useState("");
  const [telefone, setTelefone] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [emailContato, setEmailContato] = useState("");
  const [situacaoCadastral, setSituacaoCadastral] = useState("");

  // --- Estado: endereço ---
  const [cep, setCep] = useState("");
  const [logradouroTipo, setLogradouroTipo] = useState("");
  const [logradouro, setLogradouro] = useState("");
  const [numero, setNumero] = useState("");
  const [complemento, setComplemento] = useState("");
  const [bairro, setBairro] = useState("");
  const [municipio, setMunicipio] = useState("");
  const [uf, setUf] = useState("");

  // --- Estado: certificado A1 (envio diferido — só após empresa criada) ---
  const [certArquivo, setCertArquivo] = useState<File | null>(null);
  const [certSenha, setCertSenha] = useState("");

  async function handleBuscarCnpj(opts: { silencioso?: boolean } = {}) {
    const digits = onlyDigits(cnpj);
    if (!isValidCnpj(digits)) {
      if (!opts.silencioso) {
        setError("Informe um CNPJ valido (14 dígitos) antes de buscar.");
      }
      return;
    }
    // Evita refetch redundante (auto + manual ou re-render)
    if (cnpjJaPesquisado.current === digits && opts.silencioso) return;
    setBuscandoCnpj(true);
    setError(null);
    if (!opts.silencioso) setToast(null);
    try {
      const r = await buscarCnpjPublico(digits);
      cnpjJaPesquisado.current = digits;
      // Sobrescreve apenas se o campo estiver vazio (preserva edicao manual).
      // SEMPRE converte pra string (BrasilAPI às vezes devolve numbers, ex: 2062
      // pra natureza_juridica_codigo — sem essa coerção o .trim() depois quebra).
      const setSeVazio = (
        atual: string,
        novo: unknown,
        setter: (v: string) => void,
      ) => {
        if (atual === "" && novo !== null && novo !== undefined && novo !== "") {
          setter(String(novo));
        }
      };
      setSeVazio(razaoSocial, r.razao_social, setRazaoSocial);
      setSeVazio(nomeFantasia, r.nome_fantasia, setNomeFantasia);
      setSeVazio(naturezaJuridicaCodigo, r.natureza_juridica_codigo, setNaturezaJuridicaCodigo);
      setSeVazio(naturezaJuridicaDescricao, r.natureza_juridica_descricao, setNaturezaJuridicaDescricao);
      setSeVazio(dataAbertura, r.data_abertura, setDataAbertura);
      setSeVazio(telefone, r.telefone, setTelefone);
      setSeVazio(emailContato, r.email_contato, setEmailContato);
      setSeVazio(situacaoCadastral, r.situacao_cadastral, setSituacaoCadastral);
      setSeVazio(regime, r.regime_tributario, setRegime);
      setSeVazio(cep, r.cep, setCep);
      setSeVazio(logradouroTipo, r.logradouro_tipo, setLogradouroTipo);
      setSeVazio(logradouro, r.logradouro, setLogradouro);
      setSeVazio(numero, r.numero, setNumero);
      setSeVazio(complemento, r.complemento, setComplemento);
      setSeVazio(bairro, r.bairro, setBairro);
      setSeVazio(municipio, r.municipio, setMunicipio);
      setSeVazio(uf, r.uf, setUf);
      setToast(
        `✓ Carregado: ${r.razao_social}` +
        (r._raw.cnae_principal.descricao
          ? ` · CNAE: ${r._raw.cnae_principal.descricao}`
          : "")
      );
    } catch (err) {
      if (!opts.silencioso) {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao buscar CNPJ.");
      }
    } finally {
      setBuscandoCnpj(false);
    }
  }

  // Auto-busca quando CNPJ completa 14 digitos (debounce 500ms)
  useEffect(() => {
    const digits = onlyDigits(cnpj);
    if (!isValidCnpj(digits)) return;
    if (cnpjJaPesquisado.current === digits) return;
    const t = setTimeout(() => {
      handleBuscarCnpj({ silencioso: true });
    }, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cnpj]);

  async function handleBuscarCep() {
    const digits = onlyDigits(cep);
    if (digits.length !== 8) return;
    setError(null);
    try {
      const r = await fetch(`https://viacep.com.br/ws/${digits}/json/`);
      const j = await r.json();
      if (j.erro) {
        setError("CEP nao encontrado.");
        return;
      }
      if (j.tipoLogradouro && !logradouroTipo) setLogradouroTipo(j.tipoLogradouro);
      if (j.logradouro && !logradouro) setLogradouro(j.logradouro);
      if (j.bairro && !bairro) setBairro(j.bairro);
      if (j.localidade && !municipio) setMunicipio(j.localidade);
      if (j.uf && !uf) setUf(j.uf);
    } catch {
      // Silencioso — busca CEP é só ajuda
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const cnpjLimpo = onlyDigits(cnpj);
    if (!isValidCnpj(cnpjLimpo)) {
      setError("CNPJ deve ter 14 digitos.");
      setTab("cadastrais");
      return;
    }
    if (!safeTrim(razaoSocial)) {
      setError("Razao social obrigatoria.");
      setTab("cadastrais");
      return;
    }

    // Usa safeTrim em todos os campos porque BrasilAPI às vezes devolve
    // valores numéricos (ex: natureza_juridica_codigo) que quebrariam .trim().
    const payload: EmpresaCreatePayload = {
      cnpj: cnpjLimpo,
      razao_social: safeTrim(razaoSocial),
      nome_fantasia: safeTrim(nomeFantasia) || undefined,
      inscricao_estadual: safeTrim(inscricaoEstadual) || undefined,
      inscricao_municipal: safeTrim(inscricaoMunicipal) || undefined,
      natureza_juridica_codigo: safeTrim(naturezaJuridicaCodigo) || undefined,
      natureza_juridica_descricao: safeTrim(naturezaJuridicaDescricao) || undefined,
      tributacao: safeTrim(tributacao) || undefined,
      regime_tributario: regime || undefined,
      data_abertura: dataAbertura || undefined,
      telefone: safeTrim(telefone) || undefined,
      whatsapp: safeTrim(whatsapp) || undefined,
      email_contato: safeTrim(emailContato) || undefined,
      situacao_cadastral: situacaoCadastral || undefined,
      cep: onlyDigits(safeTrim(cep)) || undefined,
      logradouro_tipo: safeTrim(logradouroTipo) || undefined,
      logradouro: safeTrim(logradouro) || undefined,
      numero: safeTrim(numero) || undefined,
      complemento: safeTrim(complemento) || undefined,
      bairro: safeTrim(bairro) || undefined,
      municipio: safeTrim(municipio) || undefined,
      uf: uf || undefined,
      ativo: true,
    };

    setSubmitting(true);
    try {
      const empresa = await criarEmpresa(payload);

      // Se enviou cert, faz upload em seguida
      if (certArquivo && certSenha) {
        try {
          await uploadCertificado(empresa.id, certArquivo, certSenha);
        } catch (err) {
          setError(
            "Empresa cadastrada, mas falha ao salvar certificado: " +
            (err instanceof ApiError ? err.message : String(err)) +
            ". Suba o certificado novamente na tela da empresa."
          );
          setSubmitting(false);
          router.replace(`/empresas/${empresa.id}`);
          return;
        }
      }

      router.replace(`/empresas/${empresa.id}`);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Falha ao criar empresa.");
      setSubmitting(false);
    }
  }

  function handleCertFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    setCertArquivo(f || null);
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h2>Nova empresa</h2>
          <p className="muted">
            Preencha os 3 passos. O certificado A1 e opcional — pode subir depois.
          </p>
        </div>
        <div className="page-actions">
          <Link href="/empresas" className="btn-secondary">Cancelar</Link>
        </div>
      </header>

      {/* Abas */}
      <section className="panel" style={{ padding: 0, marginBottom: 12 }}>
        <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
          {(
            [
              { id: "cadastrais", label: "1. Dados cadastrais" },
              { id: "endereco", label: "2. Endereço" },
              { id: "credenciais", label: "3. Credenciais (opcional)" },
            ] as { id: Tab; label: string }[]
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={tab === t.id ? "btn-primary" : "btn-secondary"}
              style={{
                borderRadius: 0,
                border: "none",
                padding: "12px 18px",
                background: tab === t.id ? "var(--accent)" : "transparent",
                color: tab === t.id ? "var(--bg-0)" : "var(--text)",
                cursor: "pointer",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </section>

      {toast ? <p className="toast">{toast}</p> : null}
      {error ? <p className="toast toast-error">{error}</p> : null}

      <section className="panel form-card">
        <form onSubmit={handleSubmit} className="form-stack">

          {/* ============ ABA 1: Dados Cadastrais ============ */}
          {tab === "cadastrais" && (
            <>
              <p className="section-divider">Identificação</p>
              <div className="form-grid" style={{ gridTemplateColumns: "1fr 2fr" }}>
                <label>
                  <span>
                    CNPJ * <small className="muted">(preenche automaticamente)</small>
                  </span>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input
                      type="text"
                      inputMode="numeric"
                      placeholder="14 digitos"
                      value={cnpj}
                      onChange={(e) => setCnpj(e.target.value)}
                      autoFocus
                      required
                      style={{ flex: 1 }}
                    />
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleBuscarCnpj()}
                      disabled={buscandoCnpj || !isValidCnpj(onlyDigits(cnpj))}
                      title="Recarrega os dados via BrasilAPI sobrescrevendo apenas campos vazios"
                      style={{ whiteSpace: "nowrap" }}
                    >
                      {buscandoCnpj ? "..." : "🔄 Recarregar"}
                    </button>
                  </div>
                </label>
                <label>
                  <span>Razão social *</span>
                  <input
                    type="text"
                    value={razaoSocial}
                    onChange={(e) => setRazaoSocial(e.target.value)}
                    required
                  />
                </label>
              </div>

              <div className="form-grid">
                <label>
                  <span>Nome fantasia</span>
                  <input
                    type="text"
                    value={nomeFantasia}
                    onChange={(e) => setNomeFantasia(e.target.value)}
                  />
                </label>
                <label>
                  <span>Inscrição estadual</span>
                  <input
                    type="text"
                    value={inscricaoEstadual}
                    onChange={(e) => setInscricaoEstadual(e.target.value)}
                  />
                </label>
                <label>
                  <span>Inscrição municipal</span>
                  <input
                    type="text"
                    value={inscricaoMunicipal}
                    onChange={(e) => setInscricaoMunicipal(e.target.value)}
                  />
                </label>
              </div>

              <p className="section-divider">Natureza jurídica e tributação</p>
              <div className="form-grid">
                <label>
                  <span>Código natureza jurídica</span>
                  <input
                    type="text"
                    value={naturezaJuridicaCodigo}
                    onChange={(e) => setNaturezaJuridicaCodigo(e.target.value)}
                    placeholder="ex: 2062"
                  />
                </label>
                <label style={{ gridColumn: "span 2" }}>
                  <span>Descrição natureza jurídica</span>
                  <input
                    type="text"
                    value={naturezaJuridicaDescricao}
                    onChange={(e) => setNaturezaJuridicaDescricao(e.target.value)}
                    placeholder="ex: Sociedade Empresária Limitada"
                  />
                </label>
              </div>

              <div className="form-grid">
                <label>
                  <span>Regime tributário</span>
                  <select value={regime} onChange={(e) => setRegime(e.target.value)}>
                    <option value="">Selecione</option>
                    {REGIMES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Tributação</span>
                  <input
                    type="text"
                    value={tributacao}
                    onChange={(e) => setTributacao(e.target.value)}
                    placeholder="ex: ICMS Normal, Imune"
                  />
                </label>
                <label>
                  <span>Situação cadastral</span>
                  <select
                    value={situacaoCadastral}
                    onChange={(e) => setSituacaoCadastral(e.target.value)}
                  >
                    <option value="">Selecione</option>
                    {SITUACOES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
              </div>

              <p className="section-divider">Contato</p>
              <div className="form-grid">
                <label>
                  <span>Data de abertura</span>
                  <input
                    type="date"
                    value={dataAbertura}
                    onChange={(e) => setDataAbertura(e.target.value)}
                  />
                </label>
                <label>
                  <span>Telefone</span>
                  <input
                    type="text"
                    value={telefone}
                    onChange={(e) => setTelefone(e.target.value)}
                    placeholder="(00) 0000-0000"
                  />
                </label>
                <label>
                  <span>WhatsApp</span>
                  <input
                    type="text"
                    value={whatsapp}
                    onChange={(e) => setWhatsapp(e.target.value)}
                    placeholder="(00) 90000-0000"
                  />
                </label>
                <label style={{ gridColumn: "span 2" }}>
                  <span>E-mail de contato</span>
                  <input
                    type="email"
                    value={emailContato}
                    onChange={(e) => setEmailContato(e.target.value)}
                  />
                </label>
              </div>

              <div className="form-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setTab("endereco")}
                >
                  Próximo: Endereço →
                </button>
              </div>
            </>
          )}

          {/* ============ ABA 2: Endereço ============ */}
          {tab === "endereco" && (
            <>
              <p className="section-divider">Localização</p>
              <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr 2fr" }}>
                <label>
                  <span>CEP</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder="00000-000"
                    value={cep}
                    onChange={(e) => setCep(e.target.value)}
                    onBlur={handleBuscarCep}
                  />
                </label>
                <label>
                  <span>Tipo logradouro</span>
                  <input
                    type="text"
                    value={logradouroTipo}
                    onChange={(e) => setLogradouroTipo(e.target.value)}
                    placeholder="Rua, Av, Travessa..."
                  />
                </label>
                <label>
                  <span>Logradouro</span>
                  <input
                    type="text"
                    value={logradouro}
                    onChange={(e) => setLogradouro(e.target.value)}
                  />
                </label>
              </div>
              <div className="form-grid" style={{ gridTemplateColumns: "1fr 2fr 2fr" }}>
                <label>
                  <span>Número</span>
                  <input
                    type="text"
                    value={numero}
                    onChange={(e) => setNumero(e.target.value)}
                  />
                </label>
                <label>
                  <span>Complemento</span>
                  <input
                    type="text"
                    value={complemento}
                    onChange={(e) => setComplemento(e.target.value)}
                  />
                </label>
                <label>
                  <span>Bairro</span>
                  <input
                    type="text"
                    value={bairro}
                    onChange={(e) => setBairro(e.target.value)}
                  />
                </label>
              </div>
              <div className="form-grid" style={{ gridTemplateColumns: "3fr 1fr" }}>
                <label>
                  <span>Município</span>
                  <input
                    type="text"
                    value={municipio}
                    onChange={(e) => setMunicipio(e.target.value)}
                  />
                </label>
                <label>
                  <span>UF</span>
                  <select value={uf} onChange={(e) => setUf(e.target.value)}>
                    <option value="">--</option>
                    {UFS.map((u) => (
                      <option key={u} value={u}>{u}</option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="form-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setTab("cadastrais")}
                >
                  ← Voltar
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setTab("credenciais")}
                >
                  Próximo: Credenciais →
                </button>
              </div>
            </>
          )}

          {/* ============ ABA 3: Credenciais ============ */}
          {tab === "credenciais" && (
            <>
              <p className="section-divider">Certificado Digital A1 (opcional)</p>
              <p className="muted" style={{ fontSize: "0.85rem", margin: 0 }}>
                Faça upload do arquivo .pfx + senha. Pode pular agora e subir depois
                na tela da empresa.
              </p>
              <div className="form-grid" style={{ gridTemplateColumns: "2fr 1fr" }}>
                <label>
                  <span>Arquivo .pfx</span>
                  <input
                    type="file"
                    accept=".pfx,.p12"
                    onChange={handleCertFile}
                  />
                  {certArquivo ? (
                    <small className="muted">
                      {certArquivo.name} ({(certArquivo.size / 1024).toFixed(1)} KB)
                    </small>
                  ) : null}
                </label>
                <label>
                  <span>Senha do certificado</span>
                  <input
                    type="password"
                    value={certSenha}
                    onChange={(e) => setCertSenha(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              </div>

              <p className="muted" style={{ fontSize: "0.78rem", marginTop: 12 }}>
                Outras credenciais (Prefeitura, Emissor Nacional, Simples Nacional)
                ficam para configurar na tela da empresa após o cadastro.
              </p>

              <div className="form-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setTab("endereco")}
                >
                  ← Voltar
                </button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? "Salvando..." : "Salvar empresa"}
                </button>
              </div>
            </>
          )}
        </form>
      </section>
    </>
  );
}
