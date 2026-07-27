"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../../lib/api";
import { enviarIndicacao, portalLogin, type IndicacaoPayload } from "../../../lib/portal";

const NAVY = "#16294d";
const ORANGE = "#ec8b1c";
const GRAY = "#6b7488";

const INDICA_VAZIA: IndicacaoPayload = {
  nome_indicador: "", contato_indicador: "", empresa_indicador: "",
  nome_indicado: "", contato_indicado: "", observacao: "", website: "",
};

// Recursos REAIS do portal (batem com as abas de /portal).
const RECURSOS: { icone: string; titulo: string; desc: string }[] = [
  { icone: "📄", titulo: "Suas notas fiscais", desc: "Entradas e saídas organizadas — baixe XML e PDF quando precisar." },
  { icone: "🧾", titulo: "Guias e impostos", desc: "DAS e demais guias prontas para baixar e pagar em dia." },
  { icone: "📁", titulo: "Documentos da empresa", desc: "Contrato social, alvará, cartão CNPJ e procurações num só lugar." },
  { icone: "🔐", titulo: "Certificado digital", desc: "Acompanhe a validade e seja avisado antes de vencer." },
  { icone: "💬", titulo: "Fale com o escritório", desc: "Chat e ligação direto com a nossa equipe, sem sair do portal." },
];

