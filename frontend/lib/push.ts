// Web Push no portal do cliente — pede permissão, inscreve no navegador e manda
// a inscrição pro backend. O disparo real vem do backend (webhook do PacChat).
import { portalPushSubscribe, portalVapidKey } from "./portal";

export type EstadoPush = "granted" | "denied" | "default" | "unsupported";

function suportado(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function estadoNotificacoes(): EstadoPush {
  if (!suportado()) return "unsupported";
  return Notification.permission as EstadoPush;
}

// base64url (VAPID) → Uint8Array (formato exigido por applicationServerKey).
function base64urlParaBytes(base64: string): Uint8Array {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

/**
 * Ativa as notificações: pede permissão, inscreve no push e registra no backend.
 * `silencioso` = só re-registra se a permissão JÁ foi concedida (não abre prompt).
 * Retorna ok + motivo (pra mostrar ao usuário quando falha).
 */
export async function ativarNotificacoes(silencioso = false): Promise<{ ok: boolean; motivo?: string }> {
  if (!suportado()) return { ok: false, motivo: "Este navegador não suporta notificações." };
  const jaConcedida = Notification.permission === "granted";
  if (silencioso && !jaConcedida) return { ok: false, motivo: "sem permissão" };

  let publicKey: string | null;
  try {
    publicKey = (await portalVapidKey()).public_key;
  } catch {
    return { ok: false, motivo: "Falha ao falar com o servidor." };
  }
  if (!publicKey) return { ok: false, motivo: "Notificações ainda não estão configuradas no servidor." };

  if (!jaConcedida) {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      return { ok: false, motivo: perm === "denied" ? "Você bloqueou as notificações. Libere nas configurações do site." : "Permissão não concedida." };
    }
  }

  let reg: ServiceWorkerRegistration;
  try {
    reg = await navigator.serviceWorker.ready;
  } catch {
    return { ok: false, motivo: "Service worker não pronto." };
  }

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    try {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64urlParaBytes(publicKey),
      });
    } catch {
      // iOS: só permite push em PWA INSTALADO (adicionado à tela inicial).
      return { ok: false, motivo: "Não consegui ativar. No iPhone, instale o app na tela inicial primeiro." };
    }
  }

  const json = sub.toJSON();
  const keys = json.keys || ({} as Record<string, string>);
  if (!keys.p256dh || !keys.auth) return { ok: false, motivo: "Inscrição incompleta." };
  try {
    await portalPushSubscribe({ endpoint: sub.endpoint, p256dh: keys.p256dh, auth: keys.auth });
  } catch {
    return { ok: false, motivo: "Falha ao registrar no servidor." };
  }
  return { ok: true };
}
