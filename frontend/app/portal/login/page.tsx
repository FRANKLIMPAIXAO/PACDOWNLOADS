"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../../lib/api";
import { portalLogin } from "../../../lib/portal";

const NAVY = "#16294d";
const ORANGE = "#ec8b1c";
const GRAY = "#6b7488";

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
    <div className="pac-login">
      <div className="pac-login-card">
        <div style={{ textAlign: "center", marginBottom: 22 }}>
          <img src="/pac-logo.svg" alt="PAC Inteligência Tributária" style={{ height: 46, marginBottom: 14 }} />
          <h2 style={{ margin: 0, color: NAVY, fontSize: 20 }}>Portal do Cliente</h2>
          <p style={{ margin: "4px 0 0", color: GRAY, fontSize: 13 }}>Acesse as notas da sua empresa</p>
        </div>
        <form onSubmit={handleSubmit}>
          <label>E-mail
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
          </label>
          <label>Senha
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          {erro ? <p className="pac-login-erro">{erro}</p> : null}
          <button type="submit" disabled={busy}>{busy ? "Entrando..." : "Entrar"}</button>
        </form>
      </div>

      <style jsx>{`
        .pac-login { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f5f7fa;
          font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif; }
        .pac-login-card { width: 100%; max-width: 380px; background: #fff; border: 1px solid #e6eaf0;
          border-radius: 14px; padding: 30px 28px; box-shadow: 0 10px 30px rgba(22,41,77,0.08); }
        .pac-login form { display: grid; gap: 14px; }
        .pac-login label { display: grid; gap: 6px; font-size: 13px; color: ${GRAY}; }
        .pac-login input { appearance: none; border: 1px solid #d8dee8; border-radius: 9px; padding: 11px 13px;
          font: inherit; font-size: 15px; background: #fff; color: #1b2333; }
        .pac-login input:focus { outline: none; border-color: ${ORANGE}; box-shadow: 0 0 0 3px rgba(236,139,28,0.18); }
        .pac-login button { appearance: none; border: none; background: ${ORANGE}; color: #fff; font: inherit;
          font-size: 15px; font-weight: 500; padding: 12px; border-radius: 9px; cursor: pointer; margin-top: 4px; }
        .pac-login button:hover:not(:disabled) { filter: brightness(1.05); }
        .pac-login button:disabled { opacity: .6; cursor: not-allowed; }
        .pac-login-erro { margin: 0; color: #a32d2d; font-size: 13px; background: #fdeaea; border: 1px solid #f3c2c2;
          padding: 9px 12px; border-radius: 8px; }
      `}</style>
    </div>
  );
}
