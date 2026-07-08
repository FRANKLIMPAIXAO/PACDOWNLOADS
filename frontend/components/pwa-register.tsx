"use client";

import { useEffect } from "react";

/** Registra o service worker (/sw.js) — habilita "instalar na tela inicial" e o
 * modo standalone (app-like) no celular. Silencioso: se falhar, o site funciona
 * igual. */
export function PwaRegister() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    const reg = () => navigator.serviceWorker.register("/sw.js").catch(() => {});
    // Registra após o load pra não competir com o primeiro render.
    if (document.readyState === "complete") reg();
    else window.addEventListener("load", reg, { once: true });
  }, []);
  return null;
}
