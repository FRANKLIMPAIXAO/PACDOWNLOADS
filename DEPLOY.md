# Deploy em produção — VPS Hostinger

Guia completo para subir o **PAC Download** numa VPS Hostinger.

**Cenário de uso**: escritório contábil próprio, ~120 empresas-clientes,
acessos só pela equipe interna (não é SaaS público).

> Para análise detalhada de custo/benefício vs. JeTax/Sage e o plano de
> migração das 120 empresas, ver **`CAPACITY-120.md`**.

---

## 1. Dimensionamento do VPS

### O que vai rodar simultaneamente

| Processo | RAM ociosa | RAM pico | CPU |
|---|---|---|---|
| Backend FastAPI (uvicorn 2 workers) | 200 MB | 500 MB | médio |
| Worker Celery | 150 MB | 350 MB | médio |
| Celery beat (agendador) | 50 MB | 80 MB | baixo |
| Postgres 16 | 250 MB | 800 MB | médio |
| Redis 7 | 50 MB | 100 MB | baixo |
| Next.js (Node SSR) | 250 MB | 500 MB | baixo |
| Chromium (Playwright p/ robô SEFAZ) | 0 MB ocioso | 600 MB durante emissão | alto picos |
| Nginx | 30 MB | 60 MB | baixo |
| Sistema (Ubuntu 22.04) | 250 MB | 350 MB | baixo |
| **TOTAL ocioso** | **~1,3 GB** | | |
| **TOTAL pico** | | **~3,3 GB** | |

### Recomendação por escala

| Empresas atendidas | Plano Hostinger | Specs | Preço |
|---|---|---|---|
| **1–15** (início) | **KVM 2** | 2 vCPU · 8 GB RAM · 100 GB NVMe | ~R$ 65/mês |
| 15–80 | KVM 4 | 4 vCPU · 16 GB · 200 GB NVMe | ~R$ 120/mês |
| 80–300 | KVM 8 | 8 vCPU · 32 GB · 400 GB NVMe | ~R$ 250/mês |

**Para você começar agora**: pegue o **KVM 2**. Sobra RAM e dá pra crescer até ~30 empresas confortavelmente. Quando estiver perto do limite, é upgrade in-place (Hostinger faz sem reinstalar).

**Não pegue KVM 1 (4 GB)** — apertado para rodar Postgres + Chromium + tudo junto.

### Tamanho de banco/storage

Estimativa para uma empresa típica:
- 30–50 docs fiscais / mês (NFe recebidas + emitidas)
- Cada XML: ~8 KB no disco + ~3 KB no Postgres (`json_original`)
- 5 anos de retenção (SPED): 60 meses × 40 docs = 2.400 docs/empresa

| # empresas | XMLs (5 anos) | Postgres | Storage XMLs | Storage CNDs/Apurações |
|---|---|---|---|---|
| 10 | 24.000 docs | ~150 MB | ~200 MB | ~50 MB |
| 50 | 120.000 docs | ~600 MB | ~1 GB | ~200 MB |
| 100 | 240.000 docs | ~1,2 GB | ~2 GB | ~400 MB |

**Conclusão**: 100 GB SSD do KVM 2 cabem **~300 empresas com 5 anos de histórico**. Largo.

---

## 2. Checklist de contratações (TUDO que precisa ter)

### Já tem
- [x] **Conta Hostinger**

### Pra contratar / configurar antes do go-live

- [ ] **VPS Hostinger KVM 2** (Ubuntu 22.04 LTS) — ~R$ 65/mês
- [ ] **Domínio próprio** (ex.: `pacdownload.com.br`) — ~R$ 60/ano (.com.br) ou grátis se incluso no plano
- [ ] **DNS apontando** subdomínios para o IP da VPS:
  - `app.pacdownload.com.br` → frontend (porta 443)
  - `api.pacdownload.com.br` → backend (porta 443)
- [ ] **e-CNPJ A1 do escritório contábil** (.pfx) — ~R$ 280/ano
  - Necessário para: cadastrar empresas na Focus + autenticar Integra Contador + emitir CND Federal sem captcha
