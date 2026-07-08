"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "../../lib/api";
import {
  getPortalToken,
  portalAtualizarGuia,
  portalBaixarArquivo,
  portalBaixarCertidao,
  portalBaixarDctfweb,
  portalBaixarDocEscritorio,
  portalBaixarGuia,
  portalBaixarZip,
  portalCertidoes,
  portalDashboard,
  portalDctfweb,
  portalDocumentos,
  portalDocumentosEscritorio,
  portalDocumentosEmpresa,
  portalGuias,
  portalLogout,
  portalManifestarDoc,
  portalManifestarLote,
  portalMe,
  portalMensagens,
  portalMensagensNaoLidas,
  portalEnviarMensagem,
  portalEnviarArquivo,
  portalPushTest,
  portalTrocarEmpresa,
  portalResumo,
  portalSyncGuias,
  portalUploadSaidas,
  portalStatusUploadSaidas,
  type ChatMensagem,
  type DocEscritorio,
  type DocsEscritorio,
  type DocEmpresa,
  type DocsEmpresa,
  type CertificadoEmpresa,
  type PortalCertidao,
  type PortalDashboard,
  type PortalDctfweb,
  type PortalDocumento,
  type PortalGuiaDAS,
  type PortalMe,
  type PortalResumo,
  type RankItem,
  type UploadSaidasResp,
} from "../../lib/portal";
import { PortalAdmissao } from "../../components/portal-admissao";
import { ChatThread } from "../../components/chat-thread";
import { PortalChamada } from "../../components/portal-chamada";
import { ativarNotificacoes, estadoNotificacoes, type EstadoPush } from "../../lib/push";

// ---- Marca PAC ----
const NAVY = "#16294d";
const NAVY_2 = "#1f3563";
const ORANGE = "#ec8b1c";
const ORANGE_TX = "#b96a0c"; // laranja legível sobre branco
const GREEN = "#1d9e75";
const BLUE = "#2b6cb0";
const GRAY = "#6b7488";
const RED = "#c0392b";

const MAX_LINHAS = 50; // tabela enxuta dentro de "Minhas notas"

function brl(v: number | string | null | undefined): string {
  const n = typeof v === "string" ? Number(v) : v ?? 0;
  return (n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function dataBR(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}
function hoje(): string { return new Date().toISOString().slice(0, 10); }
function trintaDiasAtras(): string {
  const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10);
}
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
function mesLabel(mes: string): string {
  const m = Number((mes || "").split("-")[1]); return MESES_ABREV[m - 1] || mes;
}

function tipoEscritorio(tipo: string): { label: string; cor: string } {
  switch (tipo) {
    case "guia": return { label: "Guia / imposto", cor: ORANGE_TX };
    case "relatorio": return { label: "Relatório", cor: BLUE };
    case "comunicado": return { label: "Comunicado", cor: NAVY };
    default: return { label: "Documento", cor: GRAY };
  }
}

function tipoDocEmpresa(tipo: string): { label: string; cor: string } {
  switch (tipo) {
    case "contrato":
    case "contrato_social": return { label: "Contrato social", cor: NAVY };
    case "alteracao_contratual": return { label: "Alteração contratual", cor: NAVY };
    case "estatuto": return { label: "Estatuto", cor: NAVY };
    case "ata": return { label: "Ata", cor: NAVY };
    case "alvara": return { label: "Alvará", cor: BLUE };
    case "licenca": return { label: "Licença", cor: BLUE };
    case "certificado": return { label: "Certificado digital", cor: ORANGE_TX };
    case "procuracao": return { label: "Procuração", cor: GREEN };
    case "inscricao": return { label: "Inscrição", cor: BLUE };
    case "cartao_cnpj": return { label: "Cartão CNPJ", cor: BLUE };
    default: return { label: "Documento", cor: GRAY };
  }
}

// Cor/rótulo do vencimento do certificado digital.
function statusCert(c: CertificadoEmpresa): { label: string; cor: string; urgente: boolean } {
  if (c.status === "vencido") {
    const d = Math.abs(c.dias_para_vencer);
    return { label: `Vencido há ${d} dia${d === 1 ? "" : "s"}`, cor: RED, urgente: true };
  }
  if (c.status === "a_vencer") {
    return { label: `Vence em ${c.dias_para_vencer} dia${c.dias_para_vencer === 1 ? "" : "s"}`, cor: ORANGE_TX, urgente: true };
  }
  return { label: `Válido — vence em ${c.dias_para_vencer} dias`, cor: GREEN, urgente: false };
}

function diasDesde(iso: string | null): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? 0 : Math.floor((Date.now() - t) / 86400000);
}

type StatusNota = { label: string; cor: string; baixar: boolean; manifestar: boolean; aguardando: boolean };
function statusNota(doc: PortalDocumento): StatusNota {
  if (doc.origem !== "recebida" || doc.status === "baixado") {
    return { label: "Disponível", cor: GREEN, baixar: true, manifestar: false, aguardando: false };
  }
  // Manifestação (Ciência da Operação) SÓ existe pra NF-e (modelo 55). NFS-e e CT-e não manifestam.
  if (doc.tipo_documento !== "NFE") {
    return { label: "Disponível", cor: GREEN, baixar: true, manifestar: false, aguardando: false };
  }
  if (doc.status === "manifestado") {
    return { label: "Manifestada", cor: BLUE, baixar: false, manifestar: false, aguardando: true };
  }
  if (diasDesde(doc.data_emissao) > 90) {
    return { label: "Fora do prazo", cor: GRAY, baixar: false, manifestar: false, aguardando: false };
  }
  return { label: "A manifestar", cor: ORANGE_TX, baixar: false, manifestar: true, aguardando: false };
}

// ---- Ícones (SVG inline, estilo linha — herdam cor/tamanho) ----
const ICONS: Record<string, React.ReactNode> = {
  home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></>,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M9 13h6M9 17h4" /></>,
  chart: <><path d="M4 20V10M10 20V4M16 20v-7" /><path d="M2 20h20" /></>,
  folder: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></>,
  check: <><path d="M9 11l3 3 9-9" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>,
  logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></>,
  bell: <><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></>,
  users: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
  truck: <><path d="M1 3h15v13H1zM16 8h4l3 3v5h-7z" /><circle cx="5.5" cy="18.5" r="2" /><circle cx="18.5" cy="18.5" r="2" /></>,
  receipt: <><path d="M6 2v20l2-1.5L10 22l2-1.5L14 22l2-1.5L18 22V2l-2 1.5L14 2l-2 1.5L10 2 8 3.5z" /><path d="M9 8h6M9 12h6" /></>,
  shield: <><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></>,
  chat: <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /><path d="M8 9h8M8 13h5" /></>,
};
function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }} aria-hidden="true">{ICONS[name]}</svg>
  );
}

function pill(label: string, cor: string) {
  return <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 6, border: `1px solid ${cor}`, color: cor, whiteSpace: "nowrap" }}>{label}</span>;
}

function situacaoGuia(s: string): { label: string; cor: string } {
  switch (s) {
    case "paga": return { label: "Paga", cor: GREEN };
    case "atrasada": return { label: "Atrasada", cor: RED };
    case "parcialmente_paga": return { label: "Parcial", cor: ORANGE_TX };
    default: return { label: "Em aberto", cor: BLUE };
  }
}
function statusCnd(c: PortalCertidao): { label: string; cor: string } {
  // Regularidade tem PRIORIDADE sobre a data: uma SITFIS dentro da validade mas
  // com pendência NÃO é "válida". `verificar` = SITFIS que não deu pra ler.
  if (c.status === "VENCIDA") return { label: "Vencida", cor: RED };
  if (c.situacao_fiscal === "pendencias") return { label: "Com pendências", cor: RED };
  if (c.situacao_fiscal === "verificar") return { label: "Verificar", cor: GRAY };
  if (c.status === "A_VENCER") return { label: "A vencer", cor: ORANGE_TX };
  if (c.status === "VALIDA") return { label: c.situacao_fiscal === "regular" ? "Regular" : "Válida", cor: GREEN };
  return { label: "—", cor: GRAY };
}

/** Ranking horizontal (clientes / fornecedores). */
function Ranking({ items, cor }: { items: RankItem[]; cor: string }) {
  if (!items.length) return <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>Sem dados no período.</p>;
  const max = Math.max(...items.map((i) => i.valor), 1);
  return (
    <div>
      {items.map((i, idx) => (
        <div key={`${i.nome}-${idx}`} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, marginBottom: 4 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.nome}</span>
            <strong style={{ flexShrink: 0, fontWeight: 500 }}>{brl(i.valor)}</strong>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "#eef1f5" }}>
            <div style={{ height: 6, borderRadius: 3, width: `${Math.round((i.valor / max) * 100)}%`, background: cor }} />
          </div>
        </div>
      ))}
    </div>
  );
}

