# Handoff 01/06/2026 — 🚀 PRODUÇÃO NO AR + 3 gaps detectados

**Data:** 01/06/2026
**Sessão anterior:** `HANDOFF_2026-05-27_PROD-PREP.md`
**Status:** 🎯 **SISTEMA EM PRODUÇÃO EFETIVA** — Robô SEFAZ-GO baixou 3 XMLs reais da JOVELINO via Easypanel
**Próximo:** ativar serviços reais (mocks → false) + criar UI faltante

---

## 1. 🎉 MARCO DO DIA

Subimos o sistema completo em produção e fechamos o ciclo end-to-end com dado fiscal real:

```
┌──────────────────────────────────────────────────────────────────┐
│  PRODUÇÃO EFETIVA — 01/06/2026 22:30 BRT                         │
│  ─────────────────────────────────────────                       │
│  Frontend  https://pacdownloads-frontend.ibm21x.easypanel.host   │
│  Backend   https://backend.72.62.111.136.nip.io                  │
│  DB        Supabase Postgres 17.6 (aws-1-us-east-2)              │
│  Cache     Redis 7.4 (rede interna Easypanel)                    │
│  Storage   Volume persistente /app/storage (Easypanel mount)     │
│  Repo      github.com/FRANKLIMPAIXAO/PACDOWNLOADS (auto-deploy)  │
│                                                                   │
│  PROVADO: Robô SEFAZ-GO Execução #11                             │
│    JOVELINO E ACILDA LTDA → OK (3 XMLs) em 54s                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 14 bugs resolvidos hoje (sequência cronológica)

| # | Camada | Bug | Fix | Commit |
|---|---|---|---|---|
| 1 | Frontend | Google Translate quebrando React (`removeChild`) | `lang="pt-BR" translate="no" notranslate` + meta `google: notranslate` | (pre-deploy) |
| 2 | Banco | Supabase code 601 — senha com `@` quebrava URL | Reset pra `PAC25012014241200` (alfanum) | — |
| 3 | Alembic | `DuplicateObject` ENUM `tipodocumento` em Postgres | Removeu `.create()` explícito, deixa `create_table` autocriar | `f503ba2` |
| 4 | Docker | `playwright install-deps` quebrava em Debian Trixie | Removida linha (libs já no apt-get) | `abaedd4` |
| 5 | Segurança | 4 tokens vazados em handoffs antigos | Mascarados com `<REDACTED>` antes do push | `ca4df64` |
| 6 | Docker | Backend não copiava `agent/` (build context só `backend/`) | `Dockerfile.backend` na raiz copiando ambos | `af067f5` |
| 7 | Deps | `2captcha-python==1.5.5` não existe | Versão `1.5.1` | `f430f56` |
| 8 | Deps | `brazilfiscalreport==2.1.0` não existe | Versão `0.7.7` | `bfe7584` |
| 9 | Deps | `ModuleNotFoundError: httpx` no `pac_client.py` | Add `httpx==0.27.0` | `f9401a1` |
| 10 | Persistência | Cert 410 Gone (storage não-persistente — sumiu no redeploy) | Volume Easypanel `/app/storage` + re-upload PFX | (config Easypanel) |
| 11 | Docker | Chromium permission denied (`/root/.cache` vs user `pac`) | `PLAYWRIGHT_BROWSERS_PATH=/opt/...` + chown | `621526d` |
| 12 | Docker | "Host system missing dependencies" (libcups2t64, libnspr4, …) | **Base image** `mcr.microsoft.com/playwright/python:v1.48.0-jammy` | `f6d8f52` |
| 13 | Diagnóstico | 2Captcha "Falha genérica" sem contexto | Var module `ULTIMO_ERRO_TURNSTILE` + mensagens descritivas | `65de2c9` |
| 14 | Integração | Agent espera `TWOCAPTCHA_API_KEY`, backend tem `CAPTCHA_API_KEY` | Bridge no `robo_sefaz_service.py` ao spawn do subprocess | `b10f931` |

**14 fixes em 1 sessão.** Cada um destravou uma camada — daria pra escrever um post-mortem sobre como deploy enterprise quebra em cascata.

---

## 3. 🟡 3 PROBLEMAS REPORTADOS pelo Franklim — investigar amanhã

### 3.1 "Não emitiu CND"

**O que ele tentou**: clicar em "Renovar" alguma CND na tela `/prevencao` ou `/cnds`.

**Diagnóstico provável**: TODOS os providers de CND estão em modo **mock** em produção. Variáveis atuais no Easypanel backend:

```
USE_MOCK_INTEGRA=true       ← bloqueia SITFIS (FEDERAL/FEDERAL_OFICIAL)
USE_MOCK_INFOSIMPLES=true   ← bloqueia FGTS, ESTADUAL
```

**Comportamento atual**: em mock, os métodos retornam dados fake mas SEM PDF real. A UI pode mostrar "CND emitida" no mock (data fictícia) OU dar erro se o caller espera um PDF físico.

**O que investigar amanhã**:
1. Olhar logs do backend quando Franklim clicou "Renovar" — `docker logs` ou Easypanel "Logs"
2. Resposta HTTP da rota `POST /cnds/empresa/{id}/renovar?tipo=...`
3. Se retornou 200, mock funcionou OK mas dados são fake (sem PDF). Cliente espera PDF? Tela mostra erro?
4. Se retornou 500/4xx, tem bug no fluxo do mock

**Fix proposto**:
- **Curto prazo**: ligar `USE_MOCK_INTEGRA=false` + setar `SERPRO_*` reais → SITFIS funciona = FEDERAL/FEDERAL_OFICIAL via Integra Contador
- **Médio prazo**: ligar `USE_MOCK_INFOSIMPLES=false` + `INFOSIMPLES_TOKEN` → FGTS + ESTADUAL reais
- **TRABALHISTA / MUNICIPAL**: cadastro manual (sem provider — já documentado)

### 3.2 "Mensagens da caixa postal estão mockadas"

**Onde**: tela `/empresas/{id}/caixa-postal` (existe em `frontend/app/empresas/[id]/caixa-postal/page.tsx`).

**Diagnóstico confirmado**: o endpoint `MSGCONTRIBUINTE61` do Serpro (`integra_contador_service.py`) está bloqueado por `USE_MOCK_INTEGRA=true`. Retorna lista hardcoded de mensagens fictícias.

**Fix**: mesma coisa do item 3.1 — `USE_MOCK_INTEGRA=false` + Serpro real.

### 3.3 "Não sei como testar a busca de notas pela Focus NFe"

**Diagnóstico confirmado — É BUG REAL DE UI FALTANTE**:

Olhando o código:
- Backend tem rota `POST /api/v1/robo/distribuicao` (chama Focus NFe `/v2/nfes_recebidas` por empresa, sincronia incremental via NSU)
- Backend também tem `POST /api/v1/robo/empresa` (uma empresa específica) e `POST /api/v1/robo/multiempresas`
- **Frontend NÃO TEM BOTÃO** pra disparar essa rota!
- A tela `/documentos/page.tsx` linha 556 só mostra mensagem "Cadastre uma empresa e execute o robo de distribuicao" — sem oferecer COMO

Ou seja: a infra existe, mas falta UI pra disparar.

**Fix proposto pra amanhã**:
1. Adicionar botão "Sincronizar via Focus NFe (DF-e)" na tela `/documentos`
2. Modal/form: dropdown empresa + (opcional) período + checkbox "Todas"
3. Backend já está pronto — só plumbing do frontend
4. Considerar criar tela própria `/distribuicao` similar ao `/robo-sefaz` se ficar complexo

---

## 4. Estado atual da prod (snapshot 22:30 BRT)

### 4.1 Serviços rodando

| Serviço | Status | URL/Path | Notas |
|---|---|---|---|
| Backend | ✅ Rodando | `https://backend.72.62.111.136.nip.io` | Healthcheck `/health` 200 OK |
| Frontend | ✅ Rodando | `https://pacdownloads-frontend.ibm21x.easypanel.host` | Login funcional |
| Redis | ✅ Rodando | `redis://redis:6379/0` | Rede interna Easypanel |
| Supabase | ✅ Postgres 17.6 | Pooler us-east-2:5432 | 17 tabelas + admin criado |
| Volume `/app/storage` | ✅ Persistente | Easypanel mount | Cert JOVELINO sobreviveu redeploy |

