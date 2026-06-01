# Handoff 27/05/2026 — Preparação para Produção

**Data:** 27/05/2026
**Sessão anterior:** `HANDOFF_2026-05-26_INFOSIMPLES-FGTS-PGFN.md`
**Status:** Sistema 100% funcional em mock + 5 empresas reais cadastradas + auditoria Postgres OK
**Próximo:** Vincular 2ª VPS no Easypanel + criar Supabase + deploy

---

## 1. O que fechou hoje

### 1.1 Card FGTS Digital no dashboard (#47)
- Bloco `fgts` agregado em `/dashboard/resumo`:
  - `pendentes_qtd`, `valor_a_pagar`, `vencidas_qtd`, `vencendo_30d_qtd`, `empresas_sem_guia_mes`
- Coluna **FGTS** em `/dashboard/por-empresa` com `fgts_pendentes` + `fgts_mes_emitida`
- Frontend `app/page.tsx`:
  - Card "FGTS Digital" com lógica dinâmica de cor:
    - 🔴 **rose** se tem vencida
    - 🟡 **amber** se vence 30d ou empresa sem guia do mês
    - 🔵 **cyan** se só pendentes no prazo
    - 🟢 **emerald** se tudo em dia
  - Coluna "FGTS" na tabela "Visão por empresa": `N a pagar` (vermelho) / `✓ mês` (verde) / `pendente` (amarelo)

