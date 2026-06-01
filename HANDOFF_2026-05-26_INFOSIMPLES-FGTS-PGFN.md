# Handoff 26/05/2026 — Integração Infosimples + FGTS Digital + PGFN manual

**Data:** 26/05/2026
**Sessão anterior:** `HANDOFF_2026-05-25_PARTE-2_DASHBOARD-ROBO.md`
**Status:** ✅ Tudo funcional em mock. Falta apenas token Infosimples válido pra modo real.
**Próximo:** Token + testes batch com mais empresas

---

## 1. O que ficou pronto hoje

### 1.1 Provider Infosimples (`app/providers/infosimples.py`)
- Classe `InfosimplesProvider` stateless com session HTTP
- **Auth via form-encoded** (NÃO json — bug típico que pegamos no primeiro request real)
- Token + `timeout` no body, retry conservador (máx 2x) pra não queimar pré-pago
- Mapeamento de erros tipados (5 exceções):
  - `InfosimplesProdutoNaoHabilitado` (code 703) → 503 com instrução
  - `InfosimplesSaldoInsuficiente` (code 701/702) → 402 Payment Required
  - `InfosimplesCnpjInvalido` (612/613/614) → 400, NÃO retry
  - `InfosimplesRateLimit` (429) → retry após 30s
  - `InfosimplesTimeout` (820/821/822) → retry 1x
- Mocks determinísticos por (CNPJ, tipo) — dev local sem queimar saldo

**Métodos públicos finais (escopo enxuto):**
- `crf_fgts(cnpj)` → CRF Caixa (endpoint `/consultas/caixa/regularidade`)
- `cnd_sefaz_estadual(cnpj, uf)` → CND Estadual (endpoint `/consultas/sefaz/{uf}/certidao-debitos`)
- `fgts_emitir_guia_rapida(cnpj_representado, periodo)` → emite guia FGTS Digital (modo Procurador)
- `fgts_consultar_guias(cnpj_representado, periodo, pagina)` → histórico de guias FGTS

### 1.2 Cache TTL (`app/services/infosimples_cache.py` + tabela `cache_infosimples`)
- TTL dinâmico baseado em situação:
  - CND **VALIDA** (vence > 30d) → cache **30 dias**
  - CND **A_VENCER** (vence ≤ 30d) → cache **7 dias**
  - CND **VENCIDA** → cache **1 dia** (re-tenta diariamente)
  - PGFN parcelamentos → cache **7 dias** sempre
- `get_or_call(force=False)` — `force=True` bypassa cache (custa consulta)
- `invalidar(cnpj, endpoint)` — limpa cache manualmente

### 1.3 Migração CND para Infosimples (`CndRoboService`)
Roteamento final por tipo de certidão:

| Tipo CND | Provider | Endpoint | Custo |
|---|---|---|---|
| `FEDERAL` (60d, uso interno) | **Integra Contador** | SITFIS (SOLICITARPROTOCOLO91 + RELATORIOSITFIS92) | ~R$ 0,03 |
| `FEDERAL_OFICIAL` (180d, licitação/banco) | **Integra Contador** | mesmo SITFIS, validade 180d | ~R$ 0,03 |
| `FGTS` (30d) | **Infosimples** | `/consultas/caixa/regularidade` | R$ 0,20 |
| `ESTADUAL` (180d, por UF) | **Infosimples** | `/consultas/sefaz/{uf}/certidao-debitos` | R$ 0,20 |
| `TRABALHISTA` (180d) | Manual | — | R$ 0 |
| `MUNICIPAL` | Manual | — | R$ 0 |

Decisões:
- **CND Conjunta RFB+PGFN** voltou pro Integra Contador (mais barato, dados são os mesmos do SITFIS)
- **CNDT Trabalhista** saiu do Infosimples (consultas raras = não compensa pré-pago recorrente, fica manual)

### 1.4 PGFN Parcelamentos — cadastro MANUAL
**Por quê manual?** Infosimples não tem produto pra PGFN. Serpro também não. Sem alternativa automatizada hoje.

