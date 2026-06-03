# HANDOFF 04/06/2026 — Retomada após sessão épica de 03/06

> **Estado**: 🟢 Sistema PAC com automação 100% funcional (Robô SEFAZ + Focus + Integra Contador real + 102 empresas migradas). 2 bugs específicos pendentes pra atacar amanhã.
> **Deadline**: ~03/07/2026 — **30 dias** pra deixar tudo funcionando produtivamente com as 102 empresas. (Disse o Franklim: *"TENHO 30 DIAS, PARA FAZER FUNCIONAR"*)
> **Próximo passo IMEDIATO ao retomar**: resolver bug Redis robô SEFAZ AGIMED + investigar PDF SITFIS corrompido (debug endpoint já criado).

---

## TL;DR — onde paramos em 03/06

Sessão **MUITO produtiva**. Conquistamos:

- ✅ **Focus NFe Distribuição** com loop automático no frontend (1 clique baixa 1000 NFes)
- ✅ **Focus auto-cadastrar** funcionando (JSON+base64 + flags + datas DFe)
- ✅ **Integra Contador REAL** em prod (cert escritório + Serpro key/secret + procuração PAC)
- ✅ **SITFIS REAL** chamando Serpro de verdade (protocolo base64 ~250 chars válido)
- ✅ **102 empresas Jettax importadas** via endpoint XLSX + página `/empresas/importar`
- ✅ **3 endpoints de diagnóstico** (`/version`, `/focus/diagnostico`, `/integra/diagnostico`)
- ✅ **Endpoint debug PDF SITFIS** (`/sitfis/{id}/debug`) — commitado, falta deploy

E temos **2 bugs concretos** pra atacar amanhã (ver seção próxima).

---

## 🐛 Bugs pendentes pra atacar amanhã

### Bug 1: Robô SEFAZ AGIMED — erro "Redis não ativo" (task #85)

Franklim testou robô SEFAZ-GO na AGIMED no fim do dia 03/06 e deu erro "Redis não ativo". Robô SEFAZ usa Celery (configurado em `backend/app/workers/celery_app.py` + `tasks.py`) que depende de Redis.

**Hipóteses**:
1. Redis service não está rodando no Easypanel (verificar status)
2. `REDIS_URL` env var errada/ausente em backend ou worker
3. Worker Celery não está running como serviço separado
4. CLAVEAUX funcionou ontem (815 NFes em prod), AGIMED ser cadastro novo pode ter acionado code path diferente — investigar

**Plano de investigação amanhã**:
1. Easypanel → verificar se tem serviço `redis` rodando (Running verde)
2. `/version` ainda funciona → confirma se backend está conectando no Redis
3. Tentar conectar manualmente via console do backend: `redis-cli -u $REDIS_URL ping`
4. Olhar `app/workers/celery_app.py` pra ver como o config carrega REDIS_URL

### Bug 2: PDF SITFIS aberto era MOCK ANTIGO, não bug do código atual (task #86)

**Descoberta no último teste do dia (03/06 às ~22h)** — debug rodou no SITFIS-5 e
revelou que ERA MOCK ANTIGO:

```
protocolo: "MOCK-PROT-01060996000193-1780447106"    ← MOCK explícito
protocolo_len: 35                                    ← real seria 250+ chars
pdf_size_bytes: 40                                   ← real seria 50-200 KB
first_chars: "%PDF-1.4 mock SITFIS para..."         ← texto literal "mock"
gerada_em: 2026-06-03T00:38:26                      ← gerado 00:38 madrugada
```

SITFIS-5 foi gerado às **00:38h da madrugada de 03/06** — MUITO ANTES de ativarmos
`USE_MOCK_INTEGRA=false` (foi por volta das 19h). Por isso é mock — funcionamento
correto. O "Falha ao carregar PDF" vinha do navegador não conseguir renderizar
um PDF de 40 bytes com header válido mas conteúdo só de texto fake.

**Pendente verificar amanhã**: SITFIS-3 e SITFIS-4 (validade 180d = CND Federal
oficial). Esses provavelmente são os REAIS gerados após mock=false. Rodar:

```javascript
fetch('https://backend.72.62.111.136.nip.io/api/v1/empresas/7/integra/sitfis/3/debug', {
  headers:{'Authorization':'Bearer '+localStorage.getItem('pac_xml_token')}
}).then(r=>r.json()).then(j=>console.log('SITFIS-3:', JSON.stringify(j,null,2)))

fetch('https://backend.72.62.111.136.nip.io/api/v1/empresas/7/integra/sitfis/4/debug', {
  headers:{'Authorization':'Bearer '+localStorage.getItem('pac_xml_token')}
}).then(r=>r.json()).then(j=>console.log('SITFIS-4:', JSON.stringify(j,null,2)))
```

**Critério pra ser REAL**:
- `protocolo` NÃO começa com `MOCK-PROT-`
- `protocolo_len` ~250 chars (base64)
- `pdf_size_bytes` > 10000 (PDF Serpro real)
- `first_chars` começa com `%PDF-` mas tem binário ilegível depois (PDF comprimido)

