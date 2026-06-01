# Handoff 25/05/2026 — Parte 2: Dashboard consolidado + Robô SEFAZ-GO multi-empresa

**Data:** 25/05/2026 (sessão noturna, continuação da Parte 1)
**Status:** ✅ Dashboard consolidado funcional + Robô SEFAZ-GO validado em batch (3 empresas, matriz com filiais incluso)
**Próximo:** PGFN parcelamentos + CNDs faltantes via **Infosimples** (decidido)

Continuação de `HANDOFF_2026-05-25_PRODUCAO-COMPLETA.md`. Cobre o que rolou DEPOIS do save daquela MD.

---

## 1. O que ficou pronto hoje (Parte 2)

### 1.1 Dashboard consolidado (`/`)
Tela inicial ganhou **3 frentes novas**:

- **Linha 3 de cards** com indicadores Serpro/operacionais:
  - **DAS Simples**: qtd atrasadas + valor + qtd vencendo 30d (cores: rose → amber → emerald)
  - **Parcelamentos PARCSN**: total ativos + parcelas restantes
  - **DCTFWeb mês**: emitidas + empresas pendentes
  - **Robô SEFAZ-GO**: última execução (status/persistidos), execuções em andamento

- **Tabela "Visão por empresa"** (`/dashboard/por-empresa`): uma linha por empresa ativa com 8 colunas:
  - Razão social (link clicável pra `/empresas/{id}`)
  - UF, NFes mês, DAS atrasadas (qtd · valor), PARCSN ativos
  - DCTFWeb mês (✓/pendente), Cert A1 (válido/vencendo/vencido/ausente), Última execução do robô (data + status + persistidos)

- **Tolerância a falha parcial**: `Promise.allSettled` substituiu `Promise.all`. Se `/por-empresa` 404 (backend antigo), só a tabela some — o resto do dashboard continua. Tipos opcionais (`das_simples?:`) no `lib/dashboard.ts` protegem contra crash.

### 1.2 Robô SEFAZ-GO: filtro de empresa + período na UI
Substituí o botão simples "Rodar agora" no header por um **painel completo** (`/robo-sefaz`):
- Dropdown **empresa** (default "Todas (N com cert A1)" + uma opção por empresa elegível) — filtra inativas e sem cert
- Date pickers **início/fim** (default = mês anterior, igual ao agente sem args)
- Validação cliente: erro se início > fim
- Toast confirma com nome da empresa + período: `"Robô disparado! Execução #X criada (RAZÃO SOCIAL · DD/MM a DD/MM)"`
- Aviso se nenhuma empresa tem cert A1 cadastrado

Backend (`/robo-sefaz/disparar`) já aceitava `empresa_id` + período via `DispararRoboSefazPayload` desde antes — só faltava UI.

### 1.3 Robô SEFAZ-GO: AGIMED (matriz com filiais) end-to-end ✓
**3 bugs em cascata** corrigidos no `agent/sefaz-go/pac_sefaz_agent.py`:

#### Bug A: Modal de confirmação com timeout
- **Sintoma**: `TimeoutError('Locator.click: Timeout 60000ms exceeded — waiting for button:has-text(\'Baixar\'):not(:has-text(\'todos\'))`)
- **Fix**: 5 seletores fallback em sequência (`"Baixar"`, `"Confirmar"`, `"OK"`, `button[type='submit']`, `.modal button`) com 15s cada. Se nenhum funcionar, salva `screenshot + HTML` em `logs/debug/modal_sem_confirmar_*.{png,html}`.

#### Bug B: "Sem Resultados!" virava timeout no modal
- **Sintoma**: portal devolvia banner "Sem Resultados!" + tabela vazia, mas o botão "Baixar todos os arquivos" continuava visível no rodapé. Agente clicava, modal abria vazio, e o "Baixar" interno nunca aparecia.
- **Fix** (passo 7.5): depois de Pesquisar, faz `page.evaluate` procurando regex `/sem\s+resultados/gi` no `body.innerText`. Se acha → retorna `sucesso=True, sem_resultados=True` (mesmo flow de "Sem notas" que já existia).
- **Confirmado pelo screenshot debug**: filial 0277 da AGIMED genuinamente não tem NFes em abril.

#### Bug C (CRÍTICO): CNPJ errado por causa de filiais
- **Sintoma**: AGIMED matriz `0196` cadastrada no PAC, mas pesquisa sempre devolvia "Sem Resultados".
- **Causa**: cert A1 da AGIMED autoriza 4 CNPJs (`0196` matriz + `0277/0358/0439` filiais). Portal SEFAZ-GO popula `<select id="cmpCnpj">` com todas. Sem seleção explícita, browser usa **primeira opção** = filial 0277 (sem movimento).
- **Fix** (passo 4.5): antes de preencher datas, detecta `#cmpCnpj`, lê opções via JS, e `select_option(empresa.cnpj)`. Loga `cnpj_selecionado` com lista de opções pra auditoria.
- **Por que CLAVEAUX/JOVELINO funcionavam**: certs delas autorizam 1 CNPJ só (matriz sem filiais), então dropdown nem aparece.

