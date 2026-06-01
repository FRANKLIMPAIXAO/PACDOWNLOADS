# Handoff 25/05/2026 — Sistema PAC funcional end-to-end com Serpro REAL

**Data:** 25/05/2026
**Status:** ✅ Robô SEFAZ-GO + Integra Contador (DAS, PARCSN, DCTFWeb) + DANFE local — TODOS validados em produção real.

Continuação dos handoffs anteriores. Esse aqui consolida o que ficou pronto **hoje** e o estado real do sistema.

---

## 1. O que rodou em PRODUÇÃO REAL hoje

### 1.1 Robô SEFAZ-GO (CLAVEAUX + JOVELINO)
- **CLAVEAUX**: 829 NFes de saída baixadas em **51s** (período 01-30/04/2026)
- **JOVELINO**: 0 NFes (empresa sem movimento NFe no mês)
- Fluxo end-to-end: cert A1 → Playwright → 2Captcha → portal SEFAZ-GO → ZIP → upload PAC → persistência

### 1.2 Integra Contador (Serpro real)
- **DAS Simples (CONSDECLARACAO13)**: 12 declarações 2025 da JOVELINO, 9 atrasadas detectadas
- **DAS atualizada (GERARDASCOBRANCA17)**: R$ 1.298,21 com Selic+mora — PDF 156KB
- **Parcelamentos PARCSN (PEDIDOSPARC163)**: 7 parcelamentos importados; DAS parcela 05/2026 emitida (R$ 322,85, PDF 159KB)
- **DCTFWeb (GERARGUIA31)**: guia categoria 40 GERAL_MENSAL 04/2025 emitida (PDF 117KB)

### 1.3 DANFE PDF local
- Lib `brazilfiscalreport` integrada → gera DANFE em ~0.5s a partir de XML local
- Cache automático no disco (`storage/xmls/{cnpj}/nfe/.../<chave>.pdf`)
- Funciona pras 829 NFes de saída da CLAVEAUX

---

## 2. Bugs corrigidos hoje (sessão dia 25)

### 2.1 Cadastro de empresa quebrava ao salvar
- **Sintoma:** `TypeError: naturezaJuridicaCodigo.trim is not a function`
- **Causa:** BrasilAPI devolve `natureza_juridica_codigo` como `Number` (`2062`), mas o React esperava `string`
- **Fix:** helper `safeTrim()` aceita qualquer tipo + `setSeVazio` agora sempre converte com `String(novo)` antes de salvar no state
- **Arquivo:** `frontend/app/empresas/novo/page.tsx`

### 2.2 "Rodar agora" do Robô SEFAZ dava erro CORS
- **Sintoma:** navegador bloqueava com CORS error quando Celery+Redis não estavam rodando
- **Causa:** `kombu.OperationalError` levantava antes de adicionar headers CORS
- **Fix:** try/except retorna HTTP 503 com mensagem amigável + grava execução com `status='erro'` no histórico
- **Arquivo:** `backend/app/routes/robo_sefaz.py`

### 2.3 Duração negativa na execução do robô (-10691s)
- **Causa:** `iniciado_em` vem do `server_default=func.now()` do DB (timezone-aware UTC), mas `datetime.now()` Python é naive (hora local BR-3h). Diferença dava negativo
- **Fix:**
  - `duracao_segundos` property normaliza timezone antes de subtrair + `max(0, delta)` por segurança
  - Helper `_now_compatible_with(ref)` devolve `datetime.now()` no mesmo formato (naive/aware) que `ref`
  - Aplicado em `RoboSefazService._falhar()`, `executar()`, e na route `disparar_robo`
- **Arquivos:** `backend/app/models/execucao_robo_sefaz.py`, `backend/app/services/robo_sefaz_service.py`, `backend/app/routes/robo_sefaz.py`

