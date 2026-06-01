# PAC SEFAZ-GO Agent

Agente Python que automatiza o download de XMLs de NFes emitidas no portal SEFAZ-GO usando certificado A1 das empresas, e faz upload automaticamente pra API do PAC.

**Portal alvo**: https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/principal

## Status

| Versão | Arquivo | Estado |
|---|---|---|
| **v1** (produção) | `pac_sefaz_agent.py` | ✅ Playwright async, mTLS, integração PAC |
| v0 (referência) | `sefaz_go_downloader.py` | 🟡 Selenium, gerado pelo Claude Extension (mantido só pra histórico) |

## Arquitetura (v1)

```
┌──────────────────────────────────────────────────────────────────┐
│ pac_sefaz_agent.py (Python 3.11+, Playwright async)              │
│                                                                  │
│ 1. PacClient.login()                       → JWT do PAC          │
│ 2. PacClient.listar_empresas(com_cert=True)→ empresas elegíveis  │
│ 3. Pra cada empresa:                                             │
│    a. PacClient.baixar_certificado()       → .pfx + senha        │
│    b. playwright.chromium.launch(headless) → Linux/Win/Mac       │
│    c. context com clientCertificates       → mTLS automático     │
│    d. Acessa SEFAZ-GO → Turnstile passa    → form aparece        │
│    e. Preenche datas → Pesquisar           → enfileira           │
│    f. Poll Histórico até "Concluído"       → baixa ZIP           │
│    g. PacClient.upload_em_massa(zip)       → POST pra API PAC    │
│    h. Cleanup cert temporário                                    │
│ 4. Resumo JSONL + JSON final                                     │
└──────────────────────────────────────────────────────────────────┘
```

## Pré-requisitos

- Python 3.11+
- PAC Download API rodando (default: http://127.0.0.1:8000)
- Empresas cadastradas no PAC **com certificado A1 carregado** (campo `cert_a1_path`)

## Setup

```bash
# 1. Venv
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Deps
pip install -r requirements.txt
playwright install chromium

# 3. Configurar
cp .env.example .env
# editar .env com URL do PAC + credenciais
```

## Uso

```bash
# Mês anterior, todas empresas com cert A1
python pac_sefaz_agent.py

# Só uma empresa específica (id no PAC)
python pac_sefaz_agent.py --empresa 5

# Mês específico
python pac_sefaz_agent.py --periodo 2026-04

# Debug com browser visível
python pac_sefaz_agent.py --headed

# Baixa ZIP local mas NÃO envia pro PAC
python pac_sefaz_agent.py --dry-run
```

## Variáveis de ambiente (.env)

| Variável | Default | Descrição |
|---|---|---|
| `PAC_API_URL` | `http://127.0.0.1:8000` | URL do backend PAC |
| `PAC_EMAIL` | `admin@pacxml.com.br` | Usuário do agente |
| `PAC_PASSWORD` | `admin123` | Senha |
| `SEFAZ_GO_URL` | (oficial) | Override apenas pra testes |
| `HEADLESS` | `true` | `false` força janela visível |
| `STEP_TIMEOUT` | `60` | Timeout por step (s) |
| `DOWNLOAD_TIMEOUT` | `600` | Tempo máximo aguardando ZIP ficar pronto |
| `SLOW_MO_MS` | `200` | Delay entre ações (só em headed) |

## Como rodar em produção (VPS Linux Hostinger)

```bash
# 1. Instalar deps de sistema do Chromium
apt-get install -y \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2 libpango-1.0-0 libcairo2

# 2. Pip + playwright
pip install -r requirements.txt
playwright install --with-deps chromium

# 3. .env produção
cat > .env <<EOF
PAC_API_URL=http://localhost:8000
PAC_EMAIL=agente@pacxml.com.br
PAC_PASSWORD=<senha-forte>
HEADLESS=true
EOF

# 4. Cron diário (todo dia 5 do mês às 03h)
echo "0 3 5 * * cd /opt/pac-sefaz-agent && python pac_sefaz_agent.py >> logs/cron.log 2>&1" | crontab -
```

## Logs

```
logs/
├── agente_2026-05-19.jsonl    # JSON Lines (1 evento por linha)
└── resumo_20260519_030045.json # Resumo final da execução
```

Cada evento é um objeto:
```json
{"timestamp": "2026-05-19T03:00:05Z", "evento": "portal_aberto", "cnpj": "10930732000134", "url": "..."}
{"timestamp": "2026-05-19T03:00:08Z", "evento": "login_cert_iniciado", "cnpj": "10930732000134"}
{"timestamp": "2026-05-19T03:00:15Z", "evento": "form_carregado", "cnpj": "10930732000134"}
```

## Endpoints PAC usados

| Endpoint | Método | Propósito |
|---|---|---|
| `/api/v1/auth/login` | POST | Obtem JWT |
| `/api/v1/empresas` | GET | Lista empresas com cert |
| `/api/v1/empresas/{id}/certificado/baixar` | GET | Baixa `.pfx` + senha (interno) |
| `/api/v1/documentos/upload-em-massa` | POST | Envia ZIP de XMLs |

## Limitações conhecidas

- **Cloudflare Turnstile**: passa em browser real. Em headless puro às vezes bloqueia — fallback Xvfb está documentado mas não implementado ainda.
- **Selector XPath frágil**: portal SEFAZ-GO pode mudar layout — selectors em `pac_sefaz_agent.py:processar_empresa()` precisam revisão se quebrar.
- **Volume**: SEFAZ-GO provavelmente limita ~5-10k registros por consulta. Pra empresas com alto volume (como JOVELINO com 85k NFCe), fragmentar por dia.
- **Multi-UF**: este agente é só pra **GO**. SP/MG/RJ/MT precisam de novos agentes específicos (cada SEFAZ tem fluxo diferente).

## Próximos passos (Fase 3)

- [ ] UI no PAC pra disparar agente sob demanda + acompanhar progresso
- [ ] Webhook do agente notificando PAC ao terminar
- [ ] Multi-UF (começar com SP que é o mais usado)
- [ ] Fragmentação automática por período pra contornar limite de consulta
- [ ] Distribuir como Docker container pra deploy fácil no VPS