type View = "home" | "notas" | "documentos" | "empresa" | "admissao" | "indicadores" | "manifestar" | "guias" | "certidoes" | "conversa";

export default function PortalPage() {
  const router = useRouter();
  const [view, setView] = useState<View>("home");
  const [me, setMe] = useState<PortalMe | null>(null);
  const [resumo, setResumo] = useState<PortalResumo | null>(null);
  const [dash, setDash] = useState<PortalDashboard | null>(null);
  const [escritorio, setEscritorio] = useState<DocsEscritorio | null>(null);
  const [docsEmpresa, setDocsEmpresa] = useState<DocsEmpresa | null>(null);
  const [certidoes, setCertidoes] = useState<PortalCertidao[] | null>(null);
  const [guias, setGuias] = useState<PortalGuiaDAS[]>([]);
  const [dctfweb, setDctfweb] = useState<PortalDctfweb[]>([]);
  const [valorRecalc, setValorRecalc] = useState(5);
  const [guiaBusy, setGuiaBusy] = useState<string | null>(null);
  const [docs, setDocs] = useState<PortalDocumento[]>([]);
  const [tipo, setTipo] = useState("");
  const [origem, setOrigem] = useState(""); // "" | "emitida" | "recebida"
  const [dataInicio, setDataInicio] = useState(trintaDiasAtras());
  const [dataFim, setDataFim] = useState(hoje());
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [baixando, setBaixando] = useState<string | null>(null);
  const [zipBusy, setZipBusy] = useState(false);
  const [manifBusy, setManifBusy] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadSaidasResp | null>(null);
  const [uploadProg, setUploadProg] = useState<{ feitas: number; total: number } | null>(null);
  // Conversa com o escritório
  const [mensagens, setMensagens] = useState<ChatMensagem[]>([]);
  const [chatNaoLidas, setChatNaoLidas] = useState(0);
  const [chatLoading, setChatLoading] = useState(false);
  // Mobile: menu-gaveta + altura do chat ocupando ~a tela toda no celular.
  const [menuAberto, setMenuAberto] = useState(false);
  const [chatAltura, setChatAltura] = useState(540);
  // Notificação de sistema (Web Push)
  const [pushStatus, setPushStatus] = useState<EstadoPush>("default");
  const [pushBusy, setPushBusy] = useState(false);
  // Campainha: refs pra detectar mensagem NOVA da PAC entre um polling e outro.
  const audioCtxRef = useRef<AudioContext | null>(null);
  const prevNaoLidasRef = useRef<number | null>(null);
  const lastEscritorioIdRef = useRef<string | number | null>(null);

  // Garante um AudioContext "running" (destravado). No celular ele nasce
  // suspenso e só liga a partir de um gesto do usuário (ver efeito abaixo).
  const garantirAudio = useCallback((): AudioContext | null => {
    if (typeof window === "undefined") return null;
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    if (!audioCtxRef.current) { try { audioCtxRef.current = new AC(); } catch { return null; } }
    const ctx = audioCtxRef.current;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }, []);

  // "Ding-dong" curto via Web Audio (sem arquivo, CSP-safe) + vibração no Android.
  const tocarSino = useCallback(() => {
    try { navigator.vibrate?.(180); } catch { /* iOS não tem vibrate */ }
    try {
      const ctx = garantirAudio();
      if (!ctx) return;
      const t0 = ctx.currentTime;
      ([[880, 0], [1174.7, 0.13]] as [number, number][]).forEach(([freq, dt]) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, t0 + dt);
        gain.gain.exponentialRampToValueAtTime(0.34, t0 + dt + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.3);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(t0 + dt); osc.stop(t0 + dt + 0.32);
      });
    } catch { /* som é bônus — nunca quebra */ }
  }, [garantirAudio]);

  // DESTRAVA o áudio no 1º gesto do usuário (política de autoplay do celular).
  // Sem isso, o bip de mensagem nova não toca no iOS/Android (contexto suspenso).
  useEffect(() => {
    const desbloquear = () => {
      const ctx = garantirAudio();
      if (!ctx) return;
      try {
        const o = ctx.createOscillator(); const g = ctx.createGain();
        g.gain.value = 0; o.connect(g); g.connect(ctx.destination);
        o.start(); o.stop(ctx.currentTime + 0.01); // tick mudo só pra "ligar"
      } catch { /* ok */ }
    };
    const evs: (keyof WindowEventMap)[] = ["pointerdown", "touchend", "keydown", "click"];
    evs.forEach((e) => window.addEventListener(e, desbloquear, { once: true, passive: true }));
    return () => evs.forEach((e) => window.removeEventListener(e, desbloquear));
  }, [garantirAudio]);

  const carregarMensagens = useCallback((comSpinner = false) => {
    if (comSpinner) setChatLoading(true);
    portalMensagens()
      .then((r) => {
        setMensagens(r.mensagens);
        setChatNaoLidas(0);
        prevNaoLidasRef.current = 0; // abriu/leu a conversa → zera a base do sino
        // Última mensagem da PAC. Se mudou num POLL (não na abertura), toca o sino.
        const ultEsc = [...r.mensagens].reverse().find((m) => m.autor === "escritorio");
        const novoId = ultEsc ? ultEsc.id : null;
        if (!comSpinner && lastEscritorioIdRef.current !== null && novoId !== null && novoId !== lastEscritorioIdRef.current) {
          tocarSino();
        }
        lastEscritorioIdRef.current = novoId;
      })
      .catch(() => { /* seção opcional */ })
      .finally(() => { if (comSpinner) setChatLoading(false); });
  }, [tocarSino]);

  // Poll do não-lido FORA da conversa: se subiu, chegou mensagem → toca o sino.
  const checarNaoLidas = useCallback(() => {
    portalMensagensNaoLidas()
      .then((r) => {
        if (prevNaoLidasRef.current !== null && r.total > prevNaoLidasRef.current) tocarSino();
        prevNaoLidasRef.current = r.total;
        setChatNaoLidas(r.total);
      })
      .catch(() => { /* opcional */ });
  }, [tocarSino]);

  const carregarEscritorio = useCallback(() => {
    portalDocumentosEscritorio().then(setEscritorio).catch(() => { /* seção é opcional */ });
  }, []);

  const carregarEmpresa = useCallback(() => {
    portalDocumentosEmpresa().then(setDocsEmpresa).catch(() => { /* seção é opcional */ });
  }, []);

  const carregarFiscal = useCallback(() => {
    portalCertidoes().then((r) => setCertidoes(r.certidoes)).catch(() => setCertidoes([]));
    portalGuias().then((r) => { setGuias(r.guias); setValorRecalc(r.valor_recalculo_extra); }).catch(() => { /* opcional */ });
    portalDctfweb().then((r) => setDctfweb(r.guias)).catch(() => { /* opcional */ });
  }, []);

  useEffect(() => {
    if (!getPortalToken()) { router.replace("/portal/login"); return; }
    portalMe().then(setMe).catch(() => { portalLogout(); router.replace("/portal/login"); });
    carregarEscritorio();
    carregarEmpresa();
    carregarFiscal();
    checarNaoLidas();
  }, [router, carregarEscritorio, carregarEmpresa, carregarFiscal, checarNaoLidas]);

  // Chat quase em tela cheia no celular (acompanha o teclado ao abrir); altura
  // confortável fixa no desktop.
  useEffect(() => {
    function calcAltura() {
      const h = window.innerHeight, w = window.innerWidth;
      setChatAltura(w <= 820 ? Math.max(360, h - 150) : 560);
    }
    calcAltura();
    window.addEventListener("resize", calcAltura);
    return () => window.removeEventListener("resize", calcAltura);
  }, []);

  // Push: lê o estado da permissão e, se JÁ concedida, re-registra a inscrição
  // em silêncio (mantém o endpoint atualizado, sem abrir prompt).
  useEffect(() => {
    setPushStatus(estadoNotificacoes());
    ativarNotificacoes(true).catch(() => { /* silencioso */ });
  }, []);

  async function ativarPush() {
    setPushBusy(true); setAviso(null); setErro(null);
    try {
      const r = await ativarNotificacoes(false);
      setPushStatus(estadoNotificacoes());
      if (r.ok) setAviso("🔔 Notificações ativadas! Você será avisado no celular quando o escritório responder.");
      else setErro(r.motivo || "Não consegui ativar as notificações.");
    } finally {
      setPushBusy(false);
    }
  }

  async function testarPush() {
    setPushBusy(true); setAviso(null); setErro(null);
    try {
      const r = await portalPushTest();
      if (r.ok) setAviso("Enviei uma notificação de teste! FECHE o app agora — ela deve aparecer em alguns segundos. 📲");
      else setErro(r.motivo || "Não consegui enviar o teste.");
    } catch {
      setErro("Falha ao enviar o teste.");
    } finally {
      setPushBusy(false);
    }
  }

  // Abriu a conversa → carrega e zera o badge. Fora dela, faz polling do não-lido
  // (a cada 15s) — se subir, toca a campainha.
  useEffect(() => {
    if (view === "conversa") { carregarMensagens(true); return; }
    const t = setInterval(checarNaoLidas, 15000);
    return () => clearInterval(t);
  }, [view, carregarMensagens, checarNaoLidas]);

  // Conversa aberta: puxa mensagens novas a cada 6s (bip toca quase na hora).
  useEffect(() => {
    if (view !== "conversa") return;
    const t = setInterval(() => carregarMensagens(false), 6000);
    return () => clearInterval(t);
  }, [view, carregarMensagens]);

  async function enviarMensagemPortal(corpo: string) {
    await portalEnviarMensagem(corpo);
    carregarMensagens(false);
  }

  async function enviarArquivoPortal(file: Blob, nome: string, texto?: string) {
    await portalEnviarArquivo(file, nome, texto);
    carregarMensagens(false);
  }

  async function recalcularGuia(g: PortalGuiaDAS, confirmar = false) {
    setGuiaBusy(`recalc-${g.id}`); setErro(null); setAviso(null);
    try {
      const r = await portalAtualizarGuia(g.id, confirmar);
      if (r.cobranca_necessaria) {
        const ok = typeof window !== "undefined"
          && window.confirm(r.mensagem || `Este recálculo tem custo de R$ ${(r.valor ?? valorRecalc).toFixed(2)}. Deseja continuar?`);
        if (ok) { await recalcularGuia(g, true); }
        return;
      }
      setAviso(r.mensagem || "Guia atualizada gerada!");
      carregarFiscal();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao recalcular a guia.");
    } finally { setGuiaBusy(null); }
  }

  async function baixarGuia(g: PortalGuiaDAS) {
    setGuiaBusy(`pdf-${g.id}`); setErro(null);
    try { await portalBaixarGuia(g.id); }
    catch (err) { setErro(err instanceof ApiError ? err.message : "Falha ao baixar o PDF da guia."); }
    finally { setGuiaBusy(null); }
  }

  async function buscarGuias(confirmar = false) {
    setGuiaBusy("sync"); setErro(null); setAviso(null);
    try {
      const r = await portalSyncGuias(undefined, confirmar);
      if (r.cobranca_necessaria) {
        const ok = typeof window !== "undefined"
          && window.confirm(r.mensagem || `Esta busca tem custo de R$ ${(r.valor ?? valorRecalc).toFixed(2)}. Continuar?`);
        if (ok) { await buscarGuias(true); }
        return;
      }
      if (r.ok === false) { setErro(r.mensagem || "Não foi possível buscar as guias."); return; }
      setAviso(r.mensagem || `Busca concluída — ${r.novas ?? 0} nova(s), ${r.atualizadas ?? 0} atualizada(s).`);
      carregarFiscal();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao buscar as guias.");
    } finally { setGuiaBusy(null); }
  }

  async function baixarCertidao(c: PortalCertidao) {
    setBaixando(`cnd-${c.id}`); setErro(null);
    try { await portalBaixarCertidao(c.id); }
    catch (err) { setErro(err instanceof ApiError ? err.message : "Falha ao baixar a certidão."); }
    finally { setBaixando(null); }
  }

  async function baixarDctfweb(d: PortalDctfweb) {
    setGuiaBusy(`dctf-${d.id}`); setErro(null);
    try { await portalBaixarDctfweb(d.id); }
    catch (err) { setErro(err instanceof ApiError ? err.message : "Falha ao baixar o DARF DCTFWeb."); }
    finally { setGuiaBusy(null); }
  }

  async function baixarDocEscritorio(d: DocEscritorio) {
    setBaixando(`esc-${d.id}`); setErro(null);
    try {
      await portalBaixarDocEscritorio(d.id, d.nome_arquivo || undefined);
      carregarEscritorio();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao baixar o documento.");
    } finally { setBaixando(null); }
  }

  async function baixarDocEmpresa(d: DocEmpresa) {
    setBaixando(`emp-${d.id}`); setErro(null);
    try {
      await portalBaixarDocEscritorio(d.id, d.nome_arquivo || undefined);
      carregarEmpresa(); // re-busca pra atualizar o "lido"
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao baixar o documento.");
    } finally { setBaixando(null); }
  }

  const carregar = useCallback(async () => {
    setLoading(true); setErro(null);
    try {
      const params = { data_inicio: dataInicio, data_fim: dataFim };
      const [r, d, lst] = await Promise.all([
        portalResumo(params),
        portalDashboard({ meses: 6, data_inicio: dataInicio, data_fim: dataFim }).catch(() => null),
        portalDocumentos({ ...params, tipo_documento: tipo || undefined, origem: origem || undefined, cancelada: false }),
      ]);
      setResumo(r);
      if (d) setDash(d);
      setDocs(lst);
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao carregar.");
    } finally {
      setLoading(false);
    }
  }, [dataInicio, dataFim, tipo, origem]);

  useEffect(() => { if (getPortalToken()) carregar(); }, [carregar]);

  async function baixar(doc: PortalDocumento, t: "xml" | "pdf") {
    setBaixando(`${doc.id}-${t}`); setErro(null);
    try { await portalBaixarArquivo(doc.id, t); }
    catch (err) { setErro(err instanceof ApiError ? err.message : `Falha ao baixar ${t.toUpperCase()}.`); }
    finally { setBaixando(null); }
  }

  async function baixarZip(arquivo: "xml" | "pdf") {
    setZipBusy(true); setErro(null);
    try {
      await portalBaixarZip({ tipo_documento: tipo || undefined, origem: origem || undefined, data_inicio: dataInicio, data_fim: dataFim, arquivo });
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao baixar o ZIP.");
    } finally { setZipBusy(false); }
  }

  async function handleUploadSaidas(file: File | null) {
    if (!file) return;
    setUploadBusy(true); setErro(null); setUploadResult(null); setUploadProg(null);
    try {
      // Upload em BACKGROUND: o POST volta na hora (job_id) e a gente faz polling
      // até concluir. Varejo (milhares de NFC-e) não estoura mais o Traefik (60s).
      const { job_id } = await portalUploadSaidas(file);
      const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));
      // Poll a cada 2s; teto generoso (~20min) p/ ZIP gigante de supermercado.
      for (let i = 0; i < 600; i++) {
        await sleep(2000);
        let job;
        try {
          job = await portalStatusUploadSaidas(job_id);
        } catch {
          continue; // hiccup de rede transitório — tenta de novo
        }
        setUploadProg({ feitas: job.feitas, total: job.total });
        if (job.status === "concluido" && job.resultado) {
          setUploadResult(job.resultado);
          setUploadProg(null);
          if (job.resultado.persistidos > 0) await carregar(); // notas novas já aparecem
          return;
        }
        if (job.status === "erro") {
          setErro(`Falha ao processar: ${job.erro || "erro desconhecido"}`);
          setUploadProg(null);
          return;
        }
      }
      setErro("O processamento está demorando mais que o esperado. As notas continuam sendo importadas — atualize a página em alguns minutos.");
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao enviar o arquivo.");
    } finally {
      setUploadBusy(false);
    }
  }

  async function manifestarDoc(doc: PortalDocumento) {
    setManifBusy(`${doc.id}`); setErro(null); setAviso(null);
    try {
      const r = await portalManifestarDoc(doc.id);
      setAviso(r.ok ? (r.aviso || "Ciência registrada! O XML completo será liberado em breve.") : `Não deu: ${r.cstat} ${r.motivo}`);
      await carregar();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao manifestar.");
    } finally { setManifBusy(null); }
  }

  async function manifestarTodas() {
    setManifBusy("lote"); setErro(null); setAviso(null);
    try {
      const r = await portalManifestarLote(20);
      setAviso(`${(r.manifestadas || 0) + (r.ja_cientes || 0)} nota(s) com Ciência. ${r.aviso || ""}`.trim());
      await carregar();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao manifestar em lote.");
    } finally { setManifBusy(null); }
  }

  function sair() { portalLogout(); router.replace("/portal/login"); }

  async function handleTrocarEmpresa(id: number) {
    if (!id || id === me?.empresa_ativa_id) return;
    try {
      await portalTrocarEmpresa(id); // grava novo token (empresa ativa)
      // Recarrega tudo de forma limpa com a nova empresa ativa.
      window.location.reload();
    } catch (err) {
      setErro(err instanceof ApiError ? err.message : "Falha ao trocar de empresa.");
    }
  }

  function irPara(v: View) {
    if (v === "manifestar" && origem === "emitida") setOrigem("");
    setErro(null); setAviso(null);
    setView(v);
    setMenuAberto(false); // fecha a gaveta no celular ao navegar
  }

  const cert = docsEmpresa?.certificado ?? null;
  const certUrgente = cert ? statusCert(cert).urgente : false;
  const docsVisiveis = docs.slice(0, MAX_LINHAS);
  const manifestaveis = docs.filter((d) => { const s = statusNota(d); return s.manifestar || s.aguardando; });
  const fatMax = Math.max(...(dash?.faturamento_mensal.map((f) => f.valor) || [1]), 1);
  const aManifestar = dash?.a_manifestar ?? 0;

  const navGroups = [
    { grupo: "Empresa", itens: [
      { id: "home" as View, label: "Início", icon: "home" },
      { id: "notas" as View, label: "Minhas notas", icon: "file" },
      { id: "indicadores" as View, label: "Faturamento", icon: "chart" },
    ] },
    { grupo: "Impostos", itens: [
      { id: "guias" as View, label: "Guias / DAS", icon: "receipt" },
      { id: "certidoes" as View, label: "Certidões", icon: "shield" },
    ] },
    { grupo: "Documentos", itens: [
      { id: "empresa" as View, label: "Documentos da empresa", icon: "folder", badge: docsEmpresa?.nao_lidos || 0 },
      { id: "documentos" as View, label: "Do escritório", icon: "folder", badge: escritorio?.nao_lidos || 0 },
      { id: "manifestar" as View, label: "Manifestações", icon: "check", badge: aManifestar },
    ] },
    { grupo: "Funcionários", itens: [
      { id: "admissao" as View, label: "Admissão", icon: "check", badge: 0 },
    ] },
    { grupo: "Atendimento", itens: [
      { id: "conversa" as View, label: "Falar com o escritório", icon: "chat", badge: chatNaoLidas },
    ] },
  ];

  // ---- pedaços reutilizáveis ----
  const filtroPeriodo = (comTipo: boolean) => (
    <div className="pac-card" style={{ marginBottom: 16 }}>
      <div className="pac-filtros">
        {comTipo ? (
          <label>Tipo
            <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos</option>
              <option value="NFE">NF-e / NFC-e</option>
              <option value="CTE">CT-e</option>
              <option value="NFSE">NFS-e</option>
            </select>
          </label>
        ) : null}
        <label>Emissão de<input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></label>
        <label>Emissão até<input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} /></label>
        <button type="button" className="pac-btn pac-btn-primary" onClick={carregar} disabled={loading}>{loading ? "Buscando..." : "Atualizar"}</button>
      </div>
    </div>
  );

  const tabelaNotas = (lista: PortalDocumento[]) => (
    <div style={{ overflowX: "auto" }}>
      <table className="pac-table">
        <thead>
          <tr>
            <th>Tipo</th><th>Emissão</th><th>Emitente / Destinatário</th>
            <th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "center" }}>Situação</th><th style={{ textAlign: "center" }}>Ações</th>
          </tr>
        </thead>
        <tbody>
          {lista.map((doc) => {
            const s = statusNota(doc);
            return (
              <tr key={doc.id}>
                <td>{doc.tipo_documento}</td>
                <td>{dataBR(doc.data_emissao)}</td>
                <td>{doc.origem === "emitida" ? (doc.nome_destinatario || "Consumidor (balcão)") : (doc.nome_emitente || "—")}</td>
                <td style={{ textAlign: "right" }}>{brl(doc.valor_total)}</td>
                <td style={{ textAlign: "center" }}>{pill(s.label, s.cor)}</td>
                <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                  {s.manifestar ? (
                    <button type="button" className="pac-btn pac-btn-ghost" onClick={() => manifestarDoc(doc)} disabled={manifBusy === `${doc.id}`} title="Dar Ciência da Operação — libera o XML/PDF">
                      {manifBusy === `${doc.id}` ? "..." : "✍ Manifestar"}
                    </button>
                  ) : s.aguardando ? (
                    <span style={{ fontSize: 12, color: GRAY }}>aguardando XML</span>
                  ) : s.baixar ? (
                    <span style={{ display: "inline-flex", gap: 6 }}>
                      <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixar(doc, "xml")} disabled={baixando === `${doc.id}-xml`}>
                        {baixando === `${doc.id}-xml` ? "..." : "XML"}
                      </button>
                      <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixar(doc, "pdf")} disabled={baixando === `${doc.id}-pdf`}>
                        {baixando === `${doc.id}-pdf` ? "..." : "PDF"}
                      </button>
                    </span>
                  ) : (
                    <span style={{ color: GRAY }}>—</span>
                  )}
                </td>
              </tr>
            );
          })}
          {!loading && lista.length === 0 ? (
            <tr><td colSpan={6} style={{ textAlign: "center", padding: 20, color: GRAY }}>Nenhuma nota.</td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );

  const tituloSecao = (icon: string, txt: string, extra?: React.ReactNode) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 14px" }}>
      <span style={{ color: NAVY }}><Icon name={icon} size={22} /></span>
      <h2 style={{ margin: 0, fontSize: 19, color: NAVY }}>{txt}</h2>
      {extra}
    </div>
  );

  return (
    <div className="pac-portal">
      {/* Ligação de voz (WebRTC) — detecta chamada do escritório e mostra a tela */}
      <PortalChamada />
      {/* Backdrop da gaveta (só aparece no celular quando o menu está aberto) */}
      {menuAberto ? <div className="pac-backdrop" onClick={() => setMenuAberto(false)} /> : null}
      <aside className={`pac-sidebar${menuAberto ? " open" : ""}`}>
        <div className="pac-logo" onClick={() => irPara("home")} title="Início">
          <img src="/pac-logo-branco.svg" alt="PAC Inteligência Tributária" />
        </div>

        <nav className="pac-nav">
          {navGroups.map((g) => (
            <div key={g.grupo} className="pac-navgroup">
              <div className="pac-navgroup-label">{g.grupo}</div>
              {g.itens.map((it) => (
                <button key={it.id} type="button" className={`pac-navitem${view === it.id ? " active" : ""}`} onClick={() => irPara(it.id)} title={it.label}>
                  <Icon name={it.icon} size={18} />
                  <span className="pac-navlabel">{it.label}</span>
                  {"badge" in it && (it as { badge: number }).badge > 0 ? (
                    <span className="pac-badge">{(it as { badge: number }).badge}</span>
                  ) : null}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="pac-sidebar-foot">
          <div className="pac-user-name">{me?.nome || ""}</div>
          <button type="button" className="pac-navitem" onClick={sair} title="Sair">
            <Icon name="logout" size={18} /><span className="pac-navlabel">Sair</span>
          </button>
        </div>
      </aside>

      <div className="pac-main">
        <header className="pac-topbar">
          <button
            type="button"
            className="pac-hamburger"
            onClick={() => setMenuAberto((v) => !v)}
            aria-label="Menu"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="pac-topbar-empresa">{me?.empresa?.razao_social || "Portal do Cliente"}</div>
            <div className="pac-topbar-cnpj">{me?.empresa?.cnpj ? `CNPJ ${me.empresa.cnpj}` : ""}</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* Multi-empresa: seletor só aparece se o login acessa mais de uma. */}
            {me?.empresas && me.empresas.length > 1 ? (
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: GRAY }}>
                Empresa:
                <select
                  value={me.empresa_ativa_id}
                  onChange={(e) => handleTrocarEmpresa(Number(e.target.value))}
                  style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #d7dbe6", fontSize: 13, maxWidth: 280 }}
                >
                  {me.empresas.map((e) => (
                    <option key={e.id} value={e.id}>{e.razao_social}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <span style={{ color: GRAY }}><Icon name="bell" size={20} /></span>
          </div>
        </header>

        <div className="pac-content">
          {aviso ? <div className="pac-toast pac-toast-ok">{aviso}</div> : null}
          {erro ? <div className="pac-toast pac-toast-err">{erro}</div> : null}

          {/* ===================== HOME ===================== */}
          {view === "home" ? (
            <>
              {/* Alerta: certificado digital vencido / a vencer */}
              {cert && certUrgente ? (
                <button
                  type="button"
                  onClick={() => irPara("empresa")}
                  className="pac-card"
                  style={{
                    width: "100%", textAlign: "left", cursor: "pointer", marginBottom: 14,
                    borderLeft: `4px solid ${statusCert(cert).cor}`, display: "flex",
                    justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap",
                  }}
                >
                  <span style={{ color: NAVY, fontSize: 14 }}>
                    🔐 Seu <strong>certificado digital</strong> {statusCert(cert).label.toLowerCase()} (validade {dataBR(cert.validade)}).
                  </span>
                  <span style={{ color: statusCert(cert).cor, fontWeight: 600, fontSize: 13 }}>Ver detalhes →</span>
                </button>
              ) : null}

              {filtroPeriodo(false)}
              {resumo ? (
                <div className="pac-kpis">
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">Faturamento (vendas)</div>
                    <div className="pac-kpi-value" style={{ color: GREEN }}>{brl(resumo.faturamento)}</div>
                    <div className="pac-kpi-sub">{resumo.emitidas.ativas} notas de saída</div>
                  </div>
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">Compras (entradas)</div>
                    <div className="pac-kpi-value" style={{ color: NAVY }}>{brl(resumo.recebidas.valor_ativas)}</div>
                    <div className="pac-kpi-sub">{resumo.recebidas.total} notas de entrada</div>
                  </div>
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">Total de notas</div>
                    <div className="pac-kpi-value" style={{ color: BLUE }}>{resumo.total_geral}</div>
                    <div className="pac-kpi-sub">no período</div>
                  </div>
                  <div className="pac-card pac-kpi">
                    <div className="pac-kpi-label">A manifestar</div>
                    <div className="pac-kpi-value" style={{ color: ORANGE_TX }}>{aManifestar}</div>
                    <div className="pac-kpi-sub">compras em resumo</div>
                  </div>
                </div>
              ) : null}

              <h3 style={{ margin: "4px 0 12px", color: GRAY, fontWeight: 500, fontSize: 14 }}>Atalhos</h3>
              <div className="pac-atalhos">
                <button type="button" className="pac-atalho pac-atalho-hero" onClick={() => irPara("notas")}>
                  <Icon name="file" size={22} />
                  <div className="pac-atalho-tit">Minhas notas fiscais</div>
                  <div className="pac-atalho-sub">{resumo ? `${resumo.total_geral} notas · baixar XML/PDF/ZIP` : "Carregando..."}</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("empresa")}>
                  <span style={{ color: NAVY }}><Icon name="folder" size={22} /></span>
                  <div className="pac-atalho-tit">Documentos da empresa{docsEmpresa && docsEmpresa.nao_lidos > 0 ? <span className="pac-tag">{docsEmpresa.nao_lidos} novos</span> : null}</div>
                  <div className="pac-atalho-sub">Contrato, alvará, certificado{cert ? ` · vence ${dataBR(cert.validade)}` : ""}</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("documentos")}>
                  <span style={{ color: NAVY }}><Icon name="folder" size={22} /></span>
                  <div className="pac-atalho-tit">Documentos do escritório{escritorio && escritorio.nao_lidos > 0 ? <span className="pac-tag">{escritorio.nao_lidos} novos</span> : null}</div>
                  <div className="pac-atalho-sub">Guias, relatórios e comunicados</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("indicadores")}>
                  <span style={{ color: GREEN }}><Icon name="chart" size={22} /></span>
                  <div className="pac-atalho-tit">Faturamento e indicadores</div>
                  <div className="pac-atalho-sub">Gráfico + melhores clientes</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("manifestar")}>
                  <span style={{ color: ORANGE }}><Icon name="check" size={22} /></span>
                  <div className="pac-atalho-tit">Manifestações{aManifestar > 0 ? <span className="pac-tag">{aManifestar}</span> : null}</div>
                  <div className="pac-atalho-sub">Liberar o XML das compras</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("guias")}>
                  <span style={{ color: ORANGE }}><Icon name="receipt" size={22} /></span>
                  <div className="pac-atalho-tit">Guias / impostos</div>
                  <div className="pac-atalho-sub">DAS do Simples · gerar atualizada</div>
                </button>
                <button type="button" className="pac-atalho" onClick={() => irPara("certidoes")}>
                  <span style={{ color: GREEN }}><Icon name="shield" size={22} /></span>
                  <div className="pac-atalho-tit">Certidões</div>
                  <div className="pac-atalho-sub">CNDs · baixar PDF</div>
                </button>
              </div>
            </>
          ) : null}

          {/* ===================== MINHAS NOTAS ===================== */}
          {view === "notas" ? (
            <>
              {tituloSecao("file", "Minhas notas fiscais")}

              <div className="pac-card" style={{ marginBottom: 14 }}>
                <h3 style={{ margin: "0 0 4px", color: NAVY, fontSize: 15 }}>📤 Subir notas de saída (qualquer estado)</h3>
                <p style={{ margin: "0 0 12px", color: GRAY, fontSize: 13 }}>
                  Exporte o ZIP de XMLs do seu emissor e solte aqui — as notas entram automaticamente.
                  Só são aceitas notas da <strong>sua</strong> empresa.
                </p>
                <label
                  style={{
                    display: "inline-block", background: ORANGE, color: "#fff", fontWeight: 500,
                    padding: "10px 18px", borderRadius: 9, cursor: uploadBusy ? "not-allowed" : "pointer",
                    opacity: uploadBusy ? 0.6 : 1, fontSize: 14,
                  }}
                >
                  {uploadBusy ? "Importando…" : "Escolher arquivo (.zip ou .xml)"}
                  <input
                    type="file" accept=".zip,.xml" style={{ display: "none" }} disabled={uploadBusy}
                    onChange={(e) => { handleUploadSaidas(e.target.files?.[0] || null); e.target.value = ""; }}
                  />
                </label>
                {uploadBusy ? (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, color: GRAY, marginBottom: 5 }}>
                      <span>
                        {uploadProg && uploadProg.total > 0
                          ? `Processando ${uploadProg.feitas.toLocaleString("pt-BR")} de ${uploadProg.total.toLocaleString("pt-BR")} notas…`
                          : "Lendo o arquivo… (pode levar alguns minutos em ZIP grande de varejo)"}
                      </span>
                      {uploadProg && uploadProg.total > 0 ? (
                        <span>{Math.floor((uploadProg.feitas / uploadProg.total) * 100)}%</span>
                      ) : null}
                    </div>
                    <div style={{ height: 8, borderRadius: 6, background: "#e6e9f0", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: uploadProg && uploadProg.total > 0
                            ? `${Math.min(100, Math.floor((uploadProg.feitas / uploadProg.total) * 100))}%`
                            : "15%",
                          background: ORANGE,
                          transition: "width 0.4s ease",
                        }}
                      />
                    </div>
                    <p style={{ margin: "7px 0 0", fontSize: 12, color: GRAY }}>
                      Pode fechar esta aba — a importação continua no servidor.
                    </p>
                  </div>
                ) : null}
                {uploadResult ? (
                  <div style={{ marginTop: 12, fontSize: 13.5, color: GREEN }}>
                    ✅ {uploadResult.persistidos} nota(s) importada(s) · {uploadResult.duplicados} já existiam
                    {uploadResult.fora_do_escopo > 0 ? (
                      <span style={{ color: ORANGE_TX }}> · {uploadResult.fora_do_escopo} ignorada(s) (não são da sua empresa)</span>
                    ) : null}
                    {uploadResult.nao_cadastrada > 0 ? (
                      <span style={{ color: GRAY }}> · {uploadResult.nao_cadastrada} sem empresa cadastrada</span>
                    ) : null}
                  </div>
                ) : null}
              </div>

              {filtroPeriodo(true)}
              <div className="pac-card">
                <div className="pac-toolbar">
                  <div className="pac-tabs">
                    {[{ v: "", label: "Todas" }, { v: "emitida", label: "Vendas (saída)" }, { v: "recebida", label: "Compras (entrada)" }].map((t) => (
                      <button key={t.v} type="button" className={`pac-tab${origem === t.v ? " active" : ""}`} onClick={() => setOrigem(t.v)}>{t.label}</button>
                    ))}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarZip("xml")} disabled={zipBusy}>{zipBusy ? "Gerando ZIP..." : "⬇ ZIP de XMLs"}</button>
                    <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarZip("pdf")} disabled={zipBusy}>⬇ ZIP de PDFs</button>
                  </div>
                </div>
                <p style={{ margin: "0 0 10px", color: GRAY, fontSize: 13 }}>
                  {loading ? "Carregando..." : `${docs.length} nota(s) no período${docs.length > MAX_LINHAS ? ` — mostrando as ${MAX_LINHAS} mais recentes (use os filtros ou baixe o ZIP)` : ""}.`}
                </p>
                {tabelaNotas(docsVisiveis)}
              </div>
            </>
          ) : null}

          {/* ===================== DOCUMENTOS DO ESCRITÓRIO ===================== */}
          {view === "empresa" ? (
            <>
              {tituloSecao("folder", "Documentos da empresa", docsEmpresa && docsEmpresa.nao_lidos > 0 ? <span className="pac-tag">{docsEmpresa.nao_lidos} novos</span> : undefined)}

              {/* Certificado digital em destaque */}
              {cert ? (
                <div className="pac-card" style={{ marginBottom: 14, borderLeft: `4px solid ${statusCert(cert).cor}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                    <div>
                      <h3 style={{ margin: "0 0 3px", color: NAVY, fontSize: 15 }}>🔐 Certificado digital (e-CNPJ A1)</h3>
                      {cert.subject ? <div style={{ fontSize: 12.5, color: GRAY, wordBreak: "break-word", overflowWrap: "anywhere" }}>{cert.subject}</div> : null}
                      <div style={{ fontSize: 12.5, color: GRAY, marginTop: 2 }}>
                        Validade: <strong>{dataBR(cert.validade)}</strong>
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 16, fontWeight: 700, color: statusCert(cert).cor }}>{statusCert(cert).label}</div>
                      {statusCert(cert).urgente ? (
                        <div style={{ fontSize: 12, color: statusCert(cert).cor, marginTop: 2 }}>
                          ⚠️ Providencie a renovação com seu contador.
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="pac-card" style={{ marginBottom: 14 }}>
                  <h3 style={{ margin: "0 0 3px", color: NAVY, fontSize: 15 }}>🔐 Certificado digital</h3>
                  <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>
                    Sem data de validade de certificado cadastrada ainda. Assim que o escritório registrar, ela aparece aqui.
                  </p>
                </div>
              )}

              {/* Documentos cadastrais (contrato, alvará, etc.) */}
              <div className="pac-card">
                {!docsEmpresa ? (
                  <p style={{ margin: 0, color: GRAY }}>Carregando...</p>
                ) : docsEmpresa.documentos.length === 0 ? (
                  <p style={{ margin: 0, color: GRAY }}>
                    Nenhum documento ainda. Contrato social, alvarás, certificados e procurações enviados pelo escritório aparecem aqui.
                  </p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="pac-table">
                      <thead>
                        <tr>
                          <th>Tipo</th><th>Documento</th><th>Vencimento</th><th style={{ textAlign: "center" }}>Ação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {docsEmpresa.documentos.map((d) => {
                          const t = tipoDocEmpresa(d.tipo);
                          return (
                            <tr key={d.id}>
                              <td>{pill(t.label, t.cor)}</td>
                              <td>
                                <span style={!d.lido ? { fontWeight: 500 } : undefined}>
                                  {!d.lido ? "🔵 " : ""}{d.titulo}
                                </span>
                                {d.mensagem ? <div style={{ fontSize: 12, color: GRAY }}>{d.mensagem}</div> : null}
                              </td>
                              <td>{d.vencimento ? dataBR(d.vencimento) : "—"}</td>
                              <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                                {d.tem_arquivo ? (
                                  <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarDocEmpresa(d)} disabled={baixando === `emp-${d.id}`}>
                                    {baixando === `emp-${d.id}` ? "..." : "⬇ Baixar"}
                                  </button>
                                ) : <span style={{ color: GRAY }}>—</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : null}

          {view === "admissao" ? (
            <PortalAdmissao />
          ) : null}

          {view === "conversa" ? (
            <>
              {tituloSecao("chat", "Falar com o escritório")}
              <p style={{ color: GRAY, fontSize: 13, margin: "0 0 12px" }}>
                Tire dúvidas, envie recados e receba retorno do escritório. As mensagens ficam registradas aqui.
              </p>
              {/* Notificação de sistema (Web Push): ativar (se ainda não) ou testar (se já) */}
              {pushStatus !== "granted" && pushStatus !== "unsupported" ? (
                <button
                  type="button"
                  onClick={ativarPush}
                  disabled={pushBusy}
                  className="pac-card"
                  style={{
                    width: "100%", textAlign: "left", cursor: "pointer", marginBottom: 12,
                    display: "flex", alignItems: "center", gap: 10, borderLeft: `4px solid ${ORANGE}`,
                  }}
                >
                  <span style={{ fontSize: 22 }}>🔔</span>
                  <span style={{ fontSize: 13.5, color: NAVY }}>
                    <strong>Ativar notificações no celular</strong> — seja avisado quando o escritório responder, mesmo com o app fechado.
                    {pushStatus === "denied" ? <span style={{ color: RED }}> (bloqueado — libere nas configurações do site)</span> : null}
                  </span>
                </button>
              ) : pushStatus === "granted" ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 12.5, color: GREEN }}>🔔 Notificações ativadas.</span>
                  <button
                    type="button"
                    onClick={testarPush}
                    disabled={pushBusy}
                    className="pac-btn pac-btn-ghost"
                    style={{ fontSize: 12.5 }}
                  >
                    {pushBusy ? "Enviando…" : "Enviar notificação de teste"}
                  </button>
                </div>
              ) : null}
              <ChatThread
                mensagens={mensagens}
                meuLado="cliente"
                onEnviar={enviarMensagemPortal}
                onEnviarArquivo={enviarArquivoPortal}
                carregando={chatLoading}
                altura={chatAltura}
                vazioLabel="Nenhuma mensagem ainda. Mande a primeira pro escritório 👇"
              />
            </>
          ) : null}

          {view === "documentos" ? (
            <>
              {tituloSecao("folder", "Documentos do escritório", escritorio && escritorio.nao_lidos > 0 ? <span className="pac-tag">{escritorio.nao_lidos} novos</span> : undefined)}
              <div className="pac-card">
                {!escritorio ? (
                  <p style={{ margin: 0, color: GRAY }}>Carregando...</p>
                ) : escritorio.documentos.length === 0 ? (
                  <p style={{ margin: 0, color: GRAY }}>
                    Nenhum documento ainda. Quando o escritório te enviar guias, relatórios ou comunicados, eles aparecem aqui.
                  </p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="pac-table">
                      <thead>
                        <tr>
                          <th>Tipo</th><th>Documento</th><th>Competência</th><th>Vencimento</th>
                          <th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "center" }}>Ação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {escritorio.documentos.map((d) => {
                          const t = tipoEscritorio(d.tipo);
                          return (
                            <tr key={d.id}>
                              <td>{pill(t.label, t.cor)}</td>
                              <td>
                                <span style={!d.lido ? { fontWeight: 500 } : undefined}>
                                  {!d.lido ? "🔵 " : ""}{d.titulo}
                                </span>
                                {d.mensagem ? <div style={{ fontSize: 12, color: GRAY }}>{d.mensagem}</div> : null}
                              </td>
                              <td>{d.competencia || "—"}</td>
                              <td>{d.vencimento ? dataBR(d.vencimento) : "—"}</td>
                              <td style={{ textAlign: "right" }}>{d.valor != null ? brl(d.valor) : "—"}</td>
                              <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                                {d.tem_arquivo ? (
                                  <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarDocEscritorio(d)} disabled={baixando === `esc-${d.id}`}>
                                    {baixando === `esc-${d.id}` ? "..." : "⬇ Baixar"}
                                  </button>
                                ) : <span style={{ color: GRAY }}>—</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : null}

          {/* ===================== FATURAMENTO E INDICADORES ===================== */}
          {view === "indicadores" ? (
            <>
              {tituloSecao("chart", "Faturamento e indicadores")}
              {filtroPeriodo(false)}
              {dash && dash.faturamento_mensal.length > 0 ? (
                <div className="pac-card" style={{ marginBottom: 16 }}>
                  <h3 style={{ marginTop: 0, color: NAVY }}>Faturamento por mês <span style={{ fontSize: 13, fontWeight: 400, color: GRAY }}>(tendência — últimos 6 meses)</span></h3>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 150, padding: "8px 4px 0" }}>
                    {dash.faturamento_mensal.map((f) => (
                      <div key={f.mes} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }} title={brl(f.valor)}>
                        <span style={{ fontSize: 11, color: GRAY }}>{(f.valor / 1000).toFixed(0)}k</span>
                        <div style={{ width: "100%", maxWidth: 48, height: `${Math.max(4, Math.round((f.valor / fatMax) * 110))}px`, background: GREEN, borderRadius: "4px 4px 0 0" }} />
                        <span style={{ fontSize: 12, color: GRAY }}>{mesLabel(f.mes)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {dash ? (
                <div className="pac-paineis">
                  <div className="pac-card">
                    <h3 style={{ marginTop: 0, color: NAVY, display: "flex", alignItems: "center", gap: 8 }}><Icon name="users" size={18} /> Melhores clientes</h3>
                    <Ranking items={dash.top_clientes} cor={BLUE} />
                  </div>
                  <div className="pac-card">
                    <h3 style={{ marginTop: 0, color: NAVY, display: "flex", alignItems: "center", gap: 8 }}><Icon name="truck" size={18} /> Maiores fornecedores</h3>
                    <Ranking items={dash.top_fornecedores} cor={NAVY} />
                  </div>
                </div>
              ) : (
                <div className="pac-card"><p style={{ margin: 0, color: GRAY }}>Sem indicadores no período.</p></div>
              )}
            </>
          ) : null}

          {/* ===================== MANIFESTAÇÕES ===================== */}
          {view === "manifestar" ? (
            <>
              {tituloSecao("check", "Manifestações")}
              {filtroPeriodo(false)}
              <div className="pac-card">
                <div className="pac-toolbar">
                  <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>
                    {aManifestar > 0
                      ? `${aManifestar} compra(s) aguardando Ciência da Operação. Manifestar libera o XML/PDF completo.`
                      : "Nenhuma compra pendente de manifestação. Tudo em dia. ✅"}
                  </p>
                  {aManifestar > 0 ? (
                    <button type="button" className="pac-btn pac-btn-primary" onClick={manifestarTodas} disabled={manifBusy === "lote"} title="Dar Ciência da Operação em todas as compras em resumo">
                      {manifBusy === "lote" ? "Manifestando..." : `✍ Manifestar ${aManifestar} pendente(s)`}
                    </button>
                  ) : null}
                </div>
                <p style={{ margin: "0 0 10px", color: GRAY, fontSize: 12, fontStyle: "italic" }}>
                  Prazos: Ciência até 10 dias após a emissão · Confirmação até 90 dias. Notas com mais de 90 dias ficam fora do prazo.
                </p>
                {tabelaNotas(manifestaveis)}
              </div>
            </>
          ) : null}

          {/* ===================== GUIAS / DAS ===================== */}
          {view === "guias" ? (
            <>
              {tituloSecao("receipt", "Guias / impostos")}
              <div className="pac-card" style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <h3 style={{ margin: 0, color: NAVY }}>DAS — Simples Nacional</h3>
                  <button type="button" className="pac-btn pac-btn-ghost" onClick={() => buscarGuias()} disabled={guiaBusy === "sync"} title="Puxa suas guias do Simples direto da Receita (1ª grátis · depois R$ 5,00)">
                    {guiaBusy === "sync" ? "Buscando..." : "🔄 Buscar minhas guias"}
                  </button>
                </div>
                <p style={{ margin: "8px 0 12px", color: GRAY, fontSize: 13 }}>
                  Atrasou? Clique <b>Gerar atualizada</b> que o sistema recalcula com Selic + mora.
                  <br /><i>1ª busca grátis · 1 recálculo grátis por guia · extras R$ {valorRecalc.toFixed(2).replace(".", ",")} cada.</i>
                </p>
                <div style={{ overflowX: "auto" }}>
                  <table className="pac-table">
                    <thead>
                      <tr>
                        <th>Competência</th><th>Vencimento</th>
                        <th style={{ textAlign: "right" }}>Valor</th>
                        <th style={{ textAlign: "center" }}>Situação</th>
                        <th style={{ textAlign: "center" }}>Ações</th>
                      </tr>
                    </thead>
                    <tbody>
                      {guias.map((g) => {
                        const s = situacaoGuia(g.situacao);
                        const valor = g.valor_atualizado ?? g.valor_principal;
                        return (
                          <tr key={g.id}>
                            <td>{g.competencia}</td>
                            <td>{dataBR(g.data_vencimento)}{g.dias_atraso > 0 ? <span style={{ color: RED, fontSize: 12 }}> · {g.dias_atraso}d atraso</span> : null}</td>
                            <td style={{ textAlign: "right" }}>{brl(valor)}{g.valor_atualizado != null ? <div style={{ fontSize: 11, color: GRAY }}>atualizado</div> : null}</td>
                            <td style={{ textAlign: "center" }}>{pill(s.label, s.cor)}</td>
                            <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                              {g.pode_recalcular ? (
                                <button type="button" className="pac-btn pac-btn-primary" onClick={() => recalcularGuia(g)} disabled={guiaBusy === `recalc-${g.id}`}
                                  title={g.recalculos > 0 ? `Recálculo extra — custa R$ ${valorRecalc.toFixed(2)}` : "1º recálculo é grátis"}>
                                  {guiaBusy === `recalc-${g.id}` ? "..." : (g.tem_pdf ? "↻ Atualizar" : "Gerar atualizada")}
                                </button>
                              ) : null}
                              {g.tem_pdf ? (
                                <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarGuia(g)} disabled={guiaBusy === `pdf-${g.id}`} style={{ marginLeft: 6 }}>
                                  {guiaBusy === `pdf-${g.id}` ? "..." : "⬇ PDF"}
                                </button>
                              ) : null}
                            </td>
                          </tr>
                        );
                      })}
                      {guias.length === 0 ? (
                        <tr><td colSpan={5} style={{ textAlign: "center", padding: 20, color: GRAY }}>Nenhuma guia ainda — clique <b>🔄 Buscar minhas guias</b> acima pra puxar da Receita.</td></tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="pac-card">
                <h3 style={{ marginTop: 0, color: NAVY }}>DCTFWeb — contribuições (folha)</h3>
                <p style={{ margin: "0 0 12px", color: GRAY, fontSize: 13 }}>
                  DARFs de contribuições previdenciárias e retenções, emitidos pelo escritório. Baixe o PDF pra pagar.
                </p>
                {dctfweb.length === 0 ? (
                  <p style={{ margin: 0, color: GRAY, fontSize: 13 }}>Nenhum DARF DCTFWeb disponível ainda.</p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="pac-table">
                      <thead>
                        <tr>
                          <th>Período</th><th>Tipo</th><th>Emitida em</th>
                          <th style={{ textAlign: "center" }}>Ação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dctfweb.map((d) => (
                          <tr key={d.id}>
                            <td>{d.periodo}</td>
                            <td>{d.origem === "andamento" ? "Em andamento" : "Mensal"}{d.categoria ? <span style={{ color: GRAY, fontSize: 12 }}> · cat. {d.categoria}</span> : null}</td>
                            <td>{dataBR(d.emitida_em)}</td>
                            <td style={{ textAlign: "center" }}>
                              {d.tem_pdf ? (
                                <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarDctfweb(d)} disabled={guiaBusy === `dctf-${d.id}`}>
                                  {guiaBusy === `dctf-${d.id}` ? "..." : "⬇ PDF"}
                                </button>
                              ) : <span style={{ color: GRAY }}>—</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : null}

          {/* ===================== CERTIDÕES / CNDs ===================== */}
          {view === "certidoes" ? (
            <>
              {tituloSecao("shield", "Certidões (CNDs)")}
              <div className="pac-card">
                {!certidoes ? (
                  <p style={{ margin: 0, color: GRAY }}>Carregando...</p>
                ) : certidoes.length === 0 ? (
                  <p style={{ margin: 0, color: GRAY }}>Nenhuma certidão disponível ainda. O escritório emite e elas aparecem aqui.</p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="pac-table">
                      <thead>
                        <tr>
                          <th>Certidão</th><th>Número</th><th>Validade</th>
                          <th style={{ textAlign: "center" }}>Situação</th><th style={{ textAlign: "center" }}>Ação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {certidoes.map((c) => {
                          const st = statusCnd(c);
                          return (
                            <tr key={c.id}>
                              <td>
                                {c.tipo_label}
                                {c.pendencias && c.pendencias.length > 0 ? (
                                  <div style={{ fontSize: 12, color: RED, marginTop: 2 }}>⚠ {c.pendencias.join(" · ")}</div>
                                ) : null}
                              </td>
                              <td>{c.numero || "—"}</td>
                              <td>{dataBR(c.data_validade)}{c.dias_para_vencer != null && c.status === "A_VENCER" ? <span style={{ color: ORANGE_TX, fontSize: 12 }}> · {c.dias_para_vencer}d</span> : null}</td>
                              <td style={{ textAlign: "center" }}>{pill(st.label, st.cor)}</td>
                              <td style={{ textAlign: "center" }}>
                                {c.tem_pdf ? (
                                  <button type="button" className="pac-btn pac-btn-ghost" onClick={() => baixarCertidao(c)} disabled={baixando === `cnd-${c.id}`}>
                                    {baixando === `cnd-${c.id}` ? "..." : "⬇ Baixar"}
                                  </button>
                                ) : <span style={{ color: GRAY }}>—</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>

      <style jsx>{`
        .pac-portal { display: flex; min-height: 100vh; background: #f5f7fa; color: #1b2333;
          font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif; letter-spacing: -0.01em;
          max-width: 100%; overflow-x: hidden; }

        .pac-sidebar { width: 208px; flex-shrink: 0; background: ${NAVY}; color: #c4d0e4;
          display: flex; flex-direction: column; gap: 16px; padding: 16px 12px; overflow-y: auto; }
        .pac-hamburger { display: none; align-items: center; justify-content: center; background: transparent;
          border: none; color: ${NAVY}; cursor: pointer; padding: 4px; margin-right: 6px; flex-shrink: 0; }
        .pac-logo { display: flex; align-items: center; padding: 6px 6px 2px; cursor: pointer; }
        .pac-logo img { height: 34px; display: block; }
        .pac-nav { display: flex; flex-direction: column; gap: 14px; }
        .pac-navgroup { display: flex; flex-direction: column; gap: 2px; }
        .pac-navgroup-label { color: #6f82a6; font-size: 11px; letter-spacing: 0.08em; padding: 0 8px 4px; text-transform: uppercase; }
        .pac-navitem { position: relative; display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
          padding: 9px 10px; border-radius: 8px; border: none; background: transparent; color: #c4d0e4;
          font: inherit; font-size: 13.5px; cursor: pointer; transition: background .12s ease, color .12s ease; }
        .pac-navitem:hover { background: ${NAVY_2}; color: #fff; }
        .pac-navitem.active { background: rgba(236,139,28,0.16); color: #fff; box-shadow: inset 3px 0 0 ${ORANGE}; }
        .pac-navlabel { flex: 1; }
        .pac-badge { background: ${ORANGE}; color: ${NAVY}; font-size: 11px; font-weight: 500; padding: 0 7px; border-radius: 9px; }
        .pac-sidebar-foot { margin-top: auto; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 10px; }
        .pac-user-name { color: #9fb0cc; font-size: 12px; padding: 0 10px 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

        .pac-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .pac-topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px;
          background: #fff; border-bottom: 1px solid #e6eaf0; padding: 12px 24px; }
        .pac-topbar-empresa { font-size: 14px; font-weight: 500; color: ${NAVY}; }
        .pac-topbar-cnpj { font-size: 12px; color: ${GRAY}; }
        .pac-content { padding: 20px 24px; }

        .pac-card { background: #fff; border: 1px solid #e6eaf0; border-radius: 12px; padding: 16px 18px; }
        .pac-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
        .pac-kpi { padding: 14px 16px; }
        .pac-kpi-label { font-size: 13px; color: ${GRAY}; }
        .pac-kpi-value { font-size: 22px; font-weight: 500; margin: 2px 0; }
        .pac-kpi-sub { font-size: 12px; color: ${GRAY}; }

        .pac-atalhos { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .pac-atalho { text-align: left; background: #fff; border: 1px solid #e6eaf0; border-radius: 11px; padding: 16px;
          cursor: pointer; color: ${NAVY}; font: inherit; transition: transform .12s ease, box-shadow .12s ease; }
        .pac-atalho:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(22,41,77,0.08); }
        .pac-atalho-hero { background: ${NAVY}; border-color: ${NAVY}; color: #fff; }
        .pac-atalho-hero :global(svg) { color: ${ORANGE}; }
        .pac-atalho-tit { font-size: 14px; font-weight: 500; margin-top: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .pac-atalho-sub { font-size: 12px; margin-top: 2px; opacity: .8; }
        .pac-atalho-hero .pac-atalho-sub { color: #b9c6dd; opacity: 1; }
        .pac-tag { background: #fdecd6; color: ${ORANGE_TX}; font-size: 11px; padding: 1px 7px; border-radius: 9px; font-weight: 500; }
        .pac-atalho-hero .pac-tag { background: ${ORANGE}; color: ${NAVY}; }

        .pac-paineis { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }

        .pac-filtros { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
        .pac-filtros label { display: grid; gap: 5px; font-size: 13px; color: ${GRAY}; }
        .pac-filtros input, .pac-filtros select { appearance: none; border: 1px solid #d8dee8; border-radius: 8px;
          padding: 8px 10px; font: inherit; font-size: 14px; background: #fff; color: #1b2333; min-width: 140px; }
        .pac-filtros input:focus, .pac-filtros select:focus { outline: none; border-color: ${ORANGE}; box-shadow: 0 0 0 3px rgba(236,139,28,0.18); }

        .pac-btn { appearance: none; font: inherit; font-size: 13px; padding: 8px 14px; border-radius: 8px; cursor: pointer; transition: filter .12s ease, background .12s ease; }
        .pac-btn:disabled { opacity: .55; cursor: not-allowed; }
        .pac-btn-primary { background: ${ORANGE}; color: #fff; border: none; font-weight: 500; }
        .pac-btn-primary:hover:not(:disabled) { filter: brightness(1.05); }
        .pac-btn-ghost { background: #fff; border: 1px solid #d8dee8; color: ${NAVY}; }
        .pac-btn-ghost:hover:not(:disabled) { background: #f1f4f8; }

        .pac-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        .pac-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
        .pac-tab { appearance: none; font: inherit; font-size: 13px; padding: 7px 13px; border-radius: 8px; cursor: pointer;
          background: #fff; border: 1px solid #d8dee8; color: ${NAVY}; }
        .pac-tab.active { background: ${NAVY}; border-color: ${NAVY}; color: #fff; }

        .pac-table { width: 100%; border-collapse: collapse; }
        .pac-table th { text-align: left; font-size: 12px; color: ${GRAY}; text-transform: uppercase; letter-spacing: 0.04em;
          font-weight: 500; padding: 8px 10px; border-bottom: 1px solid #e6eaf0; }
        .pac-table td { padding: 10px; border-bottom: 1px solid #eef1f5; font-size: 13.5px; vertical-align: middle; }
        .pac-table tbody tr:hover td { background: #f8fafc; }

        .pac-toast { padding: 10px 14px; border-radius: 8px; font-size: 13.5px; margin-bottom: 14px; }
        .pac-toast-ok { background: #e6f6ef; color: #0f6e56; border: 1px solid #b7e3d2; }
        .pac-toast-err { background: #fdeaea; color: #a32d2d; border: 1px solid #f3c2c2; }

        /* Celular/tablet: a lateral vira GAVETA (drawer) que desliza da esquerda,
           acionada pelo ☰ na barra de cima. Conteúdo ocupa a largura toda. */
        @media (max-width: 820px) {
          .pac-hamburger { display: inline-flex; }
          .pac-sidebar {
            position: fixed; top: 0; left: 0; bottom: 0; width: 260px; z-index: 60;
            transform: translateX(-100%); transition: transform .22s ease;
            box-shadow: 2px 0 24px rgba(0,0,0,0.35); padding-top: env(safe-area-inset-top, 0px);
          }
          .pac-sidebar.open { transform: translateX(0); }
          .pac-backdrop { position: fixed; inset: 0; background: rgba(10,16,30,0.5); z-index: 55; }
          .pac-content { padding: 14px 12px; overflow-x: hidden; }
          .pac-topbar { padding: 10px 12px; padding-top: max(10px, env(safe-area-inset-top, 0px)); }
          .pac-kpis { grid-template-columns: 1fr 1fr; }
          .pac-atalhos { grid-template-columns: 1fr; }
          .pac-paineis { grid-template-columns: 1fr; }
          /* Tabelas mais largas que a tela ROLAM dentro do próprio card (a página
             não anda pro lado). O título/botão acima ficam fixos (texto quebra). */
          .pac-card { overflow-x: auto; }
          .pac-table { min-width: 520px; }
        }
        /* Telas bem estreitas: KPIs numa coluna só. */
        @media (max-width: 460px) {
          .pac-kpis { grid-template-columns: 1fr; }
          .pac-topbar-empresa { font-size: 13px; }
        }
      `}</style>
    </div>
  );
}
