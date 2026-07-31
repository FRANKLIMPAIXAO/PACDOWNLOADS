# Frontend Next.js 15 com SSR (output: standalone)
# Multi-stage: deps -> build -> runner mínimo (~150 MB)

# --- Stage 1: deps ---
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# --- Stage 2: build ---
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Variáveis NEXT_PUBLIC_* sao embedadas em build-time (recebidas via --build-arg)
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# --- Stage 3: runtime mínimo ---
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Copia somente o output standalone (sem node_modules inteiro)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static     ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public           ./public

USER nextjs
EXPOSE 3000

# HEALTHCHECK — resolve o "front caiu e só volta com deploy manual".
# Sintoma real: o processo Node TRAVAVA (aceitava TCP/TLS mas nunca respondia).
# Como ele NÃO morria, o Docker/Swarm achava que estava saudável e nunca
# reiniciava — só o deploy recriava o container. Agora o container é sondado a
# cada 30s; 3 falhas seguidas (~1,5 min) marcam unhealthy e o orquestrador
# reinicia sozinho. `--start-period` dá folga pro boot do Next.
# Usa wget do busybox (já existe no alpine) — sem dependência nova.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD wget -q -T 4 -O /dev/null http://127.0.0.1:3000/api/health || exit 1

CMD ["node", "server.js"]