### 4.2 Dados em prod

| Tipo | Quantidade | Detalhe |
|---|---|---|
| Usuário admin | 1 | `admin@pacxml.com.br / admin123` |
| Empresas | 6 | 5 do Excel + JOVELINO (subida manualmente pra teste) |
| Cert A1 cadastrado | 1 | JOVELINO (válido até 2026-07-23) |
| Execuções Robô SEFAZ | 11 | Última: #11 OK (3 XMLs JOVELINO) |
| NFes baixadas | 3 | Da JOVELINO via Robô em prod |
| Guias DCTFWeb emitidas | 1 | Empresa #6 — emitida via UI em prod (com mock Serpro) |

### 4.3 Empresas cadastradas em prod

| ID | CNPJ | Razão | Cert A1 |
|---|---|---|---|
| 1 | 53379477000196 | 53.379.477 MARIA MADALENA DA SILVA VIEIRA | — |
| 2 | 58804283000104 | A + SERVICE LTDA | — |
| 3 | 29174487000100 | ADALTRO LIMPEZAS E PISCINAS LTDA | — |
| 4 | 60543231000173 | ALFA DISTRIBUIDORA DE PECAS E ACESSORIOS LTDA | — |
| 5 | 29646299000138 | ANGELO CONSTRUTORA | — |
| 6 | 10930732000134 | **JOVELINO E ACILDA LTDA** | ✅ vence 2026-07-23 |

