"use client";

import { useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import { AdmissaoResumo, portalAdmissoes, portalCriarAdmissao } from "../lib/portal";

const NAVY = "#16294d";
const ORANGE = "#ec8b1c";
const ORANGE_TX = "#b96a0c";
const GREEN = "#1d9e75";
const GRAY = "#6b7488";
const RED = "#c0392b";
const BORDER = "#d7dbe6";

const PASSOS = ["Dados Admissionais", "Dados Pessoais", "Documentos", "Endereço", "Família", "Anexos"];

type Dep = { nome: string; cpf: string; parentesco: string; nascimento: string };
type Anexo = { nome: string; base64: string };

function statusInfo(s: string): { label: string; cor: string } {
  switch (s) {
    case "concluida": return { label: "Concluída", cor: GREEN };
    case "em_analise": return { label: "Em análise", cor: ORANGE_TX };
    case "cancelada": return { label: "Cancelada", cor: RED };
    default: return { label: "Recebida", cor: NAVY };
  }
}

export function PortalAdmissao() {
  const [modo, setModo] = useState<"lista" | "form">("lista");
  const [admissoes, setAdmissoes] = useState<AdmissaoResumo[] | null>(null);

  function carregar() {
    portalAdmissoes().then((r) => setAdmissoes(r.admissoes)).catch(() => setAdmissoes([]));
  }
  useEffect(() => { carregar(); }, []);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, color: NAVY, fontSize: 20 }}>👤➕ Admissão de funcionário</h2>
        {modo === "lista" ? (
          <button type="button" onClick={() => setModo("form")}
            style={{ background: ORANGE, color: "#fff", border: "none", borderRadius: 9, padding: "10px 18px", fontWeight: 500, cursor: "pointer" }}>
            + Nova admissão
          </button>
        ) : (
          <button type="button" onClick={() => setModo("lista")}
            style={{ background: "transparent", color: GRAY, border: `1px solid ${BORDER}`, borderRadius: 9, padding: "10px 18px", cursor: "pointer" }}>
            ← Voltar para a lista
          </button>
        )}
      </div>

      {modo === "form" ? (
        <AdmissaoForm onEnviado={() => { setModo("lista"); carregar(); }} />
      ) : (
        <div className="pac-card">
          <p style={{ margin: "0 0 12px", color: GRAY, fontSize: 13.5 }}>
            Solicite a admissão de um novo funcionário preenchendo o formulário. A solicitação vai
            direto para o escritório analisar e lançar no eSocial.
          </p>
          {admissoes === null ? (
            <p style={{ color: GRAY }}>Carregando…</p>
          ) : admissoes.length === 0 ? (
            <p style={{ color: GRAY }}>Nenhuma admissão solicitada ainda. Clique em <strong>+ Nova admissão</strong>.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="pac-table">
                <thead><tr><th>Funcionário</th><th>Cargo</th><th>Admissão</th><th>Status</th></tr></thead>
                <tbody>
                  {admissoes.map((a) => {
                    const s = statusInfo(a.status);
                    return (
                      <tr key={a.id}>
                        <td>{a.funcionario || "—"}</td>
                        <td>{a.cargo || "—"}</td>
                        <td>{a.data_admissao ? new Date(a.data_admissao + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                        <td><span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 6, border: `1px solid ${s.cor}`, color: s.cor }}>{s.label}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function lbl(t: string) {
  return <span style={{ fontSize: 12.5, fontWeight: 600, color: NAVY }}>{t}</span>;
}
const inp: React.CSSProperties = { padding: "9px 11px", borderRadius: 8, border: `1px solid ${BORDER}`, fontSize: 14, width: "100%" };

function AdmissaoForm({ onEnviado }: { onEnviado: () => void }) {
  const [step, setStep] = useState(1);
  const [d, setD] = useState<Record<string, string>>({ nacionalidade: "Brasileiro(a)" });
  const [deps, setDeps] = useState<Dep[]>([]);
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function set(k: string, v: string) { setD((cur) => ({ ...cur, [k]: v })); }

  function addDep() { setDeps((c) => [...c, { nome: "", cpf: "", parentesco: "", nascimento: "" }]); }
  function setDep(i: number, k: keyof Dep, v: string) {
    setDeps((c) => c.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  }
  function rmDep(i: number) { setDeps((c) => c.filter((_, j) => j !== i)); }

  async function onFiles(files: FileList | null) {
    if (!files) return;
    for (const f of Array.from(files)) {
      if (f.size > 25 * 1024 * 1024) { setErro(`${f.name} passa de 25 MB.`); continue; }
      const b64 = await new Promise<string>((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result).split(",")[1] || "");
        r.onerror = rej;
        r.readAsDataURL(f);
      });
      setAnexos((c) => [...c, { nome: f.name, base64: b64 }]);
    }
  }

  async function enviar() {
    if (!d.nome) { setErro("Informe o nome do funcionário (passo 2)."); setStep(2); return; }
    setBusy(true); setErro(null);
    try {
      await portalCriarAdmissao({ ...d, dependentes: deps }, anexos);
      onEnviado();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao enviar a admissão.");
    } finally { setBusy(false); }
  }

  const grid2: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 };
  const grid3: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 };
  const campo = (k: string, label: string, type = "text", ph = "") => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {lbl(label)}
      <input style={inp} type={type} placeholder={ph} value={d[k] || ""} onChange={(e) => set(k, e.target.value)} />
    </label>
  );
  const sel = (k: string, label: string, opts: string[]) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {lbl(label)}
      <select style={inp} value={d[k] || ""} onChange={(e) => set(k, e.target.value)}>
        <option value="">Selecione</option>
        {opts.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
  const UFS = ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"];

  return (
    <div className="pac-card">
      {/* Stepper */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 18 }}>
        {PASSOS.map((p, i) => {
          const n = i + 1; const ativo = n === step; const feito = n < step;
          return (
            <button key={p} type="button" onClick={() => setStep(n)}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 20, cursor: "pointer",
                fontSize: 12.5, border: `1px solid ${ativo ? ORANGE : BORDER}`,
                background: ativo ? "rgba(236,139,28,0.12)" : feito ? "rgba(29,158,117,0.10)" : "#fff",
                color: ativo ? ORANGE_TX : feito ? GREEN : GRAY, fontWeight: ativo ? 600 : 400,
              }}>
              <span style={{
                width: 18, height: 18, borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, color: "#fff", background: ativo ? ORANGE : feito ? GREEN : "#b6bdcc",
              }}>{feito ? "✓" : n}</span>
              {p}
            </button>
          );
        })}
      </div>

      {erro ? <div style={{ background: "rgba(192,57,43,0.10)", color: RED, padding: "8px 12px", borderRadius: 8, marginBottom: 14, fontSize: 13.5 }}>{erro}</div> : null}

      {/* Passo 1 — Dados admissionais */}
      {step === 1 ? (
        <div style={{ display: "grid", gap: 14 }}>
          <div style={grid3}>
            {campo("data_admissao", "Data de admissão *", "date")}
            {campo("funcao", "Função *", "text", "Ex: Auxiliar Administrativo")}
            {campo("salario", "Salário inicial", "text", "R$ 0,00")}
          </div>
          <div style={grid3}>
            {sel("tipo_contrato", "Tipo de contrato", ["Prazo indeterminado", "Prazo determinado", "Experiência (90 dias)", "Intermitente", "Jovem aprendiz"])}
            {campo("jornada_semanal", "Carga horária semanal", "text", "Ex: 44h")}
            {campo("horario", "Horário", "text", "Ex: 08:00-12:00 / 13:00-17:00")}
          </div>
        </div>
      ) : null}

      {/* Passo 2 — Dados pessoais */}
      {step === 2 ? (
        <div style={{ display: "grid", gap: 14 }}>
          {campo("nome", "Nome completo *")}
          <div style={grid2}>
            {campo("cpf", "CPF *", "text", "000.000.000-00")}
            {campo("data_nascimento", "Data de nascimento", "date")}
          </div>
          <div style={grid2}>
            {campo("nome_mae", "Nome da mãe")}
            {campo("nacionalidade", "Nacionalidade")}
          </div>
          <div style={grid3}>
            {campo("cidade_nascimento", "Cidade de nascimento")}
            {sel("uf_nascimento", "UF nascimento", UFS)}
            {sel("sexo", "Sexo", ["Masculino", "Feminino"])}
          </div>
          <div style={grid2}>
            {sel("estado_civil", "Estado civil", ["Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável"])}
            {sel("grau_instrucao", "Grau de instrução", ["Fundamental incompleto", "Fundamental completo", "Médio incompleto", "Médio completo", "Superior incompleto", "Superior completo", "Pós-graduação"])}
          </div>
        </div>
      ) : null}

      {/* Passo 3 — Documentos */}
      {step === 3 ? (
        <div style={{ display: "grid", gap: 16 }}>
          <div>
            <div style={{ color: GRAY, fontSize: 12.5, marginBottom: 8, fontWeight: 600 }}>PIS / NIS</div>
            <div style={grid2}>{campo("pis_nis", "Número do PIS/NIS")}{campo("titulo_eleitor", "Título de eleitor")}</div>
          </div>
          <div>
            <div style={{ color: GRAY, fontSize: 12.5, marginBottom: 8, fontWeight: 600 }}>Carteira de Trabalho (CTPS)</div>
            <div style={grid3}>{campo("ctps_numero", "Número")}{campo("ctps_serie", "Série")}{sel("ctps_uf", "UF", UFS)}</div>
          </div>
          <div>
            <div style={{ color: GRAY, fontSize: 12.5, marginBottom: 8, fontWeight: 600 }}>RG</div>
            <div style={grid3}>{campo("rg_numero", "Número")}{campo("rg_orgao", "Órgão emissor", "text", "SSP")}{sel("rg_uf", "UF", UFS)}</div>
          </div>
          <div>
            <div style={{ color: GRAY, fontSize: 12.5, marginBottom: 8, fontWeight: 600 }}>CNH (opcional)</div>
            <div style={grid3}>{campo("cnh_numero", "Número")}{campo("cnh_categoria", "Categoria", "text", "AB")}{campo("cnh_validade", "Validade", "date")}</div>
          </div>
        </div>
      ) : null}

      {/* Passo 4 — Endereço */}
      {step === 4 ? (
        <div style={{ display: "grid", gap: 14 }}>
          <div style={grid3}>
            {campo("cep", "CEP")}
            <div style={{ gridColumn: "span 2" }}>{campo("logradouro", "Logradouro")}</div>
          </div>
          <div style={grid3}>
            {campo("numero", "Número")}
            {campo("complemento", "Complemento")}
            {campo("bairro", "Bairro")}
          </div>
          <div style={grid2}>
            {campo("cidade", "Cidade")}
            {sel("uf", "UF", UFS)}
          </div>
        </div>
      ) : null}

      {/* Passo 5 — Família / dependentes */}
      {step === 5 ? (
        <div style={{ display: "grid", gap: 12 }}>
          <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>Dependentes (para IRRF e salário-família). Opcional.</p>
          {deps.map((dep, i) => (
            <div key={i} style={{ border: `1px solid ${BORDER}`, borderRadius: 10, padding: 12, display: "grid", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong style={{ color: NAVY, fontSize: 13 }}>Dependente {i + 1}</strong>
                <button type="button" onClick={() => rmDep(i)} style={{ background: "transparent", border: "none", color: RED, cursor: "pointer" }}>Remover</button>
              </div>
              <div style={grid2}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>{lbl("Nome")}<input style={inp} value={dep.nome} onChange={(e) => setDep(i, "nome", e.target.value)} /></label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>{lbl("CPF")}<input style={inp} value={dep.cpf} onChange={(e) => setDep(i, "cpf", e.target.value)} /></label>
              </div>
              <div style={grid2}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>{lbl("Parentesco")}
                  <select style={inp} value={dep.parentesco} onChange={(e) => setDep(i, "parentesco", e.target.value)}>
                    <option value="">Selecione</option>
                    {["Cônjuge/companheiro(a)", "Filho(a)", "Enteado(a)", "Pai/Mãe", "Outro"].map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>{lbl("Nascimento")}<input style={inp} type="date" value={dep.nascimento} onChange={(e) => setDep(i, "nascimento", e.target.value)} /></label>
              </div>
            </div>
          ))}
          <button type="button" onClick={addDep} style={{ alignSelf: "start", background: "transparent", border: `1px dashed ${ORANGE}`, color: ORANGE_TX, borderRadius: 8, padding: "8px 14px", cursor: "pointer" }}>+ Adicionar dependente</button>
        </div>
      ) : null}

      {/* Passo 6 — Anexos */}
      {step === 6 ? (
        <div style={{ display: "grid", gap: 12 }}>
          <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>Anexe os documentos digitalizados (RG, CPF, CTPS, comprovante de endereço, ASO admissional, foto…). PDF ou imagem, até 25 MB cada.</p>
          <label style={{ display: "inline-block", background: NAVY, color: "#fff", padding: "10px 18px", borderRadius: 9, cursor: "pointer", fontSize: 14, alignSelf: "start" }}>
            + Escolher arquivos
            <input type="file" multiple accept=".pdf,image/*" style={{ display: "none" }} onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
          </label>
          {anexos.length > 0 ? (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
              {anexos.map((a, i) => (
                <li key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", border: `1px solid ${BORDER}`, borderRadius: 8, padding: "8px 12px", fontSize: 13.5 }}>
                  <span>📎 {a.nome}</span>
                  <button type="button" onClick={() => setAnexos((c) => c.filter((_, j) => j !== i))} style={{ background: "transparent", border: "none", color: RED, cursor: "pointer" }}>remover</button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {/* Navegação */}
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 22, gap: 10 }}>
        <button type="button" disabled={step === 1 || busy} onClick={() => setStep((s) => s - 1)}
          style={{ background: "transparent", border: `1px solid ${BORDER}`, color: step === 1 ? "#c2c8d4" : GRAY, borderRadius: 9, padding: "10px 18px", cursor: step === 1 ? "default" : "pointer" }}>
          ← Voltar
        </button>
        {step < 6 ? (
          <button type="button" onClick={() => setStep((s) => s + 1)}
            style={{ background: ORANGE, color: "#fff", border: "none", borderRadius: 9, padding: "10px 22px", fontWeight: 500, cursor: "pointer" }}>
            Próximo →
          </button>
        ) : (
          <button type="button" onClick={enviar} disabled={busy}
            style={{ background: GREEN, color: "#fff", border: "none", borderRadius: 9, padding: "10px 22px", fontWeight: 500, cursor: busy ? "default" : "pointer", opacity: busy ? 0.7 : 1 }}>
            {busy ? "Enviando…" : "✓ Enviar admissão"}
          </button>
        )}
      </div>
    </div>
  );
}
