/* Service worker do PAC Portal (PWA).
 * CONSERVADOR de propósito — evita o trauma de "app velho em cache":
 *  - App/HTML e navegações: NETWORK-FIRST (sempre pega o código novo online;
 *    só cai no cache se estiver OFFLINE).
 *  - Estáticos com hash do Next (/_next/static/…) e imagens/fontes: cache-first
 *    (são imutáveis — o nome muda quando o conteúdo muda).
 *  - API e mídia de outra origem (api.pacgestao.com.br, Supabase Storage): NÃO
 *    intercepta (deixa o browser cuidar; nada de cachear resposta autenticada).
 * A EXISTÊNCIA deste fetch handler + o manifest + ícones = PWA instalável.
 */
const CACHE = "pac-portal-v4";

self.addEventListener("install", () => {
  self.skipWaiting();
});

// Web Push: notificação do portal no celular (tipo WhatsApp), mesmo com o app
// fechado. O payload vem do backend (PacGestão) disparado pelo webhook do PacChat.
self.addEventListener("push", (event) => {
  let data = { title: "PAC", body: "Você recebeu uma nova mensagem.", url: "/portal", tag: "pacchat" };
  try { if (event.data) data = { ...data, ...event.data.json() }; } catch { /* payload não-JSON */ }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      tag: data.tag || "pacchat",
      renotify: true,
      vibrate: [180, 80, 180],
      data: { url: data.url || "/portal" },
    }),
  );
});

// Tocar na notificação → foca a aba do portal se já aberta, senão abre.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const alvo = (event.notification.data && event.notification.data.url) || "/portal";
  event.waitUntil(
    (async () => {
      const abas = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const c of abas) {
        if (c.url.includes("/portal") && "focus" in c) return c.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(alvo);
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // não mexe em API/mídia externa

  const ehEstaticoImutavel =
    url.pathname.startsWith("/_next/static/") ||
    /\.(png|svg|ico|webmanifest|woff2?)$/.test(url.pathname);

  if (ehEstaticoImutavel) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        const res = await fetch(req);
        if (res.ok) {
          const cache = await caches.open(CACHE);
          cache.put(req, res.clone());
        }
        return res;
      })(),
    );
    return;
  }

  // Navegações/HTML e o resto do mesmo domínio: network-first (nunca serve app
  // velho quando online); offline cai no que estiver em cache, senão no /portal.
  event.respondWith(
    (async () => {
      try {
        return await fetch(req);
      } catch {
        const cached = await caches.match(req);
        return cached || (await caches.match("/portal")) || Response.error();
      }
    })(),
  );
});
