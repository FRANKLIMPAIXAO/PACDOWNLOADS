import { NextResponse } from "next/server";

// Endpoint de saúde do FRONT (usado pelo HEALTHCHECK do Docker).
// `force-dynamic` + `revalidate 0`: nunca cacheia — tem que EXECUTAR de verdade
// a cada chamada, senão um processo travado responderia do cache e o healthcheck
// não detectaria a falha (era o caso: o container travava e ninguém reiniciava).
export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  return NextResponse.json({ status: "ok", ts: Date.now() });
}