### 4.4 Env vars sensíveis no Easypanel backend

| Var | Status | Notas |
|---|---|---|
| `DATABASE_URL` | ✅ Supabase Session pooler | senha rotacionada pós-vazamento chat |
| `SECRET_KEY` | ✅ Gerada nova (token_urlsafe(64)) | |
| `CAPTCHA_API_KEY` | ✅ Setada | bridge p/ TWOCAPTCHA_API_KEY no spawn |
| `SERPRO_CERT_PATH` | ⚠️ Setado mas cert NÃO subido | `/app/certs/escritorio.pfx` não existe ainda |
| `SERPRO_CERT_PASSWORD` | ✅ Rotacionada (era `Pac@1234`) | |
| `USE_MOCK_INTEGRA` | 🟡 **true** | desligar pra ativar SITFIS real |
| `USE_MOCK_FOCUS_NFE` | 🟡 **true** | desligar pra ativar DF-e real |
| `USE_MOCK_INFOSIMPLES` | 🟡 **true** | desligar pra ativar FGTS/Estadual real |
| `USE_MOCK_SEFAZ` | ✅ **false** | Robô SEFAZ-GO real funcionando! |

---

## 5. Plano de AMANHÃ — desbloquear 100% real

### Fase A (15 min): logs do que Franklim tentou hoje

1. Pedir pra ele tentar de novo "Renovar CND" em alguma empresa
2. Eu vou olhar os logs do backend no Easypanel ao mesmo tempo
3. Capturar request/response da rota `/cnds/empresa/{id}/renovar`
4. Decisão: ligar `USE_MOCK_INTEGRA=false` agora ou debugar mock primeiro?

### Fase B (30 min): ativar Integra Contador real

Pré-requisito: cert `.pfx` do **escritório** subido pra `/app/certs/escritorio.pfx` no volume Easypanel.

Como subir o cert:
- Opção 1: SSH no container e copiar via `scp` (precisa de acesso SSH ao Easypanel)
- Opção 2: criar rota POST `/admin/upload-escritorio-cert` (precisa autenticação admin)
- Opção 3: shell embedded do Easypanel + `cat > escritorio.pfx` (gambiarra)