#### Bug D: Portal não navega pra histórico sozinho em CNPJs grandes
- **Sintoma**: após confirmar modal, agente ficava na `/consulta-publica/resultado` polindo IDs no formato `{cnpj}_{ddmmyyyy}_{ddmmyyyy}_{seq}.zip` por 10min, mas a página listava NFes individuais (`52260403852519000196...`) — formato totalmente diferente.
- **Causa**: em CNPJs com volume alto, portal não auto-navega pra `/historico` após o click. Usuário tem que clicar manualmente em "Histórico de Downloads de XMLs" no rodapé.
- **Fix** (passo 11.5): checa `page.url`; se NÃO contém `/historico`, tenta 5 variações de seletor pra clicar; fallback `page.goto(/historico)` direto.

**Resultado**: AGIMED matriz passou de "11min timeout" → **"OK 55 XMLs em 36s"** em 1 sessão.

### 1.4 UI: label do robô mostra duplicados
- Antes: `"OK (0 XMLs)"` — confundia em batches repetidos
- Agora:
  - `"OK (N novos, Y dup)"` quando misto
  - `"OK (N já existiam)"` quando 100% duplicado (mais comum em re-execuções)
  - `"OK (N XMLs)"` na primeira vez

### 1.5 Outros fixes pequenos
- `<body suppressHydrationWarning>` no `layout.tsx` — silencia erro de hidratação causado por extensões do Chrome (Scribe, Grammarly, etc.) injetando atributos antes do React rodar.
- Dashboard: cards Linha 3 com guard `resumo.das_simples && resumo.parcsn && ...` pra não crashar se backend devolver payload velho.

---

## 2. Validação batch end-to-end

Execução #8 (manual, "Todas as empresas", 01/04/2026 a 30/04/2026):

| Empresa | CNPJ | Status | Duração | Resultado real (do `resumo_*.json`) |
|---|---|---|---|---|
| AGIMED | 03852519000196 (matriz) | ✓ Concluído | 31s | 55 XMLs (todos duplicados — execução #7) |
| CLAVEAUX | 01060996000193 | ✓ Concluído | 46s | 829+ XMLs (todos duplicados — execução anterior) |
| JOVELINO | 10930732000134 | ✓ Concluído | 30s | 1 XML (duplicado) |

**Total batch: ~107s pras 3 empresas**. Dedup funcionou (unique constraint `empresa_id + chave_acesso`).

Task #14 ("testar SEFAZ-GO com várias empresas") ✅ pode ser fechada. Robô pronto pra escalar pras 120.

---

## 3. Arquivos tocados na Parte 2

### Backend
- `backend/app/routes/dashboard.py` — endpoint `/resumo` estendido (DAS/PARCSN/DCTFWeb/robô) + novo `/por-empresa`

### Frontend
- `frontend/lib/dashboard.ts` — types opcionais + `listaPorEmpresa()`
- `frontend/app/page.tsx` — linha 3 de cards + tabela "Visão por empresa" + `Promise.allSettled`
- `frontend/app/layout.tsx` — `suppressHydrationWarning`
- `frontend/app/robo-sefaz/page.tsx` — painel "Rodar agora" com dropdown empresa + período + label dup/novos
- `frontend/lib/robo-sefaz.ts` — `DetalheEmpresa.upload_pac.total_arquivos` opcional

### Agente
- `agent/sefaz-go/pac_sefaz_agent.py` — 4 mudanças:
  1. Passo 4.5: `selectOption(empresa.cnpj)` no `#cmpCnpj`
  2. Passo 7.5: detecta "Sem Resultados" antes do modal
  3. Passo 10: 5 candidatos pro botão "Baixar" do modal + debug screenshot
  4. Passo 11.5: navega pra `/historico` se portal não navegar sozinho

---

## 4. Tasks fechadas hoje (Parte 2)

| # | Task | Status |
|---|---|---|
| #23 | Backend: agregação DAS/PARCSN/DCTFWeb/robô no `/dashboard/resumo` | ✅ |
| #24 | Backend: endpoint `/dashboard/por-empresa` | ✅ |
| #25 | Frontend: `lib/dashboard.ts` com novos campos | ✅ |
| #26 | Frontend: cards + tabela consolidada no dashboard | ✅ |
| #27 | UI: filtro de empresa + período no Robô SEFAZ | ✅ |
| #28 | Fix dashboard tolerar 404 + modal robusto | ✅ |
| #29 | Fix AGIMED: detectar "Sem Resultados" antes do modal | ✅ |
| #30 | Fix AGIMED: selecionar CNPJ correto no dropdown | ✅ |
| #31 | Fix AGIMED: navegar para Histórico após confirmar modal | ✅ |
| #32 | UI: label do robô mostra duplicados além de persistidos | ✅ |
| **#14** | Pré-produção: testar SEFAZ-GO multi-empresa | ✅ batch #8 validado |

---

## 5. Próximo nível (AMANHÃ): PGFN + CNDs via Infosimples

### 5.1 Decisão tomada
Comparativo já registrado no `HANDOFF_2026-05-13_CND-RESEARCH.md` seção 2:

| Opção | Custo 120 empresas/ano | Esforço impl | Manutenção |
|---|---|---|---|
| A) Playwright + 2captcha | R$ 360/ano | **Alto** (3 scrapers) | Quebra a cada mudança de portal |
| **B) Infosimples API** ← escolhida | **R$ 500-800/ano** | **Baixo** (HTTP simples) | Eles que se viram |
| C) Serpro CCG | só p/ próprio CNPJ | Médio | Não cobre 3rd party |

