"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import {
  portalChamadaIce,
  portalChamadaIniciar,
  portalChamadaPendente,
  portalChamadaResponder,
  portalChamadaSinais,
  portalChamadaSinal,
} from "../lib/portal";

// Ligação de voz (WebRTC) no portal. Áudio P2P; sinalização proxied pelo backend.
// Dois sentidos: o escritório LIGA (cliente atende) e o cliente LIGA pro
// escritório. O botão "Ligar" fica no portal e chama `ligar()` via ref.
type Estado = "idle" | "tocando" | "chamando" | "conectando" | "em_chamada";
export type ChamadaHandle = { ligar: () => void };

function mmss(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const PortalChamada = forwardRef<ChamadaHandle>(function PortalChamada(_props, ref) {
  const [estado, setEstado] = useState<Estado>("idle");
  const [deNome, setDeNome] = useState("Escritório PAC");
  const [mudo, setMudo] = useState(false);
  const [segundos, setSegundos] = useState(0);
  const [erro, setErro] = useState<string | null>(null);

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
  // Filas de ICE: candidato remoto que chega antes do setRemoteDescription, e
  // candidato local que sai antes de termos o chamada_id (na ligação de saída).
  const remoteIceRef = useRef<RTCIceCandidateInit[]>([]);
  const localIceRef = useRef<RTCIceCandidateInit[]>([]);

  // --- Ringtone (destravado no 1º gesto — autoplay do celular) ---
  const garantirRingAudio = useCallback((): AudioContext | null => {
    if (typeof window === "undefined") return null;
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    if (!ringCtxRef.current) { try { ringCtxRef.current = new AC(); } catch { return null; } }
    const ctx = ringCtxRef.current;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }, []);

  const tocarRing = useCallback((comVibra: boolean) => {
    if (comVibra) { try { navigator.vibrate?.([300, 200, 300]); } catch { /* iOS */ } }
    const ctx = garantirRingAudio();
    if (!ctx) return;
    const t0 = ctx.currentTime;
    ([[480, 0], [620, 0.22]] as [number, number][]).forEach(([f, dt]) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t0 + dt);
      g.gain.exponentialRampToValueAtTime(0.2, t0 + dt + 0.02);
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
    remoteIceRef.current = []; localIceRef.current = [];
    setMudo(false);
    setEstado("idle");
  }, []);

  // Monta o RTCPeerConnection com os handlers comuns aos dois sentidos.
  const montarPc = useCallback(async (): Promise<RTCPeerConnection> => {
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
      if (!e.candidate) return;
      const cid = chamadaIdRef.current;
      const cand = e.candidate.toJSON();
      if (cid) portalChamadaSinal(cid, "ice", cand).catch(() => {});
      else localIceRef.current.push(cand); // ainda sem chamada_id (saída) → enfileira
    };
    pc.onconnectionstatechange = () => {
      const st = pc.connectionState;
      if (st === "connected") setEstado("em_chamada");
      else if (st === "failed" || st === "closed") encerrar(false);
    };
    return pc;
  }, [encerrar]);

  async function aplicarRemoteIce(pc: RTCPeerConnection, cand: RTCIceCandidateInit) {
    if (pc.currentRemoteDescription) {
      try { await pc.addIceCandidate(new RTCIceCandidate(cand)); } catch { /* ok */ }
    } else {
      remoteIceRef.current.push(cand); // chegou antes do remoto → enfileira
    }
  }

  // Polling dos sinais do OUTRO lado (answer/ice/bye) durante a chamada.
  const iniciarPolling = useCallback((id: string, pc: RTCPeerConnection, seqInicial: number) => {
    seqRef.current = seqInicial;
    sinaisTimerRef.current = setInterval(async () => {
      const cid = chamadaIdRef.current;
      if (!cid) return;
      try {
        const r = await portalChamadaSinais(cid, seqRef.current);
        for (const s of r.sinais || []) {
          seqRef.current = Math.max(seqRef.current, s.seq);
          if (s.tipo === "answer" && s.payload && !pc.currentRemoteDescription) {
            try {
              await pc.setRemoteDescription(new RTCSessionDescription(s.payload as RTCSessionDescriptionInit));
              for (const c of remoteIceRef.current) { try { await pc.addIceCandidate(new RTCIceCandidate(c)); } catch { /* ok */ } }
              remoteIceRef.current = [];
            } catch { /* ok */ }
          } else if (s.tipo === "ice" && s.payload) {
            await aplicarRemoteIce(pc, s.payload as RTCIceCandidateInit);
          } else if (s.tipo === "bye") { encerrar(false); return; }
        }
        if (r.status && ["encerrada", "recusada"].includes(r.status)) encerrar(false);
      } catch { /* ignora */ }
    }, 1000);
  }, [encerrar]);

  // ATENDER (chamada de ENTRADA — o escritório ligou).
  const atender = useCallback(async () => {
    const id = chamadaIdRef.current;
    const offer = offerRef.current;
    if (!id || !offer) return;
    setEstado("conectando");
    try {
      await portalChamadaResponder(id, true);
      const pc = await montarPc();
      await pc.setRemoteDescription(new RTCSessionDescription(offer));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await portalChamadaSinal(id, "answer", { type: answer.type, sdp: answer.sdp });
      iniciarPolling(id, pc, offerSeqRef.current);
    } catch {
      encerrar(true);
      setErro("Não consegui atender. Verifique a permissão do microfone.");
    }
  }, [montarPc, iniciarPolling, encerrar]);

  // LIGAR (chamada de SAÍDA — o cliente liga pro escritório).
  const ligar = useCallback(async () => {
    if (estadoRef.current !== "idle") return;
    setErro(null);
    localIceRef.current = []; remoteIceRef.current = [];
    setDeNome("Escritório PAC");
    setEstado("chamando");
    try {
      const pc = await montarPc();
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const r = await portalChamadaIniciar({ type: offer.type, sdp: offer.sdp });
      const cid = r.chamada_id;
      if (!cid) throw new Error("sem chamada_id");
      chamadaIdRef.current = cid;
      // Manda os ICE locais que já juntaram antes de termos o id.
      for (const c of localIceRef.current) portalChamadaSinal(cid, "ice", c).catch(() => {});
      localIceRef.current = [];
      iniciarPolling(cid, pc, 0);
    } catch {
      encerrar(false);
      setErro("Não consegui iniciar a ligação (microfone ou serviço indisponível).");
    }
  }, [montarPc, iniciarPolling, encerrar]);

  useImperativeHandle(ref, () => ({ ligar }), [ligar]);

  // Detector de chamada de ENTRADA (polling 3s enquanto ocioso).
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
      } catch { /* ignora */ }
    }, 3000);
    return () => { ativo = false; clearInterval(t); };
  }, []);

  // Cronômetro (em chamada).
  useEffect(() => {
    if (estado !== "em_chamada") { setSegundos(0); return; }
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [estado]);

  // Destrava o áudio no 1º gesto (pro ring tocar).
  useEffect(() => {
    const unlock = () => { garantirRingAudio(); };
    const evs: (keyof WindowEventMap)[] = ["pointerdown", "touchend", "click"];
    evs.forEach((e) => window.addEventListener(e, unlock, { once: true, passive: true }));
    return () => evs.forEach((e) => window.removeEventListener(e, unlock));
  }, [garantirRingAudio]);

  // Ring enquanto "tocando" (entrada, vibra) ou "chamando" (saída, sem vibrar).
  useEffect(() => {
    if (estado !== "tocando" && estado !== "chamando") {
      if (ringTimerRef.current) { clearInterval(ringTimerRef.current); ringTimerRef.current = null; }
      return;
    }
    const vibra = estado === "tocando";
    tocarRing(vibra);
    ringTimerRef.current = setInterval(() => tocarRing(vibra), 1700);
    return () => { if (ringTimerRef.current) { clearInterval(ringTimerRef.current); ringTimerRef.current = null; } };
  }, [estado, tocarRing]);

  // Erro some sozinho.
  useEffect(() => {
    if (!erro) return;
    const t = setTimeout(() => setErro(null), 5000);
    return () => clearTimeout(t);
  }, [erro]);

  // Limpeza ao desmontar.
  useEffect(() => () => encerrar(false), [encerrar]);

  function toggleMudo() {
    const mic = micRef.current;
    if (!mic) return;
    const novo = !mudo;
    mic.getAudioTracks().forEach((t) => { t.enabled = !novo; });
    setMudo(novo);
  }

  const conectando = estado === "conectando";
  const status =
    estado === "tocando" ? "Ligação recebida…"
      : estado === "chamando" ? "Chamando…"
        : conectando ? "Conectando…"
          : `Em chamada · ${mmss(segundos)}`;

  return (
    <>
      <audio ref={audioRef} autoPlay playsInline style={{ display: "none" }} />

      {erro && estado === "idle" ? (
        <div style={{ position: "fixed", left: 12, right: 12, bottom: 16, zIndex: 210, background: "#fdeaea", color: "#a32d2d", border: "1px solid #f3c2c2", borderRadius: 10, padding: "10px 14px", fontSize: 13.5, textAlign: "center" }}>
          {erro}
        </div>
      ) : null}

      {estado !== "idle" ? (
        <div style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(10,16,30,0.94)", padding: 24 }}>
          <div style={{ textAlign: "center", color: "#fff", display: "grid", gap: 6, maxWidth: 320 }}>
            <div style={{ fontSize: 52 }}>📞</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{deNome}</div>
            <div style={{ color: "#9fb0cc", fontSize: 14, marginBottom: 18 }}>{status}</div>

            {estado === "tocando" ? (
              <div style={{ display: "flex", gap: 28, justifyContent: "center" }}>
                <BotaoRedondo cor="#dc2626" rotulo="Recusar" onClick={() => { const id = chamadaIdRef.current; if (id) portalChamadaResponder(id, false).catch(() => {}); encerrar(false); }}>✕</BotaoRedondo>
                <BotaoRedondo cor="#16a34a" rotulo="Atender" onClick={atender}>📞</BotaoRedondo>
              </div>
            ) : estado === "chamando" ? (
              <div style={{ display: "flex", justifyContent: "center" }}>
                <BotaoRedondo cor="#dc2626" rotulo="Cancelar" onClick={() => encerrar(true)}>✕</BotaoRedondo>
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
});

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