- Modelo `ParcelamentoPgfn` (similar a PARCSN, mas `numero` é String pra aceitar alfanumérico)
- Migration `20260526_0017_infosimples_pgfn.py` cria `parcelamentos_pgfn` + `cache_infosimples`
- Service `ParcelamentoPgfnService` com CRUD (criar/atualizar/deletar/marcar_baixado/listar)
- Rotas REST `/parcelamentos-pgfn`:
  - `GET /empresa/{id}` lista da empresa
  - `GET /ativos` dashboard global
  - `POST /empresa/{id}` cria
  - `PUT /{id}` edita
  - `POST /{id}/baixar` marca como `nao_listado_mais` (mantém histórico)
  - `DELETE /{id}` remove
- Frontend `/parcelamentos-pgfn` com formulário rico:
  - Dropdown empresa, número, modalidade (7 opções pré-cadastradas: Ordinário, Transação 13.988, Excepcional, PERT, PRR, Simplificado, Outros), data pedido, situação, valor total, valor pago, qtd parcelas, parcelas pagas
  - Tabela com botões ✎ (editar) ✓ (marcar baixado) ✕ (deletar)
  - Cliente copia dados do extrato REGULARIZE manualmente

**Fontes futuras (não implementadas, pra investigar depois):**
- Parser do PDF SITFIS (Integra Contador) — SITFIS já lista débitos PGFN, parsing extrairia parcelamentos
- Scraper REGULARIZE (Playwright + 2captcha) — caro de manter
- PARC-PAEX da RFB (em prospecção, aguardar)

### 1.5 FGTS Digital — Emissão de Guias (NOVO! modo Procurador)
**Setup**: cert A1 do escritório já cadastrado no painel Infosimples. Toda chamada usa esse cert pra autenticar via procuração eletrônica gov.br em nome do cliente. **Não precisa cadastrar credencial gov.br por empresa**.

- Modelo `GuiaFgts` (único por `empresa_id + periodo`)
- Migration `20260526_0018_guia_fgts.py`
- Service `GuiaFgtsService`:
  - `emitir_mensal(empresa_id, periodo)` — chama provider, upsert no DB, baixa PDF
  - `consultar_historico(empresa_id, periodo, pagina)` — lista guias direto no Infosimples
  - `listar_empresa(empresa_id)` — guias locais da empresa
  - `listar_todas_pendentes()` — dashboard global de não-pagas
  - `marcar_paga(guia_id, data_pagamento)`
- Rotas REST `/guias-fgts`:
  - `POST /empresa/{id}/emitir` (payload: `{periodo: "YYYYMM"}`)
  - `GET /empresa/{id}` lista local
  - `GET /pendentes` dashboard global
  - `GET /empresa/{id}/historico-infosimples` consulta API direta
  - `POST /{id}/marcar-paga`
  - `GET /{id}/pdf` baixa PDF salvo em `storage/guias_fgts/{cnpj}/`
- Frontend `/fgts`:
  - Dropdown empresa + input competência YYYYMM (default mês anterior)
  - Botão "▶ Emitir guia (R$ 0,20)" com confirmação
  - Tabela: competência, vencimento, total, trabalhadores, status (emitida/paga/vencida + dias), PDF, ✓ marcar paga
  - Dashboard global rodapé: pendentes ordenadas por vencimento

**Re-emissão do mesmo período atualiza valores** (caso houve admissão/demissão no mês).

### 1.6 Dashboard estendido (`/dashboard/resumo` + `/dashboard/por-empresa`)
- Card **PGFN (Dívida Ativa)** na linha 3: ativos, valor a pagar (total - pago)
- Coluna **PGFN** na tabela "Visão por empresa" (pill amber se tem)
- Tudo com guard `Promise.allSettled` — backend desatualizado não derruba dashboard

