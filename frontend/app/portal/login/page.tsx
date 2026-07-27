"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../../lib/api";
import { portalLogin } from "../../../lib/portal";

const NAVY = "#16294d";
const ORANGE = "#ec8b1c";
const GRAY = "#6b7488";

// E-mail do escritório para o "Quero indicar" (troque por um link wa.me do
// WhatsApp quando tiver o número — converte melhor que e-mail).
const INDICA_HREF =
  "mailto:paixaoassessoriacontabil@gmail.com" +
  "?subject=" + encodeURIComponent("Quero participar do PAC Indica") +
  "&body=" + encodeURIComponent(
    "Olá! Tenho interesse em indicar outro empresário e participar do programa PAC Indica. Meu nome é: ",
  );

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

          <a className="indica" href={INDICA_HREF}>
            <span className="indica-badge">PAC<br />Indica</span>
            <span className="indica-tx">
              <strong>Participe do programa PAC Indica</strong>
              <span>Indique outro empresário para a PAC e vocês dois são recompensados. Toque para saber como.</span>
            </span>
            <span className="indica-arrow" aria-hidden>→</span>
          </a>
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
