# Handoff — Agente SEFAZ-GO híbrido funcionando end-to-end

**Data:** 21/05/2026
**Status:** ✅ Fluxo completo funcionou. 2 bugs pendentes + 1 feature nova solicitada.

---

## 1. O que foi entregue (FUNCIONANDO)

Agente Python que automatiza download de XMLs do portal SEFAZ-GO usando:
- **Playwright** com Chrome do sistema (user channel)
- **mTLS** via `client_certificates` (cert A1 da empresa, PFX re-empacotado moderno)
- **2Captcha** ($0.003/execução) pra resolver Cloudflare Turnstile
- **Token injetado no DOM** (sem submeter HTTP direto — usa o JS do portal)
- **Integração com PAC Download API** (lista empresas, baixa cert, posta ZIP)

### Fluxo validado end-to-end

```
✅ Login PAC → JWT
✅ GET /empresas → lista com cert A1
✅ GET /empresas/{id}/certificado/baixar → .pfx + senha
✅ PFX → re-empacotado moderno (AES-256/SHA256) pra OpenSSL 3
✅ Playwright Chrome do sistema (BROWSER_CHANNEL=chrome)
✅ Entry point goias.gov.br/economia/documentos-fiscais/
✅ Click "Arquivo XML dos Documentos Fiscais" → portal
✅ mTLS automático (Playwright apresenta cert sem popup)
✅ Click "Acesso Por Certificado Digital"
✅ Form /consulta-publica carrega
✅ Extrai sitekey Turnstile do DOM (0x4AAAAAABWl9df-N8s5C_f1)
✅ 2Captcha resolve em ~30-40s (token 1157 chars, $0.003)
✅ Token injetado no input #cf-turnstile-response
✅ Click "Pesquisar" — submit aceito (sem 404)
✅ Click "Baixar todos os arquivos"
✅ Modal: radio "somente documentos" → confirmar
✅ Portal navega pra /resultado/download/historico
✅ Tabela tem linha "Concluído" + botão "Baixar XML"
✅ Click no link → page.expect_download → ZIP salvo
```

**Custo real medido**: $0.003/execução (1 captcha por empresa por mês).

---

## 2. Bugs pendentes pra próxima sessão

### Bug 1 — Datepicker não aceita `.fill()`
**Sintoma:** O agente preenche data via `input.fill("01/04/2026")` mas o portal usa o período **default** do form (21/04 a 21/05) no submit.

**Causa:** Os campos `cmpDataInicial` e `cmpDataFinal` são **jQuery UI Datepickers** (classe `hasDatepicker`). O JS interno lê do estado do widget, não do value do input. `fill()` apenas seta o `value` sem disparar `change`/blur que o datepicker escuta.

**Evidência:** ZIP baixado tem nome `21042026_21052026` (período default) ao invés de `01042026_30042026` (período pedido).

**Soluções a testar (em ordem):**
1. `await input.click()` (abre datepicker) → `await input.fill(data)` → `await page.keyboard.press("Tab")` (fecha + dispara blur)
2. Dispatch JS manual: `await page.evaluate("(el, v) => { el.value=v; el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true})); }", input, data)`
3. Usar `$('#cmpDataInicial').datepicker('setDate', ...)` via `page.evaluate` (acessa direto a API do jQuery UI)

### Bug 2 — Agente clica no primeiro "Concluído" da tabela
**Sintoma:** Se já houver ZIPs antigos na fila (de execuções manuais ou anteriores do agente), o agente baixa o errado.

**Evidência:** Tabela tinha 3 ZIPs `Concluído`, agente baixou o `6211.zip` (de 18:48 — execução anterior), não o `5849.zip` (de 18:52 — execução atual).

**Solução:** Identificar a linha pelo nome do arquivo (deve conter o período pedido, ex: `01042026_30042026`). Filtrar antes de clicar.

---

## 3. Feature nova solicitada pelo user (21/05)

> "tem q ser sempre 30 dias, do mês anterior, pois é quando baixar as notas, no sistema tem q ter como programar isto"

### Requisitos

