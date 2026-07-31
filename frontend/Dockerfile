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

# ATENCAO - NAO reintroduzir HEALTHCHECK aqui sem validar no ambiente real.
# Tentativa em 30/07/2026 (commit 34ff6e6) coincidiu com o servico fora do ar
# (502 imediato = sem container saudavel, em vez do timeout de app travado):
# se a sonda falha, o Swarm MATA o container em loop e o site cai de vez.
# Suspeita principal: a PORTA. O Easypanel pode injetar PORT != 3000 e a sonda
# fixa em :3000 falharia sempre. O lugar certo pra configurar isso e a interface
# do Easypanel (da pra ajustar/desligar sem rebuild).
# A rota GET /api/health continua existindo, usada pelo monitor EXTERNO
# (cron-job.org) — que avisa por e-mail e NAO pode derrubar nada.

CMD ["node", "server.js"]