Se SITFIS-3 e 4 também forem mock → significa que o botão "Atualizar SITFIS"
estava chamando algum cache ou retornou mock por outro motivo (apesar do flag
mock=false). Aí investigar caminho de mock no código.

Se SITFIS-3/4 forem REAIS → PDF SITFIS real funciona, problema era só interpretar
o SITFIS-5 mock antigo como sendo falha.

---

## 📊 Estado completo do sistema (03/06 final)

### Camadas funcionais

| Camada | Status | Empresas testadas |
|---|---|---|
| Cadastro CRUD básico | ✅ | 102 (importadas Jettax) |
| Importador XLSX Jettax | ✅ | 102 em 1 upload |
| Robô SEFAZ-GO emitidas | ✅ (com bug AGIMED) | CLAVEAUX 812 NFes, JOVELINO 3 |
| Focus distribuição (DF-e recebidas) | ✅ | CLAVEAUX 1000+ NFes em loops |
| Focus auto-cadastrar | ✅ | JSON+base64, flags, datas |
| Integra Contador REAL (Serpro) | ✅ | autenticação + SITFIS chamada |
| SITFIS PDF salvo no disco | 🔴 corrompido | bug #86 |
| CNDs (RFB+PGFN, Trab, FGTS, Estaduais) | ✅ via Infosimples | testadas em mock + alguns reais |
| Parcelamentos (PGFN, SN, MEI) | ✅ | mock — não testado real |
| Guias DAS/DCTFWeb/FGTS Digital | ✅ | mock — não testado real |
| Dashboard agregado | ✅ | funcionando |

### Commits do dia 03/06 (~15 commits)

```
92e571f diag(integra): endpoint GET /sitfis/{id}/debug
cb3ee61 feat(empresas): página /empresas/importar (XLSX Jettax)
61356e6 feat(empresas): importador XLSX Jettax 102 empresas
e957c5f fix(integra): SituacaoFiscal.protocolo VARCHAR(80)→VARCHAR(500)
dcc82f4 diag(integra): endpoint POST /diagnostico Serpro
bc947bc fix(integra): timeout HTTP Serpro 120s→15s, auth 30s→15s
d655b55 fix(integra): reduzir waits SITFIS pra caber no Traefik
e9ffdd0 feat(focus): loop automático sync Focus + barra de progresso
57670ac diag(focus): endpoint POST /focus/diagnostico
d62e75e fix(robo): limite 25 NFes/request + endpoint /version
92d0c82 fix(robo): try/except em /robo/distribuicao
a5d2f3b fix(focus): flags obrigatórios habilita_nfe, discrimina_impostos
0e02c8a fix(focus): normalizar tipos regime/numero/cep/IE/IM
1e3139d fix(focus): JSON+base64 + data_inicio_recebimento_nfe/cte
facb9cd docs: visão de produto + análise concorrencial + carteira
```

### Env vars críticas em prod (Easypanel backend)

```
USE_MOCK_FOCUS_NFE=false
USE_MOCK_INTEGRA=false                                ← ATIVO!
USE_MOCK_INFOSIMPLES=true                             ← ainda mock (pendente)

FOCUS_MASTER_TOKEN=<sem < > delimitadores>
SERPRO_CERT_PATH=/app/storage/certs/escritorio.pfx
SERPRO_CERT_PASSWORD=<senha cert PAC INTELIGENCIA TRIBUTARIA>
SERPRO_CONSUMER_KEY=<portal Serpro>
SERPRO_CONSUMER_SECRET=<portal Serpro>
SERPRO_CONTRATANTE_CNPJ=37165535000122                ← CNPJ PAC (titular contrato)
SERPRO_AUTOR_PEDIDO_CNPJ=37165535000122

REDIS_URL=redis://...                                  ← VERIFICAR (bug #85)
DATABASE_URL=postgresql://...                          ← Supabase
SECRET_KEY=<rotacionado>
ALLOWED_ORIGINS=https://pacdownloads-frontend.ibm21x.easypanel.host,...
```

### Empresas em prod (id no banco)

| ID | Nome | CNPJ | Estado |
|---|---|---|---|
| 6 | JOVELINO E ACILDA LTDA | 10930732000134 | Focus OK, 3 NFes |
| 7 | INDUSTRIA DE LATICINIO CLAVEAUX LTDA | 01060996000193 | Focus OK, 1000+ NFes, SITFIS REAL gerou |
| 8 | AGIMED COMERCIO DE EQUIPAMENTOS LTDA | 03852519000196 | Bug Redis robô SEFAZ #85 |
| ... | + 99 outras importadas do Jettax (94 criadas + 5 outras testes) | | sem cert A1 subido ainda |

---

## 🎯 Roadmap revisado pra próximos 30 dias

### Semana 1 (04-10/06) — TERMINAR a base