1. **Janela padrão = mês anterior completo** (01 a último dia)
   - Em junho roda 01-31/05, em julho roda 01-30/06, etc.
   - Já existe `janela_mes_anterior()` no agente ✅
   - Em ambiente "rodando dia 5 de cada mês", default automaticamente fica mês anterior

2. **Agendamento no sistema PAC** — UI/backend pra:
   - Configurar dia do mês de execução (ex: dia 5)
   - Configurar horário (ex: 03h)
   - Configurar empresas (todas ativas com cert, ou seleção)
   - Cron diário verificando se é dia de rodar
   - Histórico de execuções (sucesso/falha por empresa)
   - Alerta se falhar

### Arquitetura proposta pro agendamento

**Backend novo:**
- Tabela `agendamento_robo` (id, dia_mes, hora, ativo, ultima_execucao)
- Tabela `execucao_robo` (id, agendamento_id, empresa_id, status, iniciada_em, terminada_em, qtd_xmls, log_path)
- Endpoint `POST /robo-sefaz/disparar-agora` (dispara manualmente uma empresa)
- Endpoint `GET /robo-sefaz/execucoes` (lista histórico)
- Endpoint `GET/PUT /robo-sefaz/agendamento` (config)
- Worker Celery (ou script cron) que roda diariamente e checa se é dia de disparar
- Quando dispara, chama o agente Python como subprocess ou via fila

**Frontend novo:**
- Página `/robo-sefaz` com:
  - Card "Próxima execução agendada"
  - Card "Última execução" (sucesso/falha por empresa)
  - Botão "Disparar agora" (uma empresa ou todas)
  - Tabela de execuções (filtros: empresa, status, data)
  - Form de agendamento (dia do mês, hora, empresas)

---

## 4. Arquivos relevantes (estado atual)

```
agent/sefaz-go/
├── pac_sefaz_agent.py        ← PRINCIPAL (Playwright + 2Captcha híbrido) — FUNCIONA
├── pac_client.py              ← Cliente HTTP PAC (login, listar, baixar cert, upload)
├── pac_sefaz_agent_http.py   ← Tentativa HTTP puro — NÃO FUNCIONA (endpoints chutados)
├── sefaz_go_downloader.py    ← v0 do Claude Extension (Selenium) — só referência
├── requirements.txt           ← deps atualizadas (playwright + 2captcha-python)
├── .env                       ← config local (PAC + 2Captcha key)
├── .env.example               ← template
├── README.md                  ← doc do agente
├── downloads/                 ← ZIPs baixados (1 ZIP validado, contém XML real)
│   └── unzipped/
│       └── 1101115226051093...xml (procEventoNFe Cancelamento JOVELINO)
├── certs-temp/                ← cleanup automático
└── logs/
    ├── agente_2026-05-21.jsonl  ← eventos estruturados
    ├── resumo_*.json             ← resumo por execução
    └── debug/
        ├── form_carregado_*.html ← snapshot do form
        └── historico_inicial_*.html ← snapshot da fila
```

### Configuração ativa (.env)

```
PAC_API_URL=http://127.0.0.1:8000
PAC_EMAIL=admin@pacxml.com.br
PAC_PASSWORD=admin123
SEFAZ_GO_ENTRY=https://goias.gov.br/economia/documentos-fiscais/
SEFAZ_GO_URL=https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/principal
HEADLESS=false
BROWSER_CHANNEL=chrome
TWOCAPTCHA_API_KEY=<REDACTED>  # rotacionar — token original removido pre-push GitHub
SEFAZ_GO_SITEKEY=0x4AAAAAABWl9df-N8s5C_f1
SLOW_MO_MS=200
STEP_TIMEOUT=60
DOWNLOAD_TIMEOUT=600
```

### Como rodar (validado)

```bash
cd C:\dev\pac-xml-downloader\agent\sefaz-go
python pac_sefaz_agent.py --empresa 5 --periodo 2026-04 --headed --dry-run
```

Tempo total: ~90s por empresa. Custo: $0.003.

---

## 5. Insights técnicos descobertos

### Sobre o portal SEFAZ-GO