- [ ] **Conta Focus NFe** (https://focusnfe.com.br/precos)
  - Plano básico: ~R$ 200/mês para até 5 empresas
  - Para o escritório com várias empresas: pacote por volume
  - Pegar **token-mestre** do painel para `FOCUS_MASTER_TOKEN`
- [ ] **Conta Serpro / Loja Integra Contador** (https://loja.serpro.gov.br/integracontador)
  - Pacotes a partir de ~R$ 50/mês para 1.000 chamadas
  - Precisa de **e-CNPJ** para se cadastrar
  - Pegar `consumer_key` + `consumer_secret`
- [ ] **Conta 2captcha** (https://2captcha.com) — opcional mas recomendado para CNDT
  - Cadastro grátis, créditos a partir de **US$ 1** (≈ 1.000 captchas resolvidos)
  - Pegar `API_KEY`
- [ ] **Procurações eletrônicas** dos clientes outorgadas ao CNPJ do escritório no eCAC
  - Cada cliente acessa o eCAC dele, vai em "Procurações" e cadastra o escritório com escopo CAIXA_POSTAL + SITFIS + DTE + PAGTOWEB
  - **Sem isso a Serpro recusa todas as chamadas relacionadas àquele CNPJ**
- [ ] **SMTP para alertas** (escolha 1):
  - **Brevo** (ex-Sendinblue) — 300 e-mails/dia grátis ([brevo.com](https://brevo.com))
  - **Postmark** — US$ 15/mês para 10k e-mails ([postmarkapp.com](https://postmarkapp.com))
  - **AWS SES** — US$ 0,10/1.000 e-mails (precisa AWS conta)

### Custos mensais estimados (escritório com 10–20 empresas)

| Item | Mensal |
|---|---|
| VPS KVM 2 | R$ 65 |
| Domínio .com.br (rateio anual) | R$ 5 |
| e-CNPJ A1 (rateio anual) | R$ 23 |
| Focus NFe (10 empresas) | ~R$ 250 |
| Serpro Integra Contador (5k chamadas) | ~R$ 150 |
| 2captcha (50 CNDs/mês) | R$ 1 |
| SMTP Brevo (free tier) | R$ 0 |
| **TOTAL** | **~R$ 494/mês** |

Cobre 15–20 empresas com folga. Fica ~R$ 25–35/empresa/mês operacional — dá margem boa pra cobrar R$ 100–250/empresa.

---

## 3. Arquivos de deploy (já criados no repo)

```
pac-xml-downloader/
├── DEPLOY.md                      ← este arquivo
├── docker-compose.production.yml  ← stack completa
├── backend/
│   ├── Dockerfile
│   └── .env.production.example
├── frontend/
│   ├── Dockerfile
│   └── .env.production
└── deploy/
    ├── nginx.conf
    ├── deploy.sh                  ← script de instalação na VPS
    └── backup.sh                  ← backup automático Postgres
```

---

## 4. Plano de execução passo-a-passo

### Passo 1 — Contratar VPS e domínio (15 min)

1. Loga na Hostinger → "VPS" → escolhe **KVM 2** com **Ubuntu 22.04 LTS**
2. Define senha root forte (anota num gerenciador tipo 1Password/Bitwarden)
3. Compra/aponta domínio: cria registros A em DNS:
   - `app.pacdownload.com.br` → IP da VPS
   - `api.pacdownload.com.br` → IP da VPS

### Passo 2 — Setup inicial da VPS (20 min)

```bash
# SSH na VPS (Hostinger fornece IP + credenciais)
ssh root@<IP-DA-VPS>

# Atualiza sistema
apt update && apt upgrade -y

# Cria usuário não-root (segurança)
adduser pac
usermod -aG sudo pac

# Instala Docker + Compose
curl -fsSL https://get.docker.com | sh
usermod -aG docker pac

# Firewall basico
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable

# Reinicia como pac
exit
ssh pac@<IP-DA-VPS>
```

### Passo 3 — Clonar projeto e configurar (15 min)

```bash
# No usuario pac
cd ~
git clone <seu-repo> pac-xml-downloader   # ou rsync local → VPS
cd pac-xml-downloader

# Copia template e edita
cp backend/.env.production.example backend/.env
nano backend/.env
# (preencher: SECRET_KEY, DATABASE_URL, FOCUS_MASTER_TOKEN, SERPRO_*, CAPTCHA_API_KEY...)

# Coloca o e-CNPJ do escritório
mkdir -p backend/certs
scp ecnpj-escritorio.pfx pac@<IP-VPS>:~/pac-xml-downloader/backend/certs/

# Sobe stack
docker compose -f docker-compose.production.yml up -d

# Aplica migrations
docker compose exec backend python -m alembic upgrade head

# Cria primeiro admin (ou usa default do .env e troca a senha depois pelo /register)
```

### Passo 4 — SSL Let's Encrypt (10 min)

```bash
# Gera certificados automaticamente
docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
  -d app.pacdownload.com.br -d api.pacdownload.com.br \
  --email seu@email.com --agree-tos --no-eff-email

# Reinicia nginx pra carregar
docker compose restart nginx
```

### Passo 5 — Primeiros testes reais (30 min)

1. Abrir `https://app.pacdownload.com.br` → login admin
2. **Cadastrar 1 empresa de teste** (use uma de bolso ou homologação Focus)
3. **Subir certificado A1 dela** via tela `/empresas/{id}` → Cadastrar empresa na Focus
4. **Validar no painel Focus** que a empresa apareceu
5. **Importar token retornado** ou marcar `USE_MOCK_FOCUS_NFE=false` e re-cadastrar
6. **Disparar `/robo/distribuicao`** para 7 dias retroativos
7. Conferir XMLs em `storage/xmls/` na VPS
8. **Testar Integra Contador**: configurar SERPRO_* no .env, cadastrar procuração no eCAC, sincronizar Caixa Postal e Procuração
9. **Testar robô CNDT real**: setar `USE_MOCK_SEFAZ=false` + `CAPTCHA_API_KEY`, clicar Renovar → conferir PDF baixado

### Passo 6 — Backup automatizado (5 min)

```bash
# Cron diário do dump Postgres às 3h
crontab -e
# Adicionar:
0 3 * * * cd ~/pac-xml-downloader && bash deploy/backup.sh >> /var/log/pac-backup.log 2>&1
```

O `deploy/backup.sh` (já no repo):
- Roda `pg_dump` da base
- Faz tar.gz do `storage/`
- Sobe para Backblaze B2 ou Hostinger Object Storage (configurável)
- Mantém últimos 30 dias

---

## 5. Checklist final antes de operar com clientes reais

- [ ] VPS rodando estável por 24h (sem OOM, sem crash)
- [ ] HTTPS funcionando (`https://app.pacdownload.com.br` com cadeado verde)
- [ ] Backup do dia anterior gravado em external storage
- [ ] Mock desligado:
  - [ ] `USE_MOCK_FOCUS_NFE=false`
  - [ ] `USE_MOCK_INTEGRA=false`
  - [ ] `USE_MOCK_SEFAZ=false`
- [ ] 1 empresa real cadastrada com fluxo completo testado:
  - [ ] Token Focus salvo
  - [ ] Procuração Integra Contador ativa
  - [ ] Robô DF-e baixou XMLs reais do mês passado
  - [ ] Caixa Postal eCAC sincronizada
  - [ ] CNDT renovada via robô SEFAZ
  - [ ] Apuração mensal calculada com motor (RB líquida + DAS)
- [ ] E-mail SMTP de alertas testado
- [ ] Senha admin trocada da default `admin123` 🔥
- [ ] `SECRET_KEY` no .env é **forte e única** (NÃO use a default)
- [ ] Logs sendo gravados em `/var/log/`

---

## 6. Operação diária

### Comandos úteis na VPS

```bash
# Ver logs do backend
docker compose logs -f backend

# Ver logs de todos os serviços
docker compose logs -f --tail=100

# Reiniciar 1 serviço
docker compose restart backend

# Atualizar código (após git pull)
docker compose build backend frontend
docker compose up -d

# Disparar tarefa manual do Celery
docker compose exec backend celery -A app.workers.celery_app.celery_app \
  call app.workers.tasks.executar_download_diario

# Acessar Postgres CLI
docker compose exec postgres psql -U pac -d pac_xml

# Backup manual
bash deploy/backup.sh
```

### Beat schedule já configurado (jobs automáticos)

| Job | Quando | O que faz |
|---|---|---|
| `executar_download_diario` | Todo dia 7h | Baixa NF-e recebidas via DF-e (Focus) de todas empresas ativas |
| `sync_caixa_postal_diario` | Todo dia 8h | Sincroniza Caixa Postal eCAC via Integra Contador |
| `renovar_cnds_vencendo` | Toda segunda 6h | Renova CNDs vencendo em ≤7 dias via robô SEFAZ |

### Monitoramento mínimo

- **Hostinger**: gráficos de CPU/RAM/disco no painel da VPS
- **Healthcheck**: `curl https://api.pacdownload.com.br/health` deve retornar `200 OK`
- **Sentry** (opcional, free tier): adicionar `sentry-sdk` ao backend para capturar erros — entrega quase imediata e barato

---

## 7. Próximos passos pós-go-live (em ordem de importância)

1. **Onboarding em massa**: planilha CSV com (CNPJ, razão, certificado.pfx) → script de import
2. **Notificações por e-mail** quando CND vencer, mensagem ECAC chegar, apuração pendente
3. **Multi-tenant**: cada escritório vê só seus dados (importante se vai vender)
4. **Cobrança/billing** integrado (Stripe ou ASAAS)
5. **App mobile** (PWA do frontend Next.js já vem grátis)
