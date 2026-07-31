import { NextResponse } from "next/server";

// Endpoint de saúde do FRONT.
// 1) HEALTHCHECK do Docker (sonda interna 127.0.0.1) — se travar, reinicia.
// 2) Monitor externo (cron-job.org) — avisa por e-mail quando cai/volta.
//
// `force-dynamic` + `revalidate 0`: nunca cacheia — tem que EXECUTAR de verdade
// a cada chamada, senão um processo travado responderia do cache e o healthcheck
// não detectaria a falha (era o caso: o container travava e ninguém reiniciava).
export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  // `uptime` REINICIA quando o container reinicia → é o sinal de "caiu e voltou":
  // se estiver baixo (poucos minutos) numa hora qualquer do dia, houve reinício.
  const uptimeS = Math.round(process.uptime());
  // Memória: se subir ao longo do dia e o travamento vier junto do pico, temos a
  // CAUSA RAIZ (vazamento) em vez de só a auto-recuperação.
  const m = process.memoryUsage();
  const mb = (b: number) => Math.round(b / 1048576);

  return NextResponse.json({
    status: "ok",
    ts: Date.now(),
    uptime_s: uptimeS,
    uptime_humano:
      uptimeS < 3600
        ? `${Math.round(uptimeS / 60)} min`
        : `${Math.floor(uptimeS / 3600)}h ${Math.round((uptimeS % 3600) / 60)}min`,
    memoria_mb: { rss: mb(m.rss), heap_usado: mb(m.heapUsed), heap_total: mb(m.heapTotal) },
  });
}