Depois:
1. Env var `USE_MOCK_INTEGRA=false` + redeploy
2. Testar: tela `/empresas/{id}/caixa-postal` deve carregar mensagens reais (MSGCONTRIBUINTE61)
3. Testar: `/prevencao` → Renovar CND FEDERAL → deve emitir SITFIS real (`storage/sitfis/` no volume)

### Fase C (45 min): criar UI faltante pra Focus NFe distribuição

1. **Frontend**: novo componente "Sincronizar via Focus" em `/documentos`
   - Botão no header da página
   - Modal com dropdown empresa + checkbox "Todas as ativas com Focus token"
   - Loading spinner + toast com resultado
2. **Backend**: já pronto (`/api/v1/robo/distribuicao` e `/api/v1/robo/empresa`)
3. Mock pode continuar `true` até ele confirmar tokens Focus reais

### Fase D (30 min): ativar Infosimples real

1. Confirmar `INFOSIMPLES_TOKEN` válido (foi rotacionado?)
2. Env var `USE_MOCK_INFOSIMPLES=false` + redeploy
3. Testar:
   - CND FGTS via `/prevencao` (deve cair `/consultas/caixa/regularidade`)
   - CND Estadual via `/prevencao` (deve cair `/consultas/sefaz/go/certidao-debitos`)
   - Emitir Guia FGTS Digital em `/fgts` (deve cair `/consultas/fgts/guia-rapida`)

### Fase E (15 min): batch real com 3 empresas

1. Subir certs A1 reais da CLAVEAUX (`01060996000193`) e AGIMED (`03852519000196`)
2. `/robo-sefaz` → "Todas" → Rodar
3. Esperar Execução #12: JOVELINO dup + CLAVEAUX 800+ XMLs + AGIMED ~50 XMLs (matriz com filiais)
4. Confirma escalabilidade

---

## 6. Backlog não-bloqueante

- [ ] Cron Celery beat (dia 5 às 03h) automatizando Robô SEFAZ-GO
- [ ] Backup automático Supabase (snapshot semanal)
- [ ] Backup `/app/storage` (rclone → S3 ou similar)
- [ ] Comprar domínio `pacdownload.com.br` (Registro.br, ~R$ 40/ano)
- [ ] Migrar de `*.nip.io` pro domínio próprio
- [ ] Limpar 404 `integra/procuracao` órfã (rota frontend sem backend)
- [ ] Frontend: criar tela `/distribuicao` própria (ou enriquecer `/documentos`)
- [ ] **#20** DAS valor real no sync (GERARDASCOBRANCA17 por compet)
- [ ] **#22** PARCSN OBTERPARC164 enriquecimento

---

## 7. Como retomar amanhã — quick start

### Acessos
- **Frontend**: https://pacdownloads-frontend.ibm21x.easypanel.host
- **Login**: `admin@pacxml.com.br` / `admin123`
- **Backend health**: https://backend.72.62.111.136.nip.io/health
- **Easypanel**: https://72.62.111.136:3000 (login Franklim)
- **Supabase**: https://supabase.com/dashboard/project/vqhwpkvdnizaproskjvg
- **GitHub**: https://github.com/FRANKLIMPAIXAO/PACDOWNLOADS

### Como fazer mudança de código
```bash
# No PC local
cd C:\dev\pac-xml-downloader
# ... edita o código ...
git add .
git commit -m "feat/fix: <descrição>"
git push origin main
# → Easypanel detecta e faz auto-deploy em ~3-8 min
```

### Comandos úteis no Easypanel
- **Logs backend**: serviço `backend` → aba "Logs" (mostra requests em tempo real)
- **Implantar manual**: botão verde "Implantar" no histórico
- **Shell no container**: botão `>_` na barra do serviço (acesso bash dentro do container)
- **Métricas**: CPU/Mem/Network já visíveis no topo

### Estado do código local
- Branch: `main`
- Último commit: `b10f931` (bridge CAPTCHA_API_KEY → TWOCAPTCHA_API_KEY)
- Repo limpo, sem changes pendentes