export default function PortalLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // PAC Indica (modal de formulário)
  const [indicaOpen, setIndicaOpen] = useState(false);
  const [indica, setIndica] = useState<IndicacaoPayload>(INDICA_VAZIA);
  const [indicaBusy, setIndicaBusy] = useState(false);
  const [indicaErro, setIndicaErro] = useState<string | null>(null);
  const [indicaOk, setIndicaOk] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setBusy(true);
    try {
      await portalLogin(email.trim(), password);
      router.replace("/portal");
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao entrar.");
    } finally {
      setBusy(false);
    }
  }

  function updIndica(campo: keyof IndicacaoPayload) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setIndica((s) => ({ ...s, [campo]: e.target.value }));
  }

  async function handleIndica(e: React.FormEvent) {
    e.preventDefault();
    setIndicaErro(null);
    setIndicaBusy(true);
    try {
      await enviarIndicacao({
        ...indica,
        nome_indicador: indica.nome_indicador.trim(),
        contato_indicador: indica.contato_indicador.trim(),
        nome_indicado: indica.nome_indicado.trim(),
        contato_indicado: indica.contato_indicado.trim(),
      });
      setIndicaOk(true);
    } catch (err) {
      setIndicaErro(err instanceof ApiError ? err.message : "Não foi possível enviar. Tente novamente.");
    } finally {
      setIndicaBusy(false);
    }
  }

  function fecharIndica() {
    setIndicaOpen(false);
    setTimeout(() => { setIndicaOk(false); setIndicaErro(null); setIndica(INDICA_VAZIA); }, 200);
  }

  return (
    <div className="wrap">
      {/* ================= APRESENTAÇÃO (hero) ================= */}
      <aside className="hero">
        <div className="hero-inner">
          <img src="/pac-logo-branco.svg" alt="PAC Inteligência Tributária" className="hero-logo" />

          <h1 className="hero-title">
            A sua contabilidade, <span>na palma da mão.</span>
          </h1>
          <p className="hero-sub">
            A <strong>PAC Inteligência Tributária</strong> cuida da parte fiscal e
            contábil da sua empresa. Aqui, no seu portal, você acompanha tudo em um
            só lugar — a qualquer hora, do computador ou do celular.
          </p>

          <ul className="recursos">
            {RECURSOS.map((r) => (
              <li key={r.titulo}>
                <span className="ric" aria-hidden>{r.icone}</span>
                <div className="rtx">
                  <strong>{r.titulo}</strong>
                  <span>{r.desc}</span>
                </div>
              </li>
            ))}
          </ul>

          <button type="button" className="indica" onClick={() => setIndicaOpen(true)}>
            <span className="indica-badge">PAC<br />Indica</span>
            <span className="indica-tx">
              <strong>Participe do programa PAC Indica</strong>
              <span>Indique outro empresário para a PAC e vocês dois são recompensados.</span>
            </span>
            <span className="indica-arrow" aria-hidden>→</span>
          </button>
        </div>
      </aside>

      {/* ================= LOGIN ================= */}
      <main className="login">
        <div className="card">
          <div className="card-head">
            <img src="/pac-logo.svg" alt="PAC Inteligência Tributária" className="card-logo" />
            <h2>Portal do Cliente</h2>
            <p>Acesse as notas da sua empresa</p>
          </div>
          <form onSubmit={handleSubmit}>
            <label>E-mail
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
            </label>
            <label>Senha
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </label>
            {erro ? <p className="erro">{erro}</p> : null}
            <button type="submit" disabled={busy}>{busy ? "Entrando..." : "Entrar"}</button>
          </form>
          <p className="ajuda">
            Ainda não tem acesso? Fale com o seu contador na PAC.
          </p>
        </div>
        <p className="rodape">© PAC Inteligência Tributária · Acesso exclusivo para clientes</p>
      </main>

      {/* ================= MODAL PAC INDICA ================= */}
      {indicaOpen ? (
        <div className="modal-bg" onClick={fecharIndica} role="dialog" aria-modal="true">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal-x" onClick={fecharIndica} aria-label="Fechar">×</button>

            {indicaOk ? (
              <div className="modal-ok">
                <div className="ok-emoji" aria-hidden>🎉</div>
                <h3>Indicação enviada!</h3>
                <p>Obrigado por indicar. Nossa equipe vai entrar em contato em breve — e você já está participando do programa PAC Indica.</p>
                <button type="button" className="modal-fim" onClick={fecharIndica}>Fechar</button>
              </div>
            ) : (
              <>
                <div className="modal-head">
                  <span className="indica-badge">PAC<br />Indica</span>
                  <div>
                    <h3>Indique e seja recompensado</h3>
                    <p>Conhece um empresário que precisa de uma contabilidade de verdade? Indique para a PAC — é rápido.</p>
                  </div>
                </div>

                <form onSubmit={handleIndica} className="modal-form">
                  <div className="modal-sec">Seus dados</div>
                  <label>Seu nome*
                    <input value={indica.nome_indicador} onChange={updIndica("nome_indicador")} required maxLength={120} />
                  </label>
                  <label>Seu telefone ou e-mail*
                    <input value={indica.contato_indicador} onChange={updIndica("contato_indicador")} required maxLength={120} placeholder="(62) 99999-9999" />
                  </label>
                  <label>Sua empresa <span className="opt">(opcional)</span>
                    <input value={indica.empresa_indicador} onChange={updIndica("empresa_indicador")} maxLength={160} />
                  </label>

                  <div className="modal-sec">Quem você indica</div>
                  <label>Nome dele(a)*
                    <input value={indica.nome_indicado} onChange={updIndica("nome_indicado")} required maxLength={120} />
                  </label>
                  <label>Telefone ou e-mail dele(a)*
                    <input value={indica.contato_indicado} onChange={updIndica("contato_indicado")} required maxLength={120} placeholder="(62) 99999-9999" />
                  </label>
                  <label>Observação <span className="opt">(opcional)</span>
                    <textarea value={indica.observacao} onChange={updIndica("observacao")} rows={2} maxLength={1000} placeholder="Ex.: ramo, cidade, melhor horário para contato…" />
                  </label>

                  {/* honeypot anti-bot — invisível, sempre vazio no envio humano */}
                  <input className="hp" tabIndex={-1} autoComplete="off" value={indica.website} onChange={updIndica("website")} aria-hidden />

                  {indicaErro ? <p className="erro">{indicaErro}</p> : null}
                  <button type="submit" disabled={indicaBusy}>{indicaBusy ? "Enviando..." : "Enviar indicação"}</button>
                </form>
              </>
            )}
          </div>
        </div>
      ) : null}

      <style jsx>{`
        .wrap {
          min-height: 100vh;
          display: grid;
          grid-template-columns: 1.05fr minmax(400px, 480px);
          font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif;
          background: #f5f7fa;
        }

        /* ---------- HERO ---------- */
        .hero {
          position: relative;
          overflow: hidden;
          color: #fff;
          background:
            radial-gradient(circle at 82% -8%, rgba(236, 139, 28, 0.22), transparent 45%),
            radial-gradient(circle at 0% 108%, rgba(236, 139, 28, 0.10), transparent 42%),
            linear-gradient(158deg, ${NAVY} 0%, #0f1d38 100%);
          display: flex;
          align-items: center;
          padding: 56px 6vw;
        }
        .hero-inner { width: 100%; max-width: 560px; margin-left: auto; }
        .hero-logo { height: 40px; margin-bottom: 40px; }
        .hero-title {
          margin: 0 0 16px; font-size: clamp(28px, 3.4vw, 40px); line-height: 1.12;
          font-weight: 700; letter-spacing: -0.5px;
        }
        .hero-title span { color: ${ORANGE}; }
        .hero-sub { margin: 0 0 34px; font-size: 15.5px; line-height: 1.65; color: rgba(255, 255, 255, 0.74); max-width: 490px; }
        .hero-sub strong { color: #fff; font-weight: 600; }

        .recursos { list-style: none; margin: 0 0 30px; padding: 0; display: grid; gap: 15px; }
        .recursos li { display: flex; gap: 14px; align-items: flex-start; }
        .ric {
          flex: 0 0 auto; width: 40px; height: 40px; border-radius: 11px;
          display: grid; place-items: center; font-size: 19px;
          background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.12);
        }
        .rtx { display: grid; gap: 2px; }
        .rtx strong { font-size: 14.5px; font-weight: 600; color: #fff; }
        .rtx span { font-size: 13px; line-height: 1.5; color: rgba(255, 255, 255, 0.6); }

        .indica {
          display: flex; align-items: center; gap: 16px; text-decoration: none;
          width: 100%; text-align: left; font: inherit; color: inherit; cursor: pointer;
          padding: 16px 18px; border-radius: 15px;
          background: linear-gradient(100deg, rgba(236, 139, 28, 0.18), rgba(236, 139, 28, 0.05));
          border: 1px solid rgba(236, 139, 28, 0.42);
          transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
        }
        .indica:hover { transform: translateY(-2px); border-color: rgba(236, 139, 28, 0.75); box-shadow: 0 12px 30px rgba(236, 139, 28, 0.18); }
        .indica-badge {
          flex: 0 0 auto; width: 52px; height: 52px; border-radius: 13px; background: ${ORANGE};
          color: #fff; font-weight: 800; font-size: 13px; line-height: 1.05; letter-spacing: .3px;
          display: grid; place-items: center; text-align: center; text-transform: uppercase;
          box-shadow: 0 6px 16px rgba(236, 139, 28, 0.4);
        }
        .indica-tx { display: grid; gap: 3px; }
        .indica-tx strong { font-size: 14.5px; font-weight: 700; color: #fff; }
        .indica-tx span { font-size: 12.5px; line-height: 1.5; color: rgba(255, 255, 255, 0.72); }
        .indica-arrow { margin-left: auto; color: ${ORANGE}; font-size: 20px; font-weight: 700; }

        /* ---------- LOGIN ---------- */
        .login { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; padding: 40px 28px; }
        .card {
          width: 100%; max-width: 372px; background: #fff; border: 1px solid #e6eaf0;
          border-radius: 16px; padding: 32px 30px; box-shadow: 0 16px 40px rgba(22, 41, 77, 0.08);
        }
        .card-head { text-align: center; margin-bottom: 22px; }
        .card-logo { height: 42px; margin-bottom: 14px; }
        .card-head h2 { margin: 0; color: ${NAVY}; font-size: 20px; font-weight: 700; }
        .card-head p { margin: 5px 0 0; color: ${GRAY}; font-size: 13px; }
        .card form { display: grid; gap: 14px; }
        .card label { display: grid; gap: 6px; font-size: 13px; color: ${GRAY}; }
        .card input {
          appearance: none; border: 1px solid #d8dee8; border-radius: 10px; padding: 11px 13px;
          font: inherit; font-size: 15px; background: #fff; color: #1b2333;
        }
        .card input:focus { outline: none; border-color: ${ORANGE}; box-shadow: 0 0 0 3px rgba(236, 139, 28, 0.18); }
        .card button {
          appearance: none; border: none; background: ${ORANGE}; color: #fff; font: inherit;
          font-size: 15px; font-weight: 600; padding: 12px; border-radius: 10px; cursor: pointer; margin-top: 4px;
        }
        .card button:hover:not(:disabled) { filter: brightness(1.05); }
        .card button:disabled { opacity: .6; cursor: not-allowed; }
        .erro {
          margin: 0; color: #a32d2d; font-size: 13px; background: #fdeaea; border: 1px solid #f3c2c2;
          padding: 9px 12px; border-radius: 8px;
        }
        .ajuda { margin: 16px 0 0; text-align: center; font-size: 12.5px; color: ${GRAY}; }
        .rodape { margin: 0; font-size: 11.5px; color: #97a0b0; text-align: center; }

        /* ---------- MODAL PAC INDICA ---------- */
        .modal-bg {
          position: fixed; inset: 0; z-index: 50; display: grid; place-items: center;
          padding: 18px; background: rgba(15, 29, 56, 0.55); backdrop-filter: blur(3px);
          animation: fade .16s ease;
        }
        @keyframes fade { from { opacity: 0; } to { opacity: 1; } }
        .modal {
          position: relative; width: 100%; max-width: 440px; max-height: 92vh; overflow-y: auto;
          background: #fff; border-radius: 18px; padding: 26px 26px 24px;
          box-shadow: 0 24px 60px rgba(15, 29, 56, 0.35); animation: pop .18s ease;
        }
        @keyframes pop { from { transform: translateY(10px) scale(.98); opacity: .6; } to { transform: none; opacity: 1; } }
        .modal-x {
          position: absolute; top: 12px; right: 14px; width: 32px; height: 32px; border: none;
          background: #f1f3f7; color: ${GRAY}; border-radius: 9px; font-size: 20px; line-height: 1;
          cursor: pointer;
        }
        .modal-x:hover { background: #e6e9f0; }
        .modal-head { display: flex; gap: 14px; align-items: flex-start; margin-bottom: 20px; padding-right: 24px; }
        .modal-head h3 { margin: 0; color: ${NAVY}; font-size: 18px; font-weight: 700; }
        .modal-head p { margin: 5px 0 0; color: ${GRAY}; font-size: 13px; line-height: 1.5; }
        .modal-form { display: grid; gap: 12px; }
        .modal-sec {
          margin-top: 6px; font-size: 11.5px; font-weight: 700; letter-spacing: .5px; text-transform: uppercase;
          color: ${ORANGE};
        }
        .modal-form label { display: grid; gap: 5px; font-size: 12.5px; color: ${GRAY}; }
        .modal-form .opt { color: #a6adbb; font-weight: 400; text-transform: none; }
        .modal-form input, .modal-form textarea {
          appearance: none; border: 1px solid #d8dee8; border-radius: 9px; padding: 10px 12px;
          font: inherit; font-size: 14.5px; background: #fff; color: #1b2333; resize: vertical;
        }
        .modal-form input:focus, .modal-form textarea:focus {
          outline: none; border-color: ${ORANGE}; box-shadow: 0 0 0 3px rgba(236, 139, 28, 0.16);
        }
        .modal-form button[type="submit"] {
          appearance: none; border: none; background: ${ORANGE}; color: #fff; font: inherit;
          font-size: 15px; font-weight: 600; padding: 12px; border-radius: 10px; cursor: pointer; margin-top: 6px;
        }
        .modal-form button[type="submit"]:hover:not(:disabled) { filter: brightness(1.05); }
        .modal-form button[type="submit"]:disabled { opacity: .6; cursor: not-allowed; }
        .modal-form .erro {
          margin: 0; color: #a32d2d; font-size: 13px; background: #fdeaea; border: 1px solid #f3c2c2;
          padding: 9px 12px; border-radius: 8px;
        }
        /* honeypot — fora da tela, sem ocupar espaço */
        .hp { position: absolute; left: -9999px; width: 1px; height: 1px; opacity: 0; }
        .modal-ok { text-align: center; padding: 14px 6px 4px; }
        .ok-emoji { font-size: 46px; }
        .modal-ok h3 { margin: 10px 0 6px; color: ${NAVY}; font-size: 20px; }
        .modal-ok p { margin: 0 auto 20px; color: ${GRAY}; font-size: 14px; line-height: 1.55; max-width: 330px; }
        .modal-fim {
          appearance: none; border: none; background: ${NAVY}; color: #fff; font: inherit; font-weight: 600;
          font-size: 14.5px; padding: 11px 26px; border-radius: 10px; cursor: pointer;
        }

        /* ---------- RESPONSIVO ---------- */
        @media (max-width: 900px) {
          .wrap { display: flex; flex-direction: column; }
          .login { order: 1; padding: 34px 20px 22px; }        /* login primeiro no celular */
          .hero { order: 2; padding: 40px 24px 46px; }
          .hero-inner { margin: 0 auto; max-width: 520px; }
          .hero-logo { margin-bottom: 26px; }
          .rodape { order: 3; padding-bottom: 22px; }
        }
      `}</style>
    </div>
  );
}