### 1.7 Correções de bug pegas durante implementação
| # | Bug | Fix |
|---|---|---|
| 41 | Provider mandando `json=payload` mas Infosimples espera **form-encoded** | Trocar `requests.post(json=)` → `data=`. Adicionar `timeout` no body |
| 42 | Endpoint FGTS errado (`/caixa/fgts`) e parser não pegava `crf`/`validade_fim_data` | Endpoint correto `/caixa/regularidade` + parser multi-field defensivo |
| 43 | CND Conjunta RFB+PGFN duplicada (Infosimples vs Integra) | Removida do Infosimples, fica no Integra (SITFIS) |
| 44 | CNDT consulta rara não compensava custo recorrente | Removida do Infosimples, vira cadastro manual |
| 46 | Preço `R$ 0,40` chutado em vários arquivos | Corrigido pra `R$ 0,20` (faixa real 1-500/mês) |

---

## 2. Custo real (recalculado com preço correto)

**Tabela de faixas Infosimples (pré-pago):**

| Volume mensal | Preço/consulta |
|---|---|
| 1–500 | R$ 0,20 |
| 501–2.000 | R$ 0,16 |
| 2.001–5.000 | R$ 0,14 |
| 5.001–10.000 | R$ 0,13 |
| 10.001–30.000 | R$ 0,11 |
| 30.001+ | R$ 0,10 ou menos |

**Franquia mínima R$ 100/mês** mesmo sem uso.

**Estimativa pro escritório (120 empresas ativas):**

| Consulta | Frequência | Volume/mês | Custo mensal |
|---|---|---|---|
| CRF FGTS | mensal | 120 | R$ 24,00 |
| CND Estadual (renova 180d) | bimestral médio | ~60 | R$ 12,00 |
| Guia FGTS Digital | mensal | 120 | R$ 24,00 |
| **Subtotal real** | — | **~300/mês** | **R$ 60,00** |
| **Pago (franquia mínima)** | — | — | **R$ 100,00** |

**Custo anual garantido: R$ 1.200**. Sobra orçamento dentro da faixa de R$ 0,20 pra escalar até 500 consultas/mês sem mudar de tier.

**Economia consolidada vs plano antigo (Playwright + 2captcha + duplicação de CND Conjunta):** ~R$ 533/ano.

---

## 3. Arquivos novos/modificados hoje

### Backend (criados)
- `app/providers/infosimples.py` (~830 linhas)
- `app/services/infosimples_cache.py`
- `app/services/infosimples_service.py`
- `app/models/cache_infosimples.py`
- `app/models/parcelamento_pgfn.py`
- `app/models/guia_fgts.py`
- `app/services/parcelamento_pgfn_service.py`
- `app/services/guia_fgts_service.py`
- `app/schemas/parcelamento_pgfn_schema.py`
- `app/schemas/guia_fgts_schema.py`
- `app/routes/parcelamentos_pgfn.py`
- `app/routes/guias_fgts.py`
- `alembic/versions/20260526_0017_infosimples_pgfn.py`
- `alembic/versions/20260526_0018_guia_fgts.py`

### Backend (modificados)
- `app/config.py` — settings Infosimples (token, base_url, timeout, ttls)
- `app/services/cnd_robo_service.py` — Infosimples no lugar do velho SefazRobotProvider
- `app/routes/certidoes.py` — aceita tipo ESTADUAL
- `app/routes/dashboard.py` — agregação PGFN + coluna por-empresa
- `app/models/__init__.py` — registra modelos novos
- `app/main.py` — registra rotas novas

### Frontend (criados)
- `lib/parcelamentos-pgfn.ts`
- `lib/guias-fgts.ts`
- `app/parcelamentos-pgfn/page.tsx`
- `app/fgts/page.tsx`

### Frontend (modificados)
- `lib/dashboard.ts` — campo `pgfn?` no resumo + `pgfn_ativos` por empresa
- `app/page.tsx` — card PGFN + coluna PGFN na visão por empresa
- `components/app-header.tsx` — rename Parcelamentos→PARCSN, add PGFN, add FGTS

---

## 4. Tasks fechadas hoje