- **URL inicial pública**: https://goias.gov.br/economia/documentos-fiscais/
- **Link de entrada**: "Arquivo XML dos Documentos Fiscais" (em "Consultas e Serviços com uso de Certificado Digital")
- **Após login mTLS**: `nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/principal` (tela boas-vindas)
- **Form de consulta**: `.../consulta-publica` (após click "Acesso Por Certificado Digital")
- **Submit redireciona**: `.../resultado/download/historico` com query `g-recaptcha-response`
- **Formato do ZIP**: `<CNPJ>_<DDMMYYYY-inicio>_<DDMMYYYY-fim>_<id>.zip`

### Turnstile Cloudflare

- **Sitekey**: `0x4AAAAAABWl9df-N8s5C_f1`
- **Callback JS**: `pegarTokenSuccess`
- **Input destino**: id `cf-turnstile-response`, name `g-recaptcha-response` (legado)
- **NÃO resolve sozinho em Playwright** (mesmo com stealth) — precisa 2Captcha
- **2Captcha resolve em 30-40s** com `solver.turnstile(sitekey, url)`
- **Token válido por ~120s** depois expira (re-resolver se demorou)

### Playwright

- **No Windows**: usar `BROWSER_CHANNEL=chrome` (Chrome do sistema) — Chromium do Playwright dá erro de VC++ Redistributable
- **PFX da ICP-Brasil**: precisa re-empacotar via Python `cryptography` antes (OpenSSL 3 bloqueia algoritmos legados do PFX original)
- **`client_certificates` aceita bytes**, não path string (Playwright >= 1.46)
- **Keep-alive durante 2Captcha**: page.evaluate ping a cada 10s pra evitar driver disconnect

### Endpoints HTTP puro (descobertas)

- `POST /selecao` → **405** (método não suportado, é GET)
- `GET /selecao?cmpCnpj=...&...&g-recaptcha-response=TOKEN` → suposto. Não foi totalmente testado.
- Os endpoints do submit são complexos e usam JS do portal — **não vale automatizar via HTTP puro**

---

## 6. Tasks pendentes (TaskList atual)

```
#1. ✅ Refatorar agente Selenium → Playwright
#2. ✅ Implementar poll do download + extração ZIP
#3. ✅ POST automático do ZIP no PAC
#4. ✅ Ler empresas do PAC ao invés de Excel
#5. ✅ Testar agente end-to-end (FUNCIONOU)
#6. ✅ Resolver Cloudflare Turnstile (via 2Captcha)
#7. ✅ Versão HTTP (descartada, ficou Playwright híbrido)
#8. ✅ Testar agente HTTP com 2Captcha
#9. ✅ Implementar agente híbrido Playwright+2Captcha
```

### Pra próxima sessão (criar tasks novas)

- [ ] **Bug 1 fix**: datepicker — usar `setDate` via JS ou keyboard+blur
- [ ] **Bug 2 fix**: identificar linha do histórico pelo NOME do ZIP esperado (deve conter o período exato)
- [ ] **Feature 30d mês anterior + agendamento**:
  - Backend: tabelas `agendamento_robo` + `execucao_robo`
  - Backend: endpoints disparar/listar/config
  - Backend: worker Celery diário
  - Frontend: página `/robo-sefaz` com agendamento + histórico + botão "Disparar agora"
- [ ] Testar com empresa REAL que tem NFes/NFCes no mês completo
- [ ] Validar upload-em-massa fechando o ciclo (XMLs aparecem em /documentos)
- [ ] Documentar custo real do 2Captcha por mês

---

## 7. Comandos pra retomar serviços

```bash
# Backend
cd C:/dev/pac-xml-downloader/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend
cd C:/dev/pac-xml-downloader/frontend
npm run dev

# Agente
cd C:/dev/pac-xml-downloader/agent/sefaz-go
python pac_sefaz_agent.py --empresa 5 --periodo 2026-04 --headed --dry-run
```

---

## 8. Saldo 2Captcha (último check 18:52)

- **Saldo restante**: $4.99
- **Captchas usados**: ~3-4 ($0.012)
- **Suficiente pra**: ~1.500 execuções (1000+ meses de uso normal pra 120 empresas mensais)

API Key (já configurada no `.env`): `19755d34ec98032abc7a996d220eedac`

---

**Última atualização:** 2026-05-21 18:55 BRT
**Próxima sessão:** consertar 2 bugs do agente + implementar agendamento PAC
