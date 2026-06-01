# MEMORY — PAC XML Downloader

> Índice de handoffs + estado atual. Pra detalhes, ler o handoff mais recente.

## Estado atual (27/05/2026)

Sistema fiscal completo pra escritório contábil PAC INTELIGENCIA TRIBUTARIA
(CNPJ 37.165.535/0001-22 — Franklim Paixão). Foco: 120 empresas clientes.

**Módulos funcionais em produção:**
- ✅ Cadastro empresas (com cert A1, dados via BrasilAPI, integração Focus NFe)
- ✅ Documentos fiscais (NFe/CTe/NFSe) — DF-e via Focus, robô SEFAZ-GO, manifestação, DANFE local
- ✅ DAS Simples Nacional (Integra Contador — sync + emissão atualizada com Selic+mora)
- ✅ Parcelamentos PARCSN Simples (Integra Contador)
- ✅ DCTFWeb guias (Integra Contador GERARGUIA31)
- ✅ Robô SEFAZ-GO (Playwright + 2Captcha + cert A1 + multi-empresa batch)
- ✅ Dashboard consolidado (cards + tabela por empresa)
- ✅ CND Federal / FEDERAL_OFICIAL (Integra Contador SITFIS)
- ✅ CND FGTS (Infosimples — pré-pago R$ 0,20/consulta)
- ✅ CND Estadual por UF (Infosimples)
- ✅ Parcelamentos PGFN — cadastro manual (sem API disponível)
- ✅ FGTS Digital — emissão guia + consulta (Infosimples, modo Procurador)

**Pendência crítica:**
- 🟡 Token Infosimples retornando code 601 (auth inválida) — precisa colocar token correto no `.env` pra sair do mock

## Stack

- Backend: FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2 + Celery + Redis
- Frontend: Next.js 15 (App Router) + TypeScript
- DB: SQLite (dev), Postgres (prod planejado)
- Integrações: Focus NFe, Integra Contador (Serpro), Infosimples, Playwright+2Captcha

## Índice de handoffs (mais recente em cima)

| Data | Arquivo | O que cobriu |
|---|---|---|
| **27/05/2026** | `HANDOFF_2026-05-27_PROD-PREP.md` | Card FGTS dashboard + fix CLAVEAUX batch + fix polling Robô + cadastro 5 empresas Excel + auditoria Postgres + plano deploy Easypanel/Supabase |
| 26/05/2026 | `HANDOFF_2026-05-26_INFOSIMPLES-FGTS-PGFN.md` | Provider Infosimples + cache TTL + CND FGTS/Estadual + FGTS Digital (guias) + PGFN manual + dashboard PGFN |
| 25/05/2026 | `HANDOFF_2026-05-25_PARTE-2_DASHBOARD-ROBO.md` | Dashboard consolidado + Robô SEFAZ filtro empresa + AGIMED 4 bugs (CNPJ filial, sem resultados, modal, histórico) |
| 25/05/2026 | `HANDOFF_2026-05-25_PRODUCAO-COMPLETA.md` | Integra Contador (DAS/PARCSN/DCTFWeb) + DANFE local + saída vs entrada |
| 22/05/2026 | `HANDOFF_2026-05-22_AGENTE-SEFAZ-GO-V2.md` | Robô SEFAZ-GO v2 (refatoração após bugs datepicker + histórico) |
| 21/05/2026 | `HANDOFF_2026-05-21_AGENTE-SEFAZ-GO.md` | Robô SEFAZ-GO v1 (Playwright + cert A1 + 2Captcha + Cloudflare Turnstile) |
| 13/05/2026 | `HANDOFF_2026-05-13_CND-RESEARCH.md` | Pesquisa CND (decisão Infosimples vs Playwright) |
| 02/05/2026 | `HANDOFF_2026-05-02.md` | (legado) |
| 27/04/2026 | `HANDOFF_2026-04-27.md` | (legado) |
| 26/04/2026 | `HANDOFF_2026-04-26.md` | (legado) |

## Custos operacionais estimados (120 empresas)

| Serviço | Mensal | Anual | Notas |
|---|---|---|---|
| Integra Contador (Serpro) | R$ 5–10 | ~R$ 100 | SITFIS, DAS, PARCSN, DCTFWeb, CND Conjunta — tudo via cert escritório |
| Infosimples | R$ 100 | R$ 1.200 | Franquia mínima R$ 100/mês. Volume real ~300 consultas (FGTS CRF + FGTS Digital + Estadual) |
| 2Captcha (Robô SEFAZ-GO) | ~R$ 30 | R$ 360 | Cloudflare Turnstile + portais SEFAZ |
| Focus NFe | conforme plano | — | DF-e + emissão (não confirmado) |
| **Total estimado** | **~R$ 150/mês** | **~R$ 1.800/ano** | — |

## Como subir o ambiente

```bash
# Backend
cd C:\dev\pac-xml-downloader\backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend
cd C:\dev\pac-xml-downloader\frontend
npm run dev

# Login: admin@pacxml.com.br / admin123
```

## Próximas frentes (backlog priorizado)

1. **[AMANHÃ] GitHub + Docker + Easypanel auto-deploy** — VPS2 (IP 72.62.111.136) já tem Easypanel + frontend up. Faltam: repo GitHub, Dockerfiles, conectar Easypanel ao Git
2. **Setup Supabase Postgres** — connection string pra DATABASE_URL de prod
3. **Resolver token Infosimples 601** — destrava CND FGTS, Estadual e Guia FGTS Digital
4. **Testes batch multi-empresa** — escalar para 10+ empresas reais (3 já com cert A1)
5. **#20** DAS valor real no sync — GERARDASCOBRANCA17 por compet.
6. **#22** PARCSN OBTERPARC164 — investigar ER_N002
7. **Cron mensal FGTS Digital** automático (similar Robô SEFAZ-GO)
8. **Comprar domínio + Let's Encrypt SSL** — quando VPS estável
9. **Multi-UF agente SEFAZ** (SP) — quando expandir