### 5.2 Escopo Infosimples
1. **PGFN parcelamentos** (Dívida Ativa)
   - Hoje sem cobertura no PAC (task #15 pendente)
   - Endpoints Serpro só cobrem PARCSN (Simples) — PGFN não tem API direta
   - Infosimples tem: `consultas-publicas/pgfn-parcelamentos` ou similar
   - Output esperado: lista de parcelamentos ativos + saldo + nº parcelas + DARFs por parcela

2. **CND faltantes** (que estão mocked hoje em `app/services/cnd_robo_service.py`)
   - **FGTS/CRF** (Caixa)
   - **CNDT** (Trabalhista TST)
   - **CND Conjunta RFB+PGFN** (uso externo: licitação, banco)
   - **Estadual SEFAZ-GO** (e outras UFs futuras)
   - **Municipal Goiânia** (e outras prefeituras)

### 5.3 Tasks pra abrir amanhã
- [ ] **Criar `app/providers/infosimples.py`** — HTTP simples com `requests`, auth via API token no `.env`, retry exponential, schema das respostas (JSON)
- [ ] **Refatorar `cnd_robo_service.py`** — trocar mocks por chamadas ao novo provider
- [ ] **Novo modelo `parcelamento_pgfn`** (similar ao `parcelamento_simples`) + migration
- [ ] **`/parcelamentos-pgfn` rota + tela** (espelhar `/parcelamentos-simples`)
- [ ] **Cron mensal** pra sync de CNDs + PGFN (similar ao robô SEFAZ)
- [ ] **Card "PGFN" no dashboard** (similar ao PARCSN)
- [ ] **Coluna "PGFN ativos" na "Visão por empresa"** do dashboard

### 5.4 Pré-requisitos pra amanhã (Franklim já tem?)
- [ ] Conta Infosimples criada (dashboard.infosimples.com)
- [ ] **API Token** gerado no painel (pra `.env` `INFOSIMPLES_TOKEN=...`)
- [ ] Crédito mínimo no saldo (eles cobram por volume: R$ 0,20 na faixa 1-500/mês; R$ 0,16 acima de 500; etc. Franquia mínima R$ 100/mês)
- [ ] Lista priorizada: quais 3-4 produtos do Infosimples atacar primeiro?

---

## 6. Outras pendências (não bloqueia o trabalho de amanhã)

| # | Item | Notas |
|---|---|---|
| #15 | PGFN parcelamentos | **Atacar amanhã via Infosimples** |
| #20 | DAS valor real no sync | Chamar GERARDASCOBRANCA17 por compet. — fica pra próximo |
| #22 | PARCSN OBTERPARC164 | ER_N002 `numeroParcelamento not found` — investigar payload |
| — | Deploy VPS Hostinger | Depois que Infosimples ficar pronto |
| — | Alertas email/whatsapp parcelas vencendo | Backlog |
| — | Multi-UF agente SEFAZ (SP) | Backlog |

---

## 7. Estado atual da infra (sem mudança desde Parte 1)

- Backend FastAPI rodando local `127.0.0.1:8000`, `USE_MOCK_INTEGRA=false`, `CELERY_TASK_ALWAYS_EAGER=true`
- Frontend Next.js `localhost:3000`
- Storage local: `backend/storage/{xmls,guias,parcsn,guias_dctfweb}/...`
- 3 empresas com cert A1 ativo: JOVELINO (5), CLAVEAUX (6), AGIMED (matriz + 3 filiais autorizadas)

**Reiniciar amanhã**: `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` + `cd frontend && npm run dev`. Login admin: `admin@pacxml.com.br / admin123`.
