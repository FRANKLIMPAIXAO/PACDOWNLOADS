"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  portalChamadaIce,
  portalChamadaPendente,
  portalChamadaResponder,
  portalChamadaSinais,
  portalChamadaSinal,
} from "../lib/portal";

// Gerenciador da LIGAÇÃO DE VOZ (WebRTC) no portal. O áudio vai P2P entre os
// navegadores; a sinalização passa pelo backend do PacGestão (proxy do PacChat).
// v1: o escritório liga, o cliente atende (com o portal ABERTO). Detecta a
// chamada entrante por polling e mostra uma tela de chamada por cima de tudo.
type Estado = "idle" | "tocando" | "conectando" | "em_chamada";

function mmss(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function PortalChamada() {
  const [estado, setEstado] = useState<Estado>("idle");
  const [deNome, setDeNome] = useState("Escritório PAC");
  const [mudo, setMudo] = useState(false);
  const [segundos, setSegundos] = useState(0);
  // Toque de "chamando" (ringtone) enquanto a chamada entra.
  const ringCtxRef = useRef<AudioContext | null>(null);
  const ringTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const chamadaIdRef = useRef<string | null>(null);
  const offerRef = useRef<RTCSessionDescriptionInit | null>(null);
  const offerSeqRef = useRef(0);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const micRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const seqRef = useRef(0);
  const sinaisTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const estadoRef = useRef<Estado>("idle");
  estadoRef.current = estado;

  // AudioContext do ring (destravado por gesto — política de autoplay do celular).
  const garantirRingAudio = useCallback((): AudioContext | null => {
    if (typeof window === "undefined") return null;
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    if (!ringCtxRef.current) { try { ringCtxRef.current = new AC(); } catch { return null; } }
    const ctx = ringCtxRef.current;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }, []);

  // Toque de telefone (dois bipes) + vibração — repetido enquanto "tocando".
  const tocarRing = useCallback(() => {
    try { navigator.vibrate?.([300, 200, 300]); } catch { /* iOS não tem */ }
    const ctx = garantirRingAudio();
    if (!ctx) return;
    const t0 = ctx.currentTime;
    ([[480, 0], [620, 0.22]] as [number, number][]).forEach(([f, dt]) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t0 + dt);
      g.gain.exponentialRampToValueAtTime(0.22, t0 + dt + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.2);
      o.connect(g); g.connect(ctx.destination);
      o.start(t0 + dt); o.stop(t0 + dt + 0.22);
    });
  }, [garantirRingAudio]);

  const encerrar = useCallback((mandarBye: boolean) => {
    if (sinaisTimerRef.current) { clearInterval(sinaisTimerRef.current); sinaisTimerRef.current = null; }
    const id = chamadaIdRef.current;
    if (mandarBye && id) portalChamadaSinal(id, "bye").catch(() => {});
    try { pcRef.current?.close(); } catch { /* ok */ }
    pcRef.current = null;
    micRef.current?.getTracks().forEach((t) => t.stop());
    micRef.current = null;
    if (audioRef.current) audioRef.current.srcObject = null;
    chamadaIdRef.current = null; offerRef.current = null; seqRef.current = 0;
    setMudo(false);
    setEstado("idle");
  }, []);

  // Detector de chamada entrante: polling a cada 3s enquanto está ocioso.
  useEffect(() => {
    let ativo = true;
    const t = setInterval(async () => {
      if (estadoRef.current !== "idle") return;
      try {
        const r = await portalChamadaPendente();
        if (!ativo || estadoRef.current !== "idle") return;
        if (r.chamada && r.offer) {
          chamadaIdRef.current = r.chamada.id;
          offerRef.current = r.offer;
          offerSeqRef.current = r.offer_seq ?? 0;
          setDeNome(r.chamada.de_nome || "Escritório PAC");
          setEstado("tocando");
        }
      } catch { /* PacChat fora / sem token — ignora */ }
    }, 3000);
    return () => { ativo = false; clearInterval(t); };
  }, []);

  // Cronômetro da chamada.
  useEffect(() => {
    if (estado !== "em_chamada") { setSegundos(0); return; }
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [estado]);

  // Limpeza ao desmontar.
  useEffect(() => () => encerrar(false), [encerrar]);

  // Destrava o áudio no 1º gesto do usuário (pro ring conseguir tocar depois).
  useEffect(() => {
    const unlock = () => { garantirRingAudio(); };
    const evs: (keyof WindowEventMap)[] = ["pointerdown", "touchend", "click"];
    evs.forEach((e) => window.addEventListener(e, unlock, { once: true, passive: true }));
    return () => evs.forEach((e) => window.removeEventListener(e, unlock));
  }, [garantirRingAudio]);

  // Toca o ring (repete) enquanto a chamada está "tocando".
  useEffect(() => {
    if (estado !== "tocando") {
      if (ringTimerRef.current) { clearInterval(ringTimerRef.current); ringTimerRef.current = null; }
      return;
    }
    tocarRing();
    ringTimerRef.current = setInterval(tocarRing, 1700);
    return () => { if (ringTimerRef.current) { clearInterval(ringTimerRef.current); ringTimerRef.current = null; } };
  }, [estado, tocarRing]);

  async function atender() {
    const id = chamadaIdRef.current;
    const offer = offerRef.current;
    if (!id || !offer) return;
    setEstado("conectando");
    try {
      await portalChamadaResponder(id, true);
      const { iceServers } = await portalChamadaIce();
      const pc = new RTCPeerConnection({ iceServers });
      pcRef.current = pc;

      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      micRef.current = mic;
      mic.getTracks().forEach((t) => pc.addTrack(t, mic));

      pc.ontrack = (e) => {
        if (audioRef.current) {
          audioRef.current.srcObject = e.streams[0];
          audioRef.current.muted = false;
          audioRef.current.volume = 1;
          audioRef.current.play().catch(() => {});
        }
      };
      pc.onicecandidate = (e) => {
        if (e.candidate) portalChamadaSinal(id, "ice", e.candidate.toJSON()).catch(() => {});
      };
      pc.onconnectionstatechange = () => {
        const st = pc.connectionState;
        if (st === "connected") setEstado("em_chamada");
        else if (st === "failed" || st === "closed" || st === "disconnected") encerrar(false);
      };

      await pc.setRemoteDescription(new RTCSessionDescription(offer));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await portalChamadaSinal(id, "answer", { type: answer.type, sdp: answer.sdp });

      // Polling dos sinais do escritório (ice/bye) — começa após o offer.
      seqRef.current = offerSeqRef.current;
      sinaisTimerRef.current = setInterval(async () => {
        const cid = chamadaIdRef.current;
        if (!cid) return;
        try {
          const r = await portalChamadaSinais(cid, seqRef.current);
          for (const s of r.sinais || []) {
            seqRef.current = Math.max(seqRef.current, s.seq);
            if (s.tipo === "ice" && s.payload) {
              try { await pc.addIceCandidate(new RTCIceCandidate(s.payload as RTCIceCandidateInit)); } catch { /* ok */ }
            }
            if (s.tipo === "bye") { encerrar(false); return; }
          }
          if (r.status && ["encerrada", "recusada"].includes(r.status)) encerrar(false);
        } catch { /* ignora */ }
      }, 1000);
    } catch {
      encerrar(true);
      alert("Não consegui iniciar a ligação. Verifique a permissão do microfone.");
    }
  }

  function recusar() {
    const id = chamadaIdRef.current;
    if (id) portalChamadaResponder(id, false).catch(() => {});
    encerrar(false);
  }

  function toggleMudo() {
    const mic = micRef.current;
    if (!mic) return;
    const novo = !mudo;
    mic.getAudioTracks().forEach((t) => { t.enabled = !novo; });
    setMudo(novo);
  }

  const emChamada = estado === "em_chamada";
  const conectando = estado === "conectando";

  return (
    <>
      {/* Áudio remoto (sempre montado; recebe o srcObject quando conecta) */}
      <audio ref={audioRef} autoPlay playsInline style={{ display: "none" }} />

      {estado !== "idle" ? (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "center",
            justifyContent: "center", background: "rgba(10,16,30,0.94)", padding: 24,
          }}
        >
          <div style={{ textAlign: "center", color: "#fff", display: "grid", gap: 6, maxWidth: 320 }}>
            <div style={{ fontSize: 52 }}>📞</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{deNome}</div>
            <div style={{ color: "#9fb0cc", fontSize: 14, marginBottom: 18 }}>
              {estado === "tocando" ? "Ligação recebida…" : conectando ? "Conectando…" : `Em chamada · ${mmss(segundos)}`}
            </div>

            {estado === "tocando" ? (
              <div style={{ display: "flex", gap: 28, justifyContent: "center" }}>
                <BotaoRedondo cor="#dc2626" rotulo="Recusar" onClick={recusar}>✕</BotaoRedondo>
                <BotaoRedondo cor="#16a34a" rotulo="Atender" onClick={atender}>📞</BotaoRedondo>
              </div>
            ) : (
              <div style={{ display: "flex", gap: 24, justifyContent: "center" }}>
                <BotaoRedondo cor={mudo ? "#6b7280" : "#334155"} rotulo={mudo ? "Sem som" : "Mudo"} onClick={toggleMudo} disabled={conectando}>
                  {mudo ? "🔇" : "🎙️"}
                </BotaoRedondo>
                <BotaoRedondo cor="#dc2626" rotulo="Encerrar" onClick={() => encerrar(true)}>✕</BotaoRedondo>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

function BotaoRedondo({
  children, cor, rotulo, onClick, disabled,
}: { children: React.ReactNode; cor: string; rotulo: string; onClick: () => void; disabled?: boolean }) {
  return (
    <div style={{ display: "grid", gap: 6, justifyItems: "center" }}>
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        style={{
          width: 64, height: 64, borderRadius: "50%", border: "none", cursor: disabled ? "default" : "pointer",
          background: cor, color: "#fff", fontSize: 26, opacity: disabled ? 0.5 : 1,
          boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
        }}
      >
        {children}
      </button>
      <span style={{ fontSize: 12, color: "#c4d0e4" }}>{rotulo}</span>
    </div>
  );
}