### 1.2 Fix CLAVEAUX batch SEFAZ-GO (#48)
- **Sintoma**: TimeoutError 15s no step "Acesso por Certificado Digital" em batch (Execução #9 falhou só na CLAVEAUX, AGIMED e JOVELINO OK)
- **Causa**: Cloudflare interstitial intermitente após rajada de requests, JS do portal não tinha renderizado
- **Fix em `agent/sefaz-go/pac_sefaz_agent.py`**:
  - `wait_for_load_state("networkidle", 15s)` antes de procurar botão
  - **4 estratégias** de locator com **30s cada** (90s no pior caso vs 15s+15s antes):
    1. `role-button` regex "certificado"
    2. `role-link` regex "certificado"
    3. `text=/acesso por certificado digital/i`
    4. `:text('Certificado Digital')` (literal)
  - Debug dump em `logs/debug/sem_cert_btn_*.{png,html}` + lista dos 20 botões/links visíveis
- **Validação**: Execução #10 — CLAVEAUX baixou **805 XMLs em 53s** ✅

### 1.3 Fix polling do Robô SEFAZ (#49)
- **Sintoma**: Execução #10 ficou eternamente "Rodando" no histórico mesmo depois de concluir
- **Causa raiz**: `useEffect` agendava polling APENAS no mount se já tinha execução `pendente|rodando`. Se usuário abrir tela vazia e disparar depois, polling nunca reativa.
- **Fix em `frontend/app/robo-sefaz/page.tsx`**:
  - `carregar()` extraída pra `useCallback` do componente — pode ser chamada de qualquer handler
  - `useRef` pra `alive`/`timer`/`fastUntil` — sem race condition entre renders
  - **Polling adaptativo**: 2s nos primeiros 30s pós-disparo, 5s depois
  - `handleDisparar` agora cancela timer pendente + chama `carregar()` imediato
  - **Botão "↻ Atualizar"** manual com indicador de busy
  - **Pill "⟳ atualizando a cada 2s"** quando tem rodando / "parado" quando nada ativo
  - **"Última atualização: Xs atrás"** auto-atualizando a cada segundo

### 1.4 Cadastro batch 5 empresas reais (#50)
Lidas 102 clientes do Excel `C:/Users/pacpa/Downloads/clientes.xlsx`. Cadastradas 5 GO ativas com IM via API:

| ID | CNPJ | Razão Social |
|---|---|---|
| #9 | 53379477000196 | 53.379.477 MARIA MADALENA DA SILVA VIEIRA |
| #10 | 58804283000104 | A + SERVICE LTDA |
| #11 | 29174487000100 | ADALTRO LIMPEZAS E PISCINAS LTDA |
| #12 | 60543231000173 | ALFA DISTRIBUIDORA DE PECAS E ACESSORIOS LTDA |
| #13 | 29646299000138 | ANGELO CONSTRUTORA |

**Sem cert A1** (não temos os .pfx físicos dessas). Pra rodar Robô SEFAZ precisa subir o .pfx via UI cadastro.

Script reutilizável fica documentado neste handoff (seção 5).

### 1.5 Auditoria portabilidade Postgres (#51)
**Conclusão: código JÁ está pronto pra Postgres. Nenhuma alteração necessária.**

| Check | Status |
|---|---|
| Driver `psycopg[binary]==3.2.9` no requirements | ✅ Já incluído |
| Models usam `sqlalchemy.JSON` genérico (não JSONB-only) | ✅ Funciona em ambos |
| `database.py` usa `create_engine(settings.database_url)` agnóstico | ✅ Só trocar URL |
| Migrations Alembic usam `sa.func.now()` portável | ✅ Funciona em ambos |
| Sem `json_extract` ou `datetime()` SQLite-specific em código | ✅ Limpo |

**A única mudança necessária:** `DATABASE_URL=postgresql://...` no `.env`.

---

## 2. Decisões de produção (fechadas hoje)

| Item | Decisão | Motivo |
|---|---|---|
| **Banco de dados** | Supabase | PostgreSQL gerenciado, dashboard web, backup automático, free 500MB inicial |
| **Hosting** | VPS Hostinger via **Easypanel** | Docker com UI gráfica, deploy automático do GitHub, HTTPS Let's Encrypt embutido |
| **Domínio** | Inicia em IP da VPS | Compra dominio depois quando 100% estável |
| **Usuários** | 1 admin (`admin@pacxml.com.br`) | Sem multi-tenancy por enquanto |
| **Dados** | Começar zerado em prod | Mocks/lixo do dev local NÃO vão pra prod. Migrations + admin + import Excel via script |

---

## 3. Plano de deploy — fases

### Fase 1 (próxima sessão): Setup Supabase
1. Franklim cria projeto no painel Supabase (`pac-download-prod`, região São Paulo)
2. Passa connection string pra eu testar localmente
3. `alembic upgrade head` apontado pro Supabase
4. Validação: criar admin + cadastrar 1 empresa de teste
5. **Verificar todas as queries funcionam** (PARCSN, dashboard, FGTS, etc.)

### Fase 2: Dockerização
1. `Dockerfile.backend` — Python 3.12 + uvicorn + Playwright + Chromium (~1.5GB imagem)
2. `Dockerfile.frontend` — Node 20 + Next.js build standalone
3. `docker-compose.yml` pra teste local: backend + frontend + Redis
4. `.dockerignore` (já existe, validar)
5. Volume pra `storage/` (XMLs, certs, PDFs)

### Fase 3: Easypanel deploy
1. Push código GitHub
2. Conectar GitHub no Easypanel (auto-deploy on push)
3. Configurar 3 serviços: backend, frontend, redis
4. Env vars sensíveis (tokens, DATABASE_URL Supabase) via UI
5. Volume persistente em `/data/pac-storage`
6. Cron Celery beat schedule

### Fase 4: Validação prod
1. Importar 5 empresas via script Excel
2. Subir 3 certs A1 reais (JOVELINO, CLAVEAUX, AGIMED)
3. 1 ciclo end-to-end: Robô SEFAZ + DAS sync + FGTS emit
4. Smoke test todas as telas

### Fase 5: Domínio + SSL
1. Comprar `.com.br` no Registro.br (~R$ 40/ano)
2. DNS apontando pro IP VPS
3. Let's Encrypt SSL automatic via Easypanel
4. Atualizar `ALLOWED_ORIGINS` + `NEXT_PUBLIC_API_URL`

---

## 4. Tasks fechadas hoje

| # | Task | Status |
|---|---|---|
| #47 | Card FGTS no dashboard + coluna FGTS na visão por empresa | ✅ |
| #48 | Fix CLAVEAUX: step 'Acesso Certificado Digital' com 4 estratégias | ✅ |
| #49 | Fix polling Robô SEFAZ: lista nunca atualiza pós-disparo | ✅ |
| #50 | Cadastrar 5 empresas do Excel pra testes batch | ✅ |
| #51 | Auditar código pra portabilidade SQLite → Postgres | ✅ |

---

## 5. Script reutilizável de import Excel

Salvo aqui pra rodar de novo em produção. Path do Excel: `C:/Users/pacpa/Downloads/clientes.xlsx`.

```python
# scripts/import_empresas_excel.py
import pandas as pd
import requests
from datetime import datetime

API = "http://127.0.0.1:8000"  # ou URL prod
EXCEL_PATH = 'C:/Users/pacpa/Downloads/clientes.xlsx'
LIMIT = 5  # quantas cadastrar

def parse_data(s):
    if pd.isna(s): return None
    if isinstance(s, str):
        try: return datetime.strptime(s, '%d/%m/%Y').date().isoformat()
        except: return None
    if hasattr(s, 'date'): return s.date().isoformat()
    return None

def parse_str(x):
    if pd.isna(x): return None
    return str(x).strip() or None

def parse_int_str(x):
    if pd.isna(x): return None
    try: return str(int(float(x)))
    except: return str(x).strip() or None

def parse_cep(x):
    if pd.isna(x): return None
    s = ''.join(c for c in str(x) if c.isdigit())
    return s[:8] if len(s) >= 7 else None

# Login
r = requests.post(f"{API}/api/v1/auth/login",
    json={"email":"admin@pacxml.com.br","password":"admin123"})
h = {"Authorization": f"Bearer {r.json()['access_token']}"}

ja_cnpjs = {e['cnpj'] for e in requests.get(f"{API}/api/v1/empresas", headers=h).json()}

df = pd.read_excel(EXCEL_PATH)
df['CNPJ_lim'] = df['*CNPJ'].astype(str).str.zfill(14)
cand = df[
    (df['Status'] == 1) &
    (df['Estado'] == 'GO') &
    (~df['CNPJ_lim'].isin(ja_cnpjs)) &
    (df['*Inscrição Municipal'].notna())
].head(LIMIT)

for _, r in cand.iterrows():
    payload = {k: v for k, v in {
        "cnpj": r['CNPJ_lim'],
        "razao_social": parse_str(r['Razão Social']),
        "inscricao_estadual": parse_int_str(r['Inscrição Estadual']),
        "inscricao_municipal": parse_int_str(r['*Inscrição Municipal']),
        "data_abertura": parse_data(r['Data de Abertura da Empresa']),
        "telefone": parse_str(r['Telefone']),
        "email_contato": parse_str(r['Email Fiscal']),
        "cep": parse_cep(r['CEP']),
        "logradouro_tipo": parse_str(r['Tipo de Logradouro']),
        "logradouro": parse_str(r['Endereço']),
        "numero": parse_str(r['Numero']),
        "complemento": parse_str(r['Complemento']),
        "bairro": parse_str(r['Bairro']),
        "uf": "GO", "municipio": "GOIANIA",
        "ativo": True, "tributacao": "Simples Nacional",
    }.items() if v is not None}
    resp = requests.post(f"{API}/api/v1/empresas", headers=h, json=payload)
    print(f"{r['CNPJ_lim']} → HTTP {resp.status_code}")
```

---

## 6. Pendências priorizadas

### Próxima sessão (urgente)
- [ ] Franklim cria projeto Supabase + manda connection string
- [ ] Testar local apontando pra Supabase (alembic upgrade head)
- [ ] Validar todas as queries funcionam em Postgres
- [ ] Vincular 2ª VPS no Easypanel (decidido nessa sessão — instruções abaixo)

### Backlog
- [ ] **#13/#14** Testes batch com mais empresas — depende de subir certs A1
- [ ] **#20** DAS valor real no sync (GERARDASCOBRANCA17 por compet)
- [ ] **#22** PARCSN OBTERPARC164 (ER_N002)
- [ ] Token Infosimples 601 ainda pendente — sem ele FGTS/Estadual ficam mock
- [ ] Cron mensal FGTS Digital automático
- [ ] Importação em massa de empresas via Excel (tela UI)
- [ ] Multi-UF agente SEFAZ (SP)
- [ ] Backups automatizados pra storage/ (rclone S3)

---

## 7. Como retomar amanhã

### Subir ambiente local
```bash
# Backend
cd C:\dev\pac-xml-downloader\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend
cd C:\dev\pac-xml-downloader\frontend
npm run dev

# Login: admin@pacxml.com.br / admin123
```

### Empresas atuais no DB local (id, cnpj, razão)
- #5 JOVELINO E ACILDA LTDA (cert A1 ✓)
- #6 INDUSTRIA DE LATICINIO CLAVEAUX LTDA (cert A1 ✓)
- #7 AGIMED COMERCIO DE EQUIPAMENTOS LTDA (cert A1 ✓)
- #8 TESTE PGFN MOCK LTDA (pra deletar antes de prod)
- #9-13 5 empresas do Excel (sem cert A1)

### Estado das execuções Robô SEFAZ
- #10 Concluído: AGIMED 49 dup + CLAVEAUX 805 novos + JOVELINO 3 dup
- Total: 805 NFes novas + 52 duplicadas validadas em batch

---

## 8. Como vincular 2ª VPS no Easypanel

Hostinger tem 2 VPS, uma cheia (outros projetos), outra livre pro PAC. Como Easypanel funciona com **uma única VPS por instância**, tem 2 caminhos:

### Caminho A: Instalar Easypanel separado na 2ª VPS (Recomendado)
**Custo: zero. Manutenção: 2 dashboards independentes.**

Passos práticos:
1. **Painel Hostinger** → **VPS** → seleciona a 2ª VPS (vazia)
2. **Operating System** → **Reinstall** → escolhe template **"Easypanel"** (Hostinger já tem template pronto)
   - Se não tiver template Easypanel, escolhe **Ubuntu 22.04** e instala manual:
     ```bash
     curl -sSL https://get.easypanel.io | sh
     ```
3. Aguarda ~5 min provisionar
4. Acessa `http://<IP-da-2ª-VPS>:3000` no navegador
5. Cria conta admin do Easypanel (email + senha)
6. Pronto — você tem 2 painéis independentes:
   - `http://IP-VPS1:3000` (existente, cheia)
   - `http://IP-VPS2:3000` (nova, vai hospedar o PAC)

**Vantagens:**
- Não paga nada além das VPS
- Isolamento total (problema em uma não afeta outra)
- Setup mais simples
- 90% dos usuários Easypanel fazem assim

**Desvantagens:**
- Trabalha com 2 painéis separados
- Não dá pra mover apps entre VPS facilmente

### Caminho B: Easypanel Multi-Server (Pro)
**Custo: ~US$ 15-20/mês. Manutenção: 1 dashboard único.**

Disponível apenas no plano Pro do Easypanel. Permite:
- 1 control plane (VPS1) gerencia N servidores (VPS2, VPS3...)
- Deploy de apps escolhendo qual servidor usa
- Apps podem se comunicar via overlay network

Setup:
1. Atualiza Easypanel da VPS1 pro plano **Pro**
2. No dashboard → **Settings** → **Servers** → **"Add Server"**
3. Cola IP + porta SSH da VPS2 + chave privada
4. Easypanel instala agente Docker na VPS2 automaticamente
5. Ao criar nova app, escolhe "Deploy to: VPS2"

**Vantagens:**
- 1 dashboard só pra ver tudo
- Migração entre VPS é click

**Desvantagens:**
- Custo recorrente
- Mais coisa pra dar problema (rede, SSH)

### Minha recomendação pra você: **Caminho A**

Pelos seguintes motivos:
- VPS2 vai ter SÓ o PAC Download (não vai compartilhar recursos com outras apps)
- 1 dashboard a mais não é peso operacional
- Você economiza R$ 80-100/mês que rende mais que o convenience

### Resumo dos passos pra amanhã

1. Loga na Hostinger
2. Vai na 2ª VPS (vazia)
3. Reinstala com template Easypanel OU comando manual
4. Pega o IP da 2ª VPS
5. Cria conta no painel Easypanel da 2ª VPS
6. Anota: `http://<IP-VPS2>:3000` + login/senha admin
7. Me passa o IP quando voltar — eu te guio o resto do deploy do PAC

**Importante**: pode deletar projetos antigos da VPS1 se quiser usar lá em vez de subir a VPS2 — mas a chance de bater memória com Robô SEFAZ (Chromium pesa ~500MB) é alta. Recomendo VPS dedicada pro PAC.

### Pré-requisitos da VPS pro PAC
- Ubuntu 22.04 LTS
- Mínimo **2 vCPU + 4GB RAM** (8GB ideal — Chromium do Robô pesa)
- 40GB+ disco (storage cresce com XMLs)
- IP fixo (Hostinger já dá)

---

## 9. Atualização final do dia — fix Google Translate

### 9.1 Estado descoberto
Franklim subiu o frontend na 2ª VPS (IP `72.62.111.136:3000`). Ao acessar pelo Chrome, recebeu erro:

```
Algo deu errado!
Failed to execute 'removeChild' on 'Node':
The node to be removed is not a child of this node.
```

### 9.2 Causa raiz
Erro **clássico** de React em produção pra usuários brasileiros. Quando o Chrome detecta a página e oferece "Traduzir para português?", o motor do Google Translate **manipula o DOM direto** (envolve textos em `<font>` tags, troca filhos de nós). React então tenta reconciliar uma árvore que foi alterada por fora e levanta o `removeChild` quando não encontra mais a referência original do filho.

Mesmo com `suppressHydrationWarning` (que adicionamos antes pra Scribe), Chrome Translate é mais agressivo — ele continua mexendo no DOM após hidratação, durante updates.

### 9.3 Fix aplicado (#52) — `frontend/app/layout.tsx`
3 sinais combinados pra Chrome NÃO traduzir:

| Sinal | Onde | Função |
|---|---|---|
| `lang="pt-BR"` | `<html>` | Diz pro Chrome que JÁ está em PT |
| `translate="no"` | `<html>` | Atributo HTML5 padrão |
| `className="notranslate"` | `<html>` | Convenção Google Translate |
| `<meta name="google" content="notranslate">` | via `metadata.other.google` do Next | Meta oficial Google |

Código:
```tsx
export const metadata = {
  title: "PAC Download — Central fiscal",
  description: "...",
  icons: { icon: [{ url: "/favicon.svg", type: "image/svg+xml" }] },
  other: { google: "notranslate" },  // ← NOVO
};

return (
  <html lang="pt-BR" translate="no" className="notranslate" suppressHydrationWarning>
    <body suppressHydrationWarning>...</body>
  </html>
);
```

### 9.4 Pra aplicar na VPS amanhã
- Pull do código atualizado (após push no GitHub)
- Rebuild do frontend: `npm run build && npm start`
- Hard refresh `Ctrl+Shift+R`
- Se ainda mostrar barra "Traduzir para português?" no Chrome, clica em **"Nunca traduzir este site"**

---

## 10. Plano de AMANHÃ — Integração GitHub + Easypanel

### 10.1 Fluxo proposto

```
DEV LOCAL (Windows)
   |
   |  git push origin main
   v
GITHUB (repositório privado)
   |
   |  webhook automático
   v
EASYPANEL (VPS 72.62.111.136)
   |
   |  pull + docker build + restart
   v
PRODUÇÃO no ar
```

### 10.2 Pré-requisitos pra amanhã
- [ ] Conta GitHub do Franklim (se não tem, criar grátis em github.com)
- [ ] Decidir se repositório vai ser **privado** (recomendado — código tem refs sensíveis em comments) ou **público**
- [ ] SSH key da máquina dev pro GitHub (pra push sem digitar senha)
- [ ] PAT (Personal Access Token) ou GitHub App pro Easypanel autenticar
- [ ] Decidir nome do repo: sugestão `pac-download` ou `pac-xml-downloader`

### 10.3 Passos previstos (~1.5h total)

**Etapa A — Repositório GitHub (15 min)**
1. Criar repo privado em github.com → "New repository"
2. No PC local: `git init` (se não tiver), `.gitignore` validar, primeiro `git add . && git commit`
3. `git remote add origin git@github.com:franklim/pac-download.git`
4. `git push -u origin main`

**Etapa B — Dockerfiles (30 min)**
1. `backend/Dockerfile` — Python 3.12 slim + apt deps pro Playwright + Chromium + uvicorn
2. `frontend/Dockerfile` — Node 20 multi-stage (builder + runner) com `output: "standalone"`
3. `docker-compose.yml` pra teste local
4. Testar: `docker compose up --build` no PC → ambos sobem

**Etapa C — Easypanel conecta GitHub (15 min)**
1. Painel Easypanel da VPS2 → **Settings** → **Git Providers** → conectar GitHub
2. Cria projeto novo "PAC Download"
3. 3 serviços: `backend`, `frontend`, `redis`
4. Cada serviço aponta pra `Dockerfile.<tipo>` do repo
5. Auto-deploy on push: enabled

**Etapa D — Env vars + volumes (15 min)**
1. Backend env: `DATABASE_URL` (Supabase), `INFOSIMPLES_TOKEN`, `SERPRO_*`, `FOCUS_*`, `SECRET_KEY`, `CAPTCHA_API_KEY`
2. Frontend env: `NEXT_PUBLIC_API_URL=http://72.62.111.136:8000` (ou domínio interno do Easypanel)
3. Volume backend → `/app/storage` mapeado pra `/data/pac-storage` na VPS

**Etapa E — Validação (20 min)**
1. Push do código no GitHub
2. Aguardar Easypanel detectar e fazer build/deploy
3. Acessar `http://72.62.111.136/` (Easypanel proxy pra porta 80 → frontend)
4. Login admin
5. Importar 5 empresas via script Excel apontando pro IP da VPS

### 10.4 Itens que ficam pendentes pra DEPOIS de amanhã
- Comprar domínio + Let's Encrypt SSL
- Cron Celery beat (executar_download_diario mensal)
- Backups automatizados storage/
- Subir Postgres no Supabase (se ainda não fez)
- Token Infosimples válido (resolver o code 601)

---

## 11. Tasks completas hoje (consolidado)

| # | Task | Status |
|---|---|---|
| #47 | Card FGTS no dashboard + coluna FGTS | ✅ |
| #48 | Fix CLAVEAUX: cert button 4 estratégias + networkidle | ✅ |
| #49 | Fix polling Robô SEFAZ: lista nunca atualiza pós-disparo | ✅ |
| #50 | Cadastrar 5 empresas do Excel | ✅ |
| #51 | Auditar código pra Postgres (conclusão: pronto) | ✅ |
| #52 | Fix Google Translate quebrando React | ✅ |

---

## 12. Como retomar AMANHÃ — checklist rápido

1. **Confirmar estado da VPS 72.62.111.136**:
   - SSH ou Browser Terminal Hostinger → checar o que tá rodando: `docker ps`
   - Anotar processos atuais (backend? frontend? Redis?)

2. **Criar conta GitHub** (se não tiver) → criar repo privado `pac-download`

3. **Me passar 3 informações**:
   - URL do repo GitHub recém-criado
   - Quanto de RAM tem a VPS2 (`free -h` no SSH ou painel Hostinger)
   - Se o Supabase já foi criado (e se sim, a connection string)

4. **Comigo**: crio Dockerfiles, faço primeiro push, configuro Easypanel pra pull automático, ligamos Supabase, e em ~2h o sistema tá rodando em prod com deploy contínuo.

---

**Boa noite — amanhã pegamos GitHub + Docker + Easypanel + Supabase numa só sessão. 🚀**
