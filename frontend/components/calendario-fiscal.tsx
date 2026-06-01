"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../lib/api";
import { EventoAgenda, listarEventos, tipoColor } from "../lib/agenda";

const NOMES_MESES = [
  "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

const DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"];

function ymd(year: number, month0: number, day: number): string {
  return `${year}-${String(month0 + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function CalendarioFiscal() {
  const today = new Date();
  const [ano, setAno] = useState(today.getFullYear());
  const [mes0, setMes0] = useState(today.getMonth()); // 0..11

  const [eventos, setEventos] = useState<EventoAgenda[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEventos(null);
    setError(null);
    const mes = `${ano}-${String(mes0 + 1).padStart(2, "0")}`;
    listarEventos(mes)
      .then(setEventos)
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar agenda.");
      });
  }, [ano, mes0]);

  const eventosPorDia = useMemo(() => {
    const map = new Map<string, EventoAgenda[]>();
    for (const e of eventos ?? []) {
      const arr = map.get(e.data) ?? [];
      arr.push(e);
      map.set(e.data, arr);
    }
    return map;
  }, [eventos]);

  function navegar(delta: number) {
    let m = mes0 + delta;
    let a = ano;
    while (m < 0) { m += 12; a -= 1; }
    while (m > 11) { m -= 12; a += 1; }
    setMes0(m);
    setAno(a);
  }

  // Construir grid: primeiro dia da semana do mes + dias
  const primeiroDiaSemana = new Date(ano, mes0, 1).getDay(); // 0..6
  const totalDias = new Date(ano, mes0 + 1, 0).getDate();
  const cells: ({ day: number } | null)[] = [];
  for (let i = 0; i < primeiroDiaSemana; i++) cells.push(null);
  for (let d = 1; d <= totalDias; d++) cells.push({ day: d });
  // Completa para múltiplo de 7
  while (cells.length % 7 !== 0) cells.push(null);

  const todayKey = ymd(today.getFullYear(), today.getMonth(), today.getDate());

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Agenda fiscal</h3>
        <div className="page-actions">
          <button type="button" className="btn-ghost" onClick={() => navegar(-1)}>‹</button>
          <span style={{ minWidth: 160, textAlign: "center", fontWeight: 600 }}>
            {NOMES_MESES[mes0]} de {ano}
          </span>
          <button type="button" className="btn-ghost" onClick={() => navegar(1)}>›</button>
        </div>
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      <div className="calendar">
        <div className="calendar-head">
          {DIAS_SEMANA.map((d) => <span key={d}>{d}</span>)}
        </div>
        <div className="calendar-grid">
          {cells.map((cell, i) => {
            if (!cell) return <div key={`e-${i}`} className="calendar-day empty" />;
            const key = ymd(ano, mes0, cell.day);
            const evs = eventosPorDia.get(key) ?? [];
            const isToday = key === todayKey;
            return (
              <div
                key={key}
                className={`calendar-day ${isToday ? "today" : ""}`}
                title={evs.map((e) => `${e.titulo} — ${e.descricao || ""}`).join("\n")}
              >
                <span className="calendar-day-num">{cell.day}</span>
                {evs.length > 0 ? (
                  <>
                    {evs.slice(0, 2).map((e, idx) => (
                      <span
                        key={`${key}-${idx}`}
                        className="calendar-event-line"
                        style={{ borderLeftColor: tipoColor(e.tipo), borderLeftWidth: 2 }}
                      >
                        {e.titulo}
                      </span>
                    ))}
                    {evs.length > 2 ? (
                      <div className="calendar-events">
                        {evs.slice(2).map((e, idx) => (
                          <span
                            key={`d-${key}-${idx}`}
                            className="calendar-dot"
                            style={{ background: tipoColor(e.tipo) }}
                            title={e.titulo}
                          />
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: "0.78rem", color: "var(--muted)" }}>
        {[
          { tipo: "CND",     label: "CND" },
          { tipo: "DAS",     label: "DAS" },
          { tipo: "DCTFWEB", label: "DCTFWeb" },
          { tipo: "GPS",     label: "GPS/INSS" },
          { tipo: "FGTS",    label: "FGTS" },
        ].map((l) => (
          <span key={l.tipo} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span className="calendar-dot" style={{ background: tipoColor(l.tipo) }} />
            {l.label}
          </span>
        ))}
      </div>
    </section>
  );
}