### 2.4 Celery+Redis off em dev local — "Rodar agora" precisa rodar
- **Solução:** `CELERY_TASK_ALWAYS_EAGER=true` no `.env` faz `.delay()` rodar síncrono
- **Mas:** em eager mode a request HTTP ficaria travada por 3-5 min até o agent terminar
- **Fix complementar:** route detecta eager mode e dispara em `threading.Thread(daemon=True)` (fire-and-forget). Devolve HTTP 202 instantâneo
- **Em produção (VPS):** setar `CELERY_TASK_ALWAYS_EAGER=false` e subir Celery worker + beat normalmente. Sem mudar código
- **Arquivos:** `backend/.env`, `backend/app/workers/celery_app.py`, `backend/app/routes/robo_sefaz.py`

### 2.5 Agente baixava EVENTOS em vez de NFes (392 → 829)
- **Sintoma:** ZIP do agent tinha 392 arquivos `procEventoNFe` (cancelamentos + cartas de correção), faltavam ~400 NFes do mês
- **Causa:** modal de download do portal SEFAZ-GO tem 3 radios: "Documentos+Eventos", "Somente Documentos", "Somente Eventos". O código marcava cego `radios.nth(1)` que era "Somente Eventos"
- **Fix:** lê TODOS os radios + labels via JS, procura explicitamente o que tem "Documento" sem "Evento", loga tudo pra auditoria
- **Validação:** 392 eventos → 829 NFes em 51s
- **Arquivo:** `agent/sefaz-go/pac_sefaz_agent.py`

### 2.6 Botão "Manifestar" aparecia em NFes de SAÍDA
- **Conceito fiscal:** SAÍDAS (NFe própria) já estão completas na SEFAZ porque a empresa as autorizou — manifestação não se aplica. Só ENTRADAS (NFe que fornecedor emitiu CONTRA a empresa) precisam Ciência → Confirmação → permite baixar XML completo via Distribuição
- **Sintoma:** UI mostrava botão "Manifestar" pras 829 NFes da CLAVEAUX, o que tentaria manifestar NFes próprias (a SEFAZ rejeitaria)
- **Fix:**
  - Helper `ehSaidaPropria(doc)` detecta via `doc.origem === "emitida"` OU comparando CNPJ na chave (posições 6-20) com CNPJ da empresa
  - Saídas mostram pill cinza **"Saída"** com tooltip explicando
  - Contador "Manifestar X pendentes" ignora saídas
  - Schema backend agora devolve `origem` na resposta
- **Arquivos:** `frontend/app/documentos/page.tsx`, `frontend/lib/documentos.ts`, `backend/app/schemas/documento_schema.py`

### 2.7 PDF DANFE não vinha pras NFes de saída
- **Sintoma:** XML baixava mas PDF dava "Nenhum arquivo encontrado". Focus só devolve PDF de notas RECEBIDAS após manifestação
- **Fix:** instalada `brazilfiscalreport`. Rota `/documentos/{id}/pdf` detecta NFe de saída e gera DANFE localmente a partir do XML (com cache em disco)
- **Validação:** PDF 5.893 bytes gerado em ~0.5s
- **Arquivo:** `backend/app/routes/documentos.py`, dependência nova `brazilfiscalreport`

---

## 3. Tasks fechadas hoje

| # | Feature | Status |
|---|---|---|
| #16 | Parcelamentos Simples (PARCSN ordinário) | ✅ Validado Serpro real |
| #17 | DAS Simples Nacional atrasadas | ✅ Validado Serpro real |
| #18 | DAS atualizadas (Selic+mora) | ✅ Validado Serpro real |
| #19 | Descobrir nome correto CONSDECLARACAO13 | ✅ |
| #21 | DCTFWeb (ativa + andamento) | ✅ Validado Serpro real |
| **Novo** | Bug datepicker (frontend safeTrim) | ✅ |
| **Novo** | CORS 503 elegante no Rodar agora | ✅ |
| **Novo** | Duração negativa (timezone fix) | ✅ |
| **Novo** | Eager mode pra dev local sem Celery | ✅ |
| **Novo** | Radio errado do modal SEFAZ (392 eventos → 829 NFes) | ✅ |
| **Novo** | Saída/Entrada na UI (Manifestar só pra entradas) | ✅ |
| **Novo** | DANFE PDF local via brazilfiscalreport | ✅ |