| # | Task | Status |
|---|---|---|
| #15 | PGFN parcelamentos (era via Serpro, virou manual) | ✅ |
| #34 | Provider Infosimples base | ✅ |
| #35 | Cache TTL agressivo (CND 30d/7d/1d, PGFN 7d) | ✅ |
| #36 | Migrar CndRoboService → Infosimples (FGTS, ESTADUAL) | ✅ |
| #37 | Modelo ParcelamentoPgfn + migration | ✅ |
| #38 | ParcelamentoPgfnService + rota | ✅ |
| #39 | Frontend lib + página `/parcelamentos-pgfn` | ✅ |
| #40 | Dashboard card PGFN + coluna na Visão por empresa | ✅ |
| #41 | FIX form-encoded + SEFAZ Estadual | ✅ |
| #42 | FIX endpoint CRF correto + parser fields | ✅ |
| #43 | FIX CND Conjunta volta pra Integra Contador | ✅ |
| #44 | Remover CNDT + PGFN manual | ✅ |
| #45 | FGTS Digital emitir/consultar (modo Procurador) | ✅ |
| #46 | Atualizar preços R$ 0,40 → R$ 0,20 | ✅ |

---

## 5. Pendências (próxima sessão)

### Bloqueio imediato
- [ ] **Token Infosimples 601** — Franklim precisa colocar token válido no `.env` (sem aspas, sem espaço, sem quebra). Verificar com `curl direto` se persistir.

### Após token válido
- [ ] Smoke test real: 1 emissão FGTS + 1 CRF + 1 CND Estadual de 1 empresa real → confirmar valores, vencimentos, PDFs salvos
- [ ] Ativar produtos no painel Infosimples se algum responder 703:
  - CRF FGTS (`/consultas/caixa/regularidade`)
  - SEFAZ-GO (`/consultas/sefaz/go/certidao-debitos`)
  - FGTS Digital (`/consultas/fgts/guia-rapida` + `/consultas/fgts/guia`)
- [ ] Cron mensal pra emitir guia FGTS automática (similar ao cron do Robô SEFAZ-GO)
- [ ] Testes batch com 10+ empresas — confirmar que Infosimples não quebra em volume

### Backlog
- [ ] **#20** DAS valor real no sync (Integra Contador GERARDASCOBRANCA17 por compet.)
- [ ] **#22** PARCSN OBTERPARC164 (ER_N002 — investigar payload)
- [ ] Card FGTS no dashboard inicial (similar ao PGFN)
- [ ] Multi-UF agente SEFAZ (SP) — quando expandir além de GO
- [ ] Deploy VPS Hostinger (quando Infosimples estiver validado em produção)

---

## 6. Como subir o ambiente amanhã

### Backend
```bash
cd C:\dev\pac-xml-downloader\backend
# Aplica migrations se houver nova
python -m alembic upgrade head
# Sobe servidor
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend
```bash
cd C:\dev\pac-xml-downloader\frontend
npm run dev
```

### `.env` essencial
```
# Modo eager (dev sem Celery)
CELERY_TASK_ALWAYS_EAGER=true

# Integra Contador (Serpro) — REAL
USE_MOCK_INTEGRA=false
SERPRO_CONSUMER_KEY=...
SERPRO_CONSUMER_SECRET=...
SERPRO_CERT_PATH=C:\caminho\para\cert\escritorio.pfx
SERPRO_CERT_PASSWORD=...
SERPRO_CONTRATANTE_CNPJ=37165535000122
SERPRO_AUTOR_PEDIDO_CNPJ=37165535000122

# Infosimples — PENDENTE token válido
USE_MOCK_INFOSIMPLES=false  # vira true se não tiver token
INFOSIMPLES_TOKEN=sqqq...XXXXXX   # ← resolver o 601 aqui

# Focus NFe
USE_MOCK_FOCUS_NFE=false
FOCUS_MASTER_TOKEN=...
```

### Login
- `admin@pacxml.com.br` / `admin123`

### Empresas cadastradas hoje
- **#5** JOVELINO E ACILDA LTDA (10930732000134, UF GO) — cert A1 ✅
- **#6** INDUSTRIA DE LATICINIO CLAVEAUX LTDA (01060996000193, UF GO) — cert A1 ✅
- **#7** AGIMED COMERCIO DE EQUIPAMENTOS LTDA (03852519000196, UF GO) — cert A1 ✅ (matriz com 3 filiais)
- **#8** TESTE PGFN MOCK LTDA (99999999000000) — só pra teste PGFN, pode deletar