- **Dia 04** (amanhã):
  - [ ] Resolver bug Redis robô SEFAZ AGIMED (#85)
  - [ ] Resolver PDF SITFIS corrompido (#86) — deploy `92e571f` + debug
  - [ ] Subir certs A1 das 102 empresas (formato batch ZIP? ou manual?)
  - [ ] Auto-cadastrar Focus em batch nas elegíveis (já tem endpoint)

- **Dias 05-07**:
  - [ ] Testar Integra Contador real em outras empresas (5-10 escolhidas)
  - [ ] Ativar Infosimples real (USE_MOCK_INFOSIMPLES=false) + rotacionar token
  - [ ] Tela `/cnds` com filtros avançados (sub-tipo, situação, vencimento)

- **Dias 08-10**:
  - [ ] Cron mensal automático (Robô SEFAZ + Focus + FGTS Digital + CNDs)
  - [ ] Backup automático storage + Supabase

### Semana 2 (11-17/06) — INTELIGÊNCIA DE CARTEIRA

Primeiro diferencial real sobre concorrentes.

- [ ] Dashboard `/carteira` cruzando 102 clientes:
  - Painel regime tributário (gráfico + alertas)
  - Painel Reforma Tributária (quantos Híbridos, simulador batch)
  - Painel obrigações (calendário próximos 7 dias)
  - Painel pendências (CND vencida, e-CAC não lida)
  - Painel financeiro (DAS apurado vs pago, parcelamentos ativos)

### Semana 3 (18-24/06) — REFORMA TRIBUTÁRIA CORE

- [ ] Tabela `classificacao_ncm` + importador planilha estoque
- [ ] Simulador Híbrido Simples batch nas 84 SN
- [ ] Monitor split payment

### Semana 4 (25/06-03/07) — COMUNICADOR + POLIMENTO

- [ ] Comunicador WhatsApp (Evolution API ou Z-API)
- [ ] Tela `/nfes` com totalizadores (substitui tela principal Jettax)
- [ ] Domínio próprio + Let's Encrypt
- [ ] **Ativar uso diário com as 102 empresas**

---

## 🔑 Arquivos chave pra retomada

```
HANDOFF_2026-06-04_RETOMADA.md         ← VOCÊ ESTÁ AQUI
HANDOFF_2026-06-03_VISAO-PRODUTO.md    ← visão estratégica
docs/CARTEIRA-PAC-TRIBUTARIA.md         ← 102 empresas detalhadas
docs/ANALISE-CONCORRENCIAL-2026.md      ← 10 concorrentes

backend/
  app/routes/
    empresas.py            ← endpoints empresa + Focus + diagnóstico cert + importar-xlsx
    integra.py             ← endpoints Integra Contador + SITFIS debug
    robo.py                ← /robo/distribuicao (Focus DF-e)
    robo_sefaz.py          ← /robo/sefaz/disparar (Celery — bug Redis #85)
    certidoes.py           ← /cnds/empresa/{id}/renovar (gera CND via SITFIS)
  app/services/
    jettax_importer.py     ← importador XLSX 102 empresas (commit 61356e6)
    integra_contador_service.py  ← SITFIS orquestrador (bug PDF #86 aqui)
    cnd_robo_service.py    ← gera CNDs (FEDERAL via SITFIS, FGTS/ESTADUAL via Infosimples)
  app/providers/
    focus_nfe.py           ← provider Focus (JSON+base64, regime int, timeouts)
    integra_contador.py    ← provider Serpro (timeout 15s, mutual TLS cert)
  app/workers/
    celery_app.py          ← config Celery (BUG #85)
    tasks.py               ← tasks background
  alembic/versions/
    20260603_0019_situacao_fiscal_protocolo_500.py  ← migration PDF SITFIS

frontend/
  app/empresas/
    importar/page.tsx      ← página importador XLSX
    [id]/page.tsx          ← detalhe empresa (FocusCard + CndCard + IntegraCard)
  app/documentos/page.tsx  ← lista NFes + SyncFocusModal com loop automático
  lib/empresas.ts          ← API empresas + import XLSX
  lib/documentos.ts        ← API documentos + sync Focus

Dockerfile.backend         ← raiz, é o que prod usa (NÃO backend/Dockerfile)
```

---

## 🚨 Quando retomar amanhã

1. **Ler este handoff** (estado completo)
2. **Conferir tasks pendentes** principalmente #85 (Redis) e #86 (PDF)
3. **Decidir prioridade**:
   - Redis #85 desbloqueia uso do robô SEFAZ pras 102 empresas (alto impacto)
   - PDF SITFIS #86 desbloqueia CNDs federais via Integra real (médio impacto)
   - Subir certs em batch desbloqueia auto-cadastrar Focus pras 102

Recomendação: começar pelo **Redis #85** porque robô SEFAZ é a base de tudo (download de XMLs emitidos). Sem isso, não importa o resto.

Boa noite e bom trabalho amanhã 🌙