---

## 4. Tasks pendentes

| # | Item | Bloqueio? |
|---|---|---|
| #13 | Testar SEFAZ-GO sem `--dry-run` ponta a ponta | ✅ Resolvido (CLAVEAUX = 829 XMLs persistidos) — pode marcar completed |
| #14 | Testar SEFAZ-GO com várias empresas | Funciona pra 2 empresas com cert A1; precisa cadastrar mais |
| #15 | Parcelamentos PGFN | **Sem API direta no Serpro.** Caminhos: (a) extrair PDF SITFIS via SOLICITARPROTOCOLO91; (b) scraping REGULARIZE; (c) PARC-PAEX (em prospecção) |
| #20 | DAS: trazer valor real no sync (hoje vem 0) | Solução: chamar GERARDASCOBRANCA17 pra cada competência durante o sync |
| #22 | PARCSN: enriquecer com OBTERPARC164 | Hoje dá `ER_N002: numeroParcelamento not found` — precisa investigar payload correto |

---

## 5. Arquivos e estado da infra

### Backend (FastAPI, porta 8000)
- ✅ Rodando local: `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- ✅ `USE_MOCK_INTEGRA=false` (Serpro REAL)
- ✅ `CELERY_TASK_ALWAYS_EAGER=true` (dev local; em VPS deixar false)

### Frontend (Next.js, porta 3000)
- ✅ Rodando local: `cd frontend && npm run dev`
- Menu: Dashboard, Empresas, Documentos, Apuracoes, Prevencao, Relatorios, **Robô SEFAZ**, **DAS Simples**, **Parcelamentos**, **DCTFWeb**

### Storage
- `backend/storage/xmls/{cnpj}/nfe/...` — XMLs e DANFE PDFs gerados
- `backend/storage/guias/{cnpj}/das_*.pdf` — DAS atualizadas
- `backend/storage/parcsn/{cnpj}/parcsn_*.pdf` — DAS de parcelas PARCSN
- `backend/storage/guias_dctfweb/{cnpj}/dctfweb_*.pdf` — Guias DCTFWeb

### Empresas cadastradas no DB
- **#5 JOVELINO E ACILDA LTDA** (10930732000134) — Cert A1: ✅
- **#6 INDUSTRIA DE LATICINIO CLAVEAUX LTDA** (01060996000193) — Cert A1: ✅ (829 NFes baixadas)

---

## 6. Próximos passos sugeridos

### Curto prazo (próxima sessão)
1. **#14** Cadastrar mais empresas + rodar SEFAZ-GO multi-empresa em batch
2. **#20** Sync DAS com valor real (chamar GERARDASCOBRANCA17 pra cada atrasada)
3. **#22** PARCSN OBTERPARC164 (investigar payload)
4. **#15** PGFN via SITFIS (parse PDF da situação fiscal)

### Médio prazo (preparar produção)
5. Subir VPS Hostinger: backend + frontend + Postgres + Redis + Celery worker + Celery beat
6. CRON real do dia 5 às 03h pra disparar Robô SEFAZ mensal automático
7. Criptografar `focus_token` da empresa em repouso (Fernet)
8. Multi-UF: começar SP (precisa criar `agent/sefaz-sp/` similar ao GO)

### Features novas
9. Página dashboard consolidada (todas as empresas + DAS atrasadas + parcelamentos vencendo + guias pendentes)
10. Alertas por email/whatsapp quando parcela DAS vence em 3 dias
11. Importação em massa de empresas via Excel
12. Backup automático SQLite (rotaciona 30 dias)
