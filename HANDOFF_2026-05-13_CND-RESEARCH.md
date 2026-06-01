# Handoff — Integração real Focus + Integra Contador validadas, pendente CND de cartório

**Data:** 13/05/2026
**Sessão anterior:** instalação produção VPS Hostinger
**Foco desta sessão:** trocar mocks por integrações reais (Focus NFe + Integra Contador/Serpro)

---

## 1. Status executivo

### ✅ Funcionando 100% real

| Componente | Status | Detalhe |
|---|---|---|
| **Focus NFe — auth** | ✅ | Master token + token por empresa, mTLS-less |
| **Focus NFe — `/v2/empresas` (listar/filtrar)** | ✅ | Master token; `/v2/empresas/{cnpj}` NÃO existe (422) |
| **Focus NFe — `/v2/nfes_recebidas`** | ✅ | Pronto, mas JOVELINO ainda sem movimento — habilitação recente |
| **Integra Contador — auth (`/authenticate`)** | ✅ | mTLS A1 + Basic Auth, JWT 45min, cache thread-safe |
| **Integra — Caixa Postal listar (`MSGCONTRIBUINTE61`)** | ✅ | **44 mensagens reais da JOVELINO sincronizadas** |
| **Integra — Caixa Postal detalhe (`MSGDETALHAMENTO62`)** | ✅ | HTML completo do `corpoModelo` |
| **Integra — Caixa Postal indicador (`INNOVAMSG63`)** | ✅ | Path corrigido pra `/Monitorar` |
| **Integra — SITFIS solicitar protocolo (`SOLICITARPROTOCOLO91`)** | 🟡 | Funciona, mas Serpro tem cooldown longo (>3min) — retry 6× resolve |
| **Integra — SITFIS emitir relatório (`RELATORIOSITFIS92`)** | 🟡 | Validado HTTP 200 + PDF, mas dependente do protocolo acima |
| **Frontend tile Federal unificado** | ✅ | 1 tile cobre SITFIS interno + CND oficial sob demanda |

### ❌ Mock ainda (precisa decisão)

- **FGTS (CRF) — Portal Caixa**
- **Trabalhista (CNDT) — Portal TST**
- **CND Conjunta RFB+PGFN — Portal RFB** (uso externo: licitação, banco)
- **DTE consultar** (idSistema/idServico errados — descobrir no catálogo Serpro)

### Mocks ainda no banco (deletar antes de produção)

5 registros em `certidoes` para `empresa_id=5` (JOVELINO) — todos com `data_emissao=2026-05-13` e observação literal `"MOCK-PROT-..."` ou `"Emitida automaticamente via..."`. Apagar via:

```sql
DELETE FROM certidoes WHERE empresa_id = 5 AND data_emissao = '2026-05-13';
```

---

## 2. Pendência crítica que trava o resto: CND de cartório

### Comparativo dos 3 caminhos

| Opção | Custo mensal | Custo p/ 120 empresas/ano | Esforço de impl | Manutenção |
|---|---|---|---|---|
| **A) Playwright + 2captcha** | R$ ~30/mês 2captcha + storage Chromium | R$ 360/ano | **Alto** — 3 scrapers, código complexo | Quebra cada vez que o portal muda |
| **B) Infosimples API** | Pré-pago por consulta (~R$ 0,30-0,50) | R$ 500-800/ano | **Baixo** — HTTP simples | Eles que se viram com captcha/mudanças |
| **C) Manual** | R$ 0 | R$ 0 | **Zero** — upload PDF já existe | Você baixa do portal, cliente fica esperando |

### O que pesquisar pra escolher

**Pra cada API que você avaliar, levantar:**

1. **Preço por consulta** (CNDT vs CRF vs CND Conjunta — geralmente preços diferentes)
2. **Plano mínimo** (algumas exigem pacote de 100+ consultas/mês)
3. **Limite de chamadas paralelas** (você roda batch semanal pras 120 empresas)
4. **Resposta inclui PDF ou só JSON?** Você precisa do PDF assinado pra entregar
5. **SLA** (uptime > 99%? tempo de resposta médio?)
6. **Tem ambiente sandbox/homologação gratuito?** Pra testar antes de pagar
7. **Cobra requisição com erro?** (CND positiva, empresa inexistente, captcha falhou)
8. **API key vs OAuth2?** (key é mais simples)
9. **LGPD/Termo de uso aceita** envio de CNPJ de terceiros? (você é escritório contábil — precisa estar coberto)

### Providers brasileiros conhecidos pra você pesquisar

- **Infosimples** — https://infosimples.com (mais conhecido, cobre 100+ certidões)
- **Direct Data** — https://www.directdata.com.br (foco em consultas cadastrais e fiscais)
- **Brasil API + scrappers custom** — alguns endpoints públicos
- **Consulta Solutions** — focado em escritórios contábeis
- **Datavalid Serpro** — mas é mais cadastral, não certidões
- **Receita Federal API oficial?** — não tem; portal manual obrigatório

### Critério de decisão sugerido

- Se conseguir **B (Infosimples)** por menos de R$ 600/ano → vai de B, esquece a complexidade
- Se preço de B > R$ 1000/ano → vale considerar A (Playwright)
- Se cliente raramente pede CND externa (uso interno SITFIS basta) → **C (Manual)** + SITFIS automático já cobre 90%

### Custos atuais do projeto pra comparar

Pelo `CAPACITY-120.md`:
- **Hostinger VPS**: R$ 100/mês
- **Focus NFe**: R$ ~250/mês (estimado por volume)
- **Serpro Integra Contador**: pay-per-use (~R$ 50-200/mês esperado)
- **Total atual**: ~R$ 1.025/mês = R$ 12.300/ano

Comparado a JeTax R$ 2.500/mês = R$ 30.000/ano → **economia atual de R$ 17.700/ano**.

Mesmo gastando R$ 800/ano em Infosimples a economia continua > R$ 16.000/ano.

---

## 3. JOVELINO — caso de teste validado real

### Dados da empresa
| Campo | Valor |
|---|---|
| CNPJ | 10.930.732/0001-34 |
| Razão social | JOVELINO E ACILDA LTDA |
| Nome fantasia | MECANICA EL SHADDAY |
| Regime | Simples Nacional (`regime_tributario: "1"` na Focus) |
| Anexo | I |
| Atividade | Comércio + Mecânica |
| Endereço | Av. Lago dos Patos, Aparecida de Goiânia — GO |
| ID local | 5 |
| ID Focus | 163084 |
| Token Focus produção | `43RwJOtxyNxzPiXFBamLmHE6qeT5xVsa` |
| Token Focus homologação | `gyszurJKtfxf6vONWv384ltCMCed0HOY` |

### Estado na Focus (validado real)
- `habilita_manifestacao: true` ✅
- `habilita_manifestacao_cte: true` ✅
- `habilita_nfsen_recebidas_producao: true` ✅
- `data_inicio_recebimento_nfe: "2026-01-01"`
- `proximo_numero_nfce_producao: 85677` (85.676 NFCe já emitidas)
- `proximo_numero_nfe_producao: 7` (6 NFes emitidas)
- `data_ultima_emissao: "2026-05-07T11:04:42-03:00"`
- **`certificado_valido_ate: "2026-07-23"` ⚠️ vence em ~2 meses**

### Caixa Postal eCAC (sincronizada — 44 mensagens reais)
Resumo das mensagens mais críticas:
- 19/08/2025 — `EVITE A EXCLUSÃO DO SIMPLES NACIONAL!!!` (alta relevância)
- 16/08/2025 — `EVITE A EXCLUSÃO DO SIMPLES NACIONAL!!!`
- 03/08/2025 — `TERMO DE EXCLUSÃO DO SIMPLES NACIONAL`
- 28/06/2025 — `Cancelamento do TERMO DE EXCLUSÃO`
- 25/06/2025 — `TERMO DE EXCLUSÃO DO SIMPLES NACIONAL`
- 7 termos de intimação entre 19/12/2023 e 19/01/2025

**Confirmado pelo usuário**: empresa ainda no Simples Nacional (débitos foram regularizados, exclusão evitada).

### Como reproduzir o teste real

```bash
# 1. Login
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pacxml.com.br","password":"admin123"}'

# 2. Sync Caixa Postal (puxa as 44 msgs da JOVELINO)
TOKEN=<copia o access_token>
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/empresas/5/integra/caixa-postal/sync

# 3. Listar mensagens
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/empresas/5/integra/caixa-postal

# 4. Disparar SITFIS (cooldown! aguardar 10-15min entre tentativas)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v1/cnds/empresa/5/renovar?tipo=FEDERAL"
```

---

## 4. Credenciais de produção configuradas

Arquivo: `backend/.env`

### Focus NFe
```
USE_MOCK_FOCUS_NFE=false
FOCUS_BASE_URL=https://api.focusnfe.com.br
FOCUS_AMBIENTE=producao
FOCUS_MASTER_TOKEN=<REDACTED>
```

### Serpro Integra Contador
```
USE_MOCK_INTEGRA=false
SERPRO_AUTH_URL=https://autenticacao.sapi.serpro.gov.br/authenticate
SERPRO_GATEWAY_URL=https://gateway.apiserpro.serpro.gov.br/integra-contador/v1
SERPRO_CONSUMER_KEY=<REDACTED>
SERPRO_CONSUMER_SECRET=<REDACTED>
SERPRO_CERT_PATH=C:/dev/pac-xml-downloader/backend/certs/pac.pfx
SERPRO_CERT_PASSWORD=<REDACTED>
SERPRO_CONTRATANTE_CNPJ=37165535000122
SERPRO_AUTOR_PEDIDO_CNPJ=37165535000122
```

> ⚠️ Tokens originais removidos em 01/06/2026 antes do push GitHub.
> **Rotacionar nas plataformas** (Focus, Serpro, 2Captcha) — assumir comprometidos.

### Cert A1 da PAC
- **Arquivo**: `backend/certs/pac.pfx` (898 KB, gitignored)
- **Origem**: copiado de `C:/Users/.../PAC XML/PAC_Senha Pac@1234.pfx`
- **Subject**: `PAC INTELIGENCIA TRIBUTARIA LTDA:37165535000122`
- **Validade**: 22/08/2025 → 22/08/2026 (3+ meses)
- **Emissor**: AC SOLUTI RFB V5

### Contrato Serpro
- Pedido: **446504**
- CNPJ contratante: **37.165.535/0001-22** (PAC INTELIGENCIA TRIBUTARIA LTDA)
- Vigência: 01/09/2025 → 02/09/2030
- Pay-per-use, plataforma toda disponível (não tem módulos separados)

### Procurações eletrônicas e-CAC necessárias
Cláusula 4.5 do contrato — pra cada empresa-cliente consultada via Integra, **a empresa precisa ter procuração eletrônica ativa no e-CAC outorgada à PAC** (CNPJ 37.165.535/0001-22).

**JOVELINO já tem procuração ativa** (confirmado — SITFIS + Caixa Postal funcionaram).

---

## 5. Bugs corrigidos nessa sessão

### Backend

1. **`FocusNFeProvider.consultar_empresa(cnpj)`**
   - Antes: `GET /v2/empresas/{cnpj}` → Focus devolve HTTP 422 (endpoint inexistente)
   - Agora: lista todas via `/v2/empresas` e filtra localmente por CNPJ
   - Bonus: exige token-mestre (token-empresa devolve 401), mensagem clara no erro

2. **`EmpresaIntegracaoService.status_integracao()`**
   - Antes: usava `empresa.focus_token` que não tem permissão pra ver detalhes
   - Agora: usa `settings.focus_master_token` do .env

3. **`IntegraContadorProvider._executar()`**
   - Antes: estourava com `JSONDecodeError` quando Serpro responde HTTP 200 com body vazio
   - Agora: devolve `{"status": 200, "dados": None, "_empty": True}` gracefully

4. **`IntegraContadorProvider.caixa_postal_indicador()`**
   - Antes: `PATH_CONSULTAR` (errado) → Erro-AcessoNegado-017
   - Agora: `PATH_MONITORAR` (categoria certa no catálogo Serpro)

5. **`IntegraContadorProvider.caixa_postal_detalhe()`**
   - Antes: campo `isnMsg` no body → Erro-EntradaIncorreta-994 "Campo informado (isnMsg) inválido"
   - Agora: campo `isn` (nome real no payload Serpro)

6. **`IntegraContadorService.sync_caixa_postal()`**
   - Antes: lia `dados.listaMensagens` direto (não existia, resposta está em `dados.conteudo[0].listaMensagens`)
   - Antes: mapeava `isnMsg`, `assunto`, `remetente`, `indicadorRelevancia`
   - Agora: lê estrutura `conteudo[0]` aninhada, mapeia campos reais: `isn`, `assuntoModelo`, `descricaoOrigem`, `relevancia`
   - Agora: data combina `dataEnvio` (`"20250819"`) + `horaEnvio` (`"105007"`)

7. **`IntegraContadorService.gerar_situacao_fiscal()` — SITFIS**
   - Antes: falhava imediatamente quando protocolo retornava vazio
   - Agora: retry 6× com 30s entre cada (3min totais) — HTTP 503 claro se cooldown persistir

8. **`parse_data_emissao` em `_common.py`**
   - Antes: só ISO 8601
   - Agora: aceita também YYYYMMDD e YYYYMMDDHHMMSS (formato Serpro)
   - Adicionado helper `parse_data_hora_serpro(data, hora)` que combina os 2 campos

### Frontend

9. **Tile FEDERAL e FEDERAL_OFICIAL unificados** em `cnd-card.tsx`
   - Antes: 2 tiles separados confundindo (mesma base RFB+PGFN)
   - Agora: 1 tile "Federal RFB+PGFN" com 2 botões — "Atualizar SITFIS" (interno) e "Emitir CND oficial" (externo)

10. **Texto honesto** sobre scrapers pendentes
    - Antes: FGTS/CNDT mostravam "Portal Caixa (Playwright)" como se rodasse
    - Agora: "Portal Caixa (scraper pendente — cadastrar manual)"
    - `automatico: false` removeu botão "Renovar agora" enganoso

---

## 6. Lições aprendidas — Serpro Integra Contador

### Sobre o auth (`/authenticate`)
- **mTLS A1 OBRIGATÓRIO mesmo na auth** (não é só pra serviços) — sem cert dá HTTP 400 "Não foi possível identificar um certificado digital válido"
- Header `Role-Type: TERCEIROS` é obrigatório
- Body é `grant_type=client_credentials` em `application/x-www-form-urlencoded`
- Resposta inclui `access_token` (Bearer) + `jwt_token` separado
- Token vence em ~45min (`expires_in: 2687`)

### Sobre as chamadas de serviço
- Header `Authorization: Bearer {access_token}` + `jwt_token: {jwt_token}` (header separado, não dentro do body)
- Body padrão sempre `contratante` + `autorPedidoDados` + `contribuinte` + `pedidoDados`
- Tipos: `2` = PJ, `1` = PF
- `pedidoDados.dados` precisa ser **string JSON** (não dict aninhado)

### Sobre rate limits / cooldowns
- **SITFIS tem cooldown LONGO por CNPJ** — testes mostraram >3min, pode chegar a 10-15min se queimar muitos protocolos seguidos
- Quando em cooldown, Serpro responde HTTP 200 com **body literalmente vazio** (não JSON, não erro)
- Caixa Postal não tem cooldown perceptível
- Auth tem cache 45min — não reauteticar a cada chamada

### Sobre estruturas de resposta
- Quase tudo aninha em `{"codigo": "00", "conteudo": [{...}]}` — exceto SITFIS e DTE
- Datas vêm como YYYYMMDD em string sem separadores
- Campos com nome "X_modelo" são comuns (`assuntoModelo`, `corpoModelo`, `codigoModelo`)

### Endpoints que NÃO funcionam como documentado
- **DTE** — `idSistema=CAIXAPOSTAL idServico=CONSULTASITUACAODTE111` → "Identificação do sistema ou serviço inválida"
  - TODO: descobrir código correto no catálogo Serpro (https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/)
- **Procurações OBTERPROCURACAO41** — devolve `[Erro-PROCURACOES-002] (Status HTTP 40011)`
  - Pode ser cooldown ou serviço fora do ar; tentar de novo em outro horário

---

## 7. Lições aprendidas — Focus NFe

### Sobre os endpoints
- **`/v2/empresas/{cnpj}` NÃO EXISTE** — devolve HTTP 422 com `["codigo","requisicao_invalida"]`
  - Use `GET /v2/empresas` (lista todas, requer master token) e filtre localmente
- **`/v2/empresas/{cnpj}` com token de empresa** → HTTP 401 (master-only)
- **`/v2/nfes_recebidas?cnpj=X`** funciona com token-da-empresa
- **`/v2/ctes_recebidos?cnpj=X`** retorna 404 — endpoint pode ter nome diferente

### Habilitação de recebimento
- Por padrão a Focus **não monitora notas recebidas** — precisa habilitar manualmente no painel pra cada CNPJ
- Após habilitar, `habilita_manifestacao=true`, `habilita_manifestacao_cte=true`, `habilita_nfsen_recebidas_producao=true`
- **Não puxa histórico retroativo** — começa a capturar a partir da `data_inicio_recebimento_*` configurada
- Demora **até 24h** pro primeiro batch chegar via DF-e

### Estado atual das 4 empresas do user
| CNPJ | Empresa | Manifestação NFe | Manifestação CTe | NFSe rec |
|---|---|---|---|---|
| 10.930.732/0001-34 | **JOVELINO** | ✅ | ✅ | ✅ |
| 47.870.071/0001-09 | HC GESTAO | ❌ | ❌ | — |
| 63.052.142/0001-12 | ROCA | ❌ | ❌ | — |
| 38.387.077/0001-39 | LULIT SOLUTIONS | ❌ | ❌ | — |

**TODO usuário**: habilitar manifestação no painel Focus pras outras 3.

---

## 8. Comandos úteis pra retomar

### Subir o ambiente
```bash
# Backend
cd C:/dev/pac-xml-downloader/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend
cd C:/dev/pac-xml-downloader/frontend
npm run dev
```

### Validar Serpro/Focus tá funcional
```bash
cd backend
python -c "
from app.providers.integra_contador import IntegraContadorProvider
p = IntegraContadorProvider()
a, j = p.autenticar()
print('Serpro OK:', a[:30])

from app.providers.focus_nfe import FocusNFeProvider
from app.config import get_settings
f = FocusNFeProvider()
print('Focus empresas:', len(f.listar_empresas(get_settings().focus_master_token)))
"
```

### Direto Serpro/Focus (sem app)
```bash
# Focus — listar empresas
curl -u "M2gM9HGvuHCT60qCn9EpbAWv81QwoFoI:" \
  "https://api.focusnfe.com.br/v2/empresas" | jq

# Focus — recebidas JOVELINO
curl -u "43RwJOtxyNxzPiXFBamLmHE6qeT5xVsa:" \
  "https://api.focusnfe.com.br/v2/nfes_recebidas?cnpj=10930732000134" | jq
```

---

## 9. TODO list pra próxima sessão

### 🟢 Alta prioridade (você decidir)
- [ ] **Pesquisar API de CND** — comparar Infosimples vs Direct Data vs outras (item 2 deste doc)
- [ ] **Habilitar manifestação no painel Focus** para HC GESTAO, ROCA, LULIT (3 empresas)

### 🟡 Média prioridade (eu posso fazer)
- [ ] **Apagar 5 CNDs mock** da JOVELINO no banco
- [ ] **Disparar SITFIS real** uma vez que o cooldown Serpro passar (15min+)
- [ ] **Descobrir idSistema/idServico correto do DTE** — consultar catálogo Serpro Apicenter
- [ ] **Tentar OBTERPROCURACAO41 de novo** — pode estar fora do ar agora
- [ ] **Validar frontend visualmente** — F5 em `/empresas/5` confirmar tile Federal unificado

### 🟠 Baixa prioridade
- [ ] **Implementar scraping CND** depois que você escolher A/B/C
- [ ] **Alerta automático**: certificado A1 da JOVELINO vence 23/07/2026 (2 meses)
- [ ] **Manifestação automática** das NFes recebidas pra estender janela SEFAZ 90 dias
- [ ] **Encriptar tokens Focus** em repouso (Fernet com chave derivada de SECRET_KEY)

---

## 10. Outros endpoints Integra Contador prontos (não testados em produção)

Já estão no provider, prontos pra usar quando precisar:

- **PGDAS-D** (Simples Nacional):
  - `pgdas_transmitir_declaracao(cnpj, ano_mes, receita_bruta, receitas)`
  - `pgdas_gerar_das(cnpj, ano_mes)` → PDF + cod barras
  - `pgdas_consultar_ultima_declaracao(cnpj)`
  - `pgdas_consultar_extrato(cnpj, ano_mes)`
- **Pagamentos (PAGTOWEB)**:
  - `pagamentos_listar(cnpj, data_inicial, data_final)`
  - `pagamentos_emitir_comprovante(cnpj, numero_documento)` → PDF
- **Procurações**:
  - `consultar_procuracao(cnpj)` — útil pra validar antes de outras chamadas

---

---

## 11. ATUALIZAÇÃO 14:30 — Robô NFes-recebidas funcionando real

### Bug encontrado e corrigido
- Endpoint `baixar_xml_nfe_recebida` era `/v2/nfes_recebidas/{chave}/xml` (errado, 404)
- **Endpoint real**: `/v2/nfes_recebidas/{chave}.xml` (com extensão, não barra)
- Variável atualizada: `NFE_RECEBIDA_XML_ENDPOINT` em `focus_nfe.py`

### Resultado do robô na JOVELINO (janela 13/04 → 13/05)
```
processados: 27 · baixados: 26 · duplicados: 1 · erros: 0
```

26 XMLs reais persistidos em `storage/xmls/10930732000134/`, todos do fornecedor `SO INJECAO DISTRIBUIDORA LTDA`. Valores de R$ 24 a R$ 470.

### ⚠️ Limitação importante: resNFe vs nfeProc
O XML baixado por `/v2/nfes_recebidas/{chave}.xml` é o **`resNFe`** (resumo da DF-e da SEFAZ), não a NF-e completa. Contém:
- ✅ `chNFe` (chave 44 dígitos)
- ✅ `CNPJ` emitente
- ✅ `xNome` emitente
- ✅ `dhEmi` (data emissão)
- ✅ `vNF` (valor total)
- ✅ `nProt` (protocolo SEFAZ)
- ❌ `nNF` (número)
- ❌ `serie`
- ❌ `CFOP`
- ❌ Itens, impostos, NCM, etc.

**Pra ter a NF-e completa (`procNFe`)**, é necessário:
1. **Manifestar a NF** (POST `/v2/nfes_recebidas/{chave}/manifesto` com tipo "ciencia")
2. Aguardar Focus refazer a sync com a SEFAZ
3. Rebaixar via `.xml` — agora vem o XML completo

**TODO futuro**: implementar manifestação automática em batch logo após o robô listar. Sem isso, o robô atual cobre o suficiente pra dashboard e métricas básicas (quem vendeu pra empresa, quanto, quando), mas não pra apuração fiscal (precisa NCM, CFOP, item-a-item).

### Bug PDF mock antigo
A mensagem "Falha ao carregar documento PDF" vinha de uma `SituacaoFiscal` (id=6) gerada com `USE_MOCK_INTEGRA=true` antes — o "PDF" no disco tinha 40 bytes com conteúdo literal `"%PDF-1.4 mock SITFIS para..."`. Browser detecta o header `%PDF` e tenta renderizar, mas falha porque não é um PDF válido.

**Resolvido**: SituacaoFiscal apagada do banco + arquivo removido + 5 CNDs mock também limpas.

### Estado do banco (JOVELINO empresa_id=5)
- ✅ 26 NFes reais em `documentos_fiscais`
- ✅ 44 mensagens reais em `mensagens_ecac`
- ✅ Token Focus produção em `empresas`
- 🧹 0 CNDs (apagados os mocks, aguardando SITFIS real)
- 🧹 0 SituacaoFiscal (apagado o mock)

---

---

## 12. ATUALIZAÇÃO 16:00 — Manifestação + DANFE + decisão FiscalAPI

### Manifestação NFe destinatário (Ciência da Operação)

**Por que precisa:** Focus só libera XML completo (`procNFe`) e DANFE PDF DEPOIS que destinatário manifesta a operação. Sem manifestação, só temos o `resNFe` (resumo via DF-e).

**Implementado:**

1. `FocusNFeProvider.manifestar_nfe_recebida(token, chave, tipo)` — real (era stub)
   - Tipos válidos: `ciencia`, `confirmacao`, `desconhecimento`, `nao_realizada`
   - Body: `{"tipo": "ciencia"}` — Focus retorna status SEFAZ 135 quando aceito
2. `FocusNFeProvider.baixar_pdf_nfe_recebida(token, chave)` — GET `/v2/nfes_recebidas/{chave}.pdf`
3. `RoboXMLService.manifestar_e_baixar_pdfs(empresa_id)`:
   - Lista todas NFes recebidas
   - Se não manifestou ainda (`json_original.manifestado_em` é falso), manifesta
   - Aguarda sync configurável
   - Re-baixa `.xml` (vira procNFe completo) e baixa `.pdf` (DANFE) ao lado
   - **Idempotente** via flag `manifestado_em` (não re-manifesta à toa)
4. Endpoint: `POST /api/v1/robo/manifestar?empresa_id=X&aguardar_sync_segundos=30`

**Bug SQLAlchemy** descoberto: mutar dict JSON in-place não dispara detecção de mudança. Solução:
```python
novo_raw = dict(raw)
novo_raw["manifestado_em"] = ...
doc.json_original = novo_raw
flag_modified(doc, "json_original")
```

**Resultado JOVELINO:** 26/26 NFes manifestadas (SEFAZ 135 OK), 1/26 com procNFe completo + DANFE 46.5KB. As outras 25 aguardando Focus sincronizar com SEFAZ — pipeline async pode levar até algumas horas.

### Latência do pipeline DF-e
```
[App] manifesta → Focus → SEFAZ aceita (135) → SEFAZ processa →
     SEFAZ libera XML completo via DF-e → próximo batch DF-e Focus →
     Focus expõe procNFe + DANFE pra download
```

Pode levar minutos ou horas — **depende da carga SEFAZ e do timing do batch DF-e da Focus**. Sem como acelerar. Recomendação: rodar `/robo/manifestar` no batch noturno (ex: 22h) — ao amanhã, todos os XMLs/PDFs estão prontos.

### ✅ Decisão CND escolhida: FiscalAPI

**Provider escolhido:** https://fiscalapi.com.br

**Cobertura confirmada:**
- ✅ CND Federal RFB+PGFN
- ✅ CRF FGTS Caixa
- ✅ CNDT Trabalhista TST
- ✅ CND Estadual ICMS (27 UFs)
- ✅ Retorna **`pdf_base64`** pra TODAS — diferencial vs Credify
- ✅ Status normalizado: `negativa`, `positiva`, `positiva_com_efeitos_de_negativa`, `nao_contribuinte`, `erro`
- ✅ URL de verificação (`url_verificacao`) pra autenticidade
- ✅ Cache server-side (`cached: bool`)
- ✅ Auth simples: header `X-API-Key: fapi_...`

**Plano escolhido:** **Starter R$ 50/mês = 500 consultas**

Cálculo realista (consultas **mensais** das 4 CNDs nas 120 empresas):
- 120 × 4 = **480 consultas/mês** (folga 20 no plano Starter)
- Custo anual: **R$ 600**

### Custo total atualizado PAC Download
| Item | Valor mensal |
|---|---|
| VPS Hostinger | R$ 100 |
| Focus NFe (Pro) | R$ ~250 |
| Serpro Integra | R$ ~150 |
| **FiscalAPI Starter** | **R$ 50** |
| **TOTAL** | **R$ 550/mês = R$ 6.600/ano** |

Comparado a **JeTax R$ 30.000/ano** → **economia R$ 23.400/ano** + auto-renovação real das CNDs.

### TODO próxima sessão (quando user voltar com API key FiscalAPI)
1. Criar `backend/app/providers/fiscalapi.py` com:
   - `FiscalApiProvider.consultar_cnd_estadual(uf, cnpj)`
   - `FiscalApiProvider.consultar_cnd_federal(cnpj)`
   - `FiscalApiProvider.consultar_crf_fgts(cnpj)`
   - `FiscalApiProvider.consultar_cndt_trabalhista(cnpj)`
   - Cada um retorna `CertidaoEmitida(pdf_bytes, status, validade, ...)`
2. Adicionar config no `.env`:
   ```
   USE_MOCK_FISCALAPI=false
   FISCALAPI_BASE_URL=https://api.fiscalapi.com.br
   FISCALAPI_API_KEY=fapi_...
   ```
3. Trocar `SefazRobotProvider` por `FiscalApiProvider` no `cnd_robo_service.py` para os tipos `FEDERAL_OFICIAL`, `FGTS`, `TRABALHISTA`, `ESTADUAL`
4. Manter SITFIS Integra Contador para `FEDERAL` (uso interno) — já real
5. Frontend: tirar texto "scraper pendente" dos tiles FGTS/Trabalhista/Estadual quando provider real estiver ativo

---

**Última atualização:** 2026-05-18 22:00 BRT
**Próxima ação esperada:** continuar Fase 2 do agente SEFAZ-GO em 19/05

---

## 14. NOTA 18/05 — Agente SEFAZ-GO v0 salvo em `agent/sefaz-go/`

User gravou o fluxo manual de download no portal SEFAZ-GO e o Claude Extension gerou um Selenium script v0. Salvo em:

- `agent/sefaz-go/sefaz_go_downloader.py` — script principal
- `agent/sefaz-go/requirements.txt` — deps
- `agent/sefaz-go/README.md` — status + roadmap

### Fluxo descoberto (validado pelo user)

1. URL: `https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/principal`
2. Botão "Acesso Por Certificado Digital" → Chrome popup nativo seleção de cert
3. Tela "Consulta Arquivos XML de Documentos Fiscais":
   - Dropdown CPF/CNPJ contribuinte
   - Período (data inicial / data final em DD/MM/YYYY)
   - Modelo (55/65 NFe/NFCe, 57 CTe, etc)
4. Cloudflare Turnstile aparece (badge "Verificando...") — passa em browser real
5. Botão "Baixar todos os arquivos" → modal com radio "Baixar somente documentos" → "Baixar"
6. Fica em fila → "Histórico de Downloads de XMLs" → status "Concluído" → ZIP fica disponível 7 dias
7. Formato do ZIP: `<CNPJ>_<DDMMYYYY-inicio>_<DDMMYYYY-fim>_<qtd>.zip`

### Pendências pra Fase 2 (próxima sessão)

1. **Refatorar pra Playwright** (melhor que Selenium pra mTLS + Cloudflare)
2. **Aguardar download** (poll na pasta) + extrair ZIP
3. **POST automático** no endpoint `/api/v1/documentos/upload-em-massa` (já implementado nessa sessão!)
4. **Ler empresas** do banco PAC via API ao invés de Excel
5. **Login no PAC** com email/senha + reusar token JWT
6. **Distribuir como .exe** via PyInstaller

### Como o agente vai usar a infra que já existe

✅ Endpoint backend `POST /api/v1/documentos/upload-em-massa` (criado nesta sessão) já aceita ZIP da SEFAZ-GO e:
- Detecta tipo NFe/CTe/NFSe pelo root XML
- Roteia por CNPJ emitente/destinatário
- Decide origem "emitida" vs "recebida"
- Idempotente (unique constraint chave_acesso)
- Retorna detalhes por arquivo

Testado real com 2 NFes emitidas da JOVELINO (NFe 2 e 3 de 06-07/11/2025) → persistidas como `origem=emitida` corretamente.

### Outras entregas dessa sessão (18/05)

- **Migração 0013**: campos `cancelada`, `cancelada_em`, `motivo_cancelamento`, `protocolo_cancelamento` em `documentos_fiscais`
- **Detecção de NFes canceladas**: parser regex em `procEventoNFe descEvento=Cancelamento`. Resultado: **6 NFes da JOVELINO marcadas como canceladas** (todas com motivo "peça errada" da SO INJECAO DISTRIBUIDORA)
- **Tela Caixa Postal eCAC dedicada**: `/empresas/[id]/caixa-postal` com filtros + busca + expansor HTML + sync + marcar lidas
- **Dashboard real**: 8 cards reais + top fornecedores + módulos com stats dinâmicos. Limpeza de 4 empresas mock (sobrou só JOVELINO real)
- **ApuracoesEmpresaCard**: card de PGDAS-D nas empresas Simples Nacional
- **Migration 0012**: cadastro empresa expandido (IE, IM, natureza jurídica, endereço completo, cert por empresa)
- **Auto-busca CNPJ via BrasilAPI**: 14 dígitos → preenche form automaticamente
- **Upload em massa via UI**: modal drag-drop em `/documentos` aceita ZIP/XML
- **Filtro de período em /documentos**: data_inicio/data_fim + 7 atalhos rápidos (mês atual/anterior/30d/60d/90d/ano/tudo)

---

## 13. NOTA — MDFe habilitada na JOVELINO (16:30)

User informou que **habilitou MDFe** no painel Focus para JOVELINO (CNPJ 10.930.732/0001-34).

**Não implementar ainda — só anotar.**

### Pendente fazer (próxima sessão, quando user pedir):

**Frontend — botões de manifestação:**

1. **Botão "Manifestar" em cada linha** da tabela `/documentos` (ao lado dos botões XML/PDF):
   - Chama `POST /api/v1/robo/manifestar-uma?documento_id={id}` (a criar no backend)
   - Tipo padrão: `ciencia`
   - Opção dropdown: `ciencia` / `confirmacao` / `desconhecimento` / `nao_realizada`
   - Desabilita se já manifestada (`json_original.manifestado_em` !== null)
   - Mostra status visual: "Manifestada em DD/MM" se já feita

2. **Botão "Manifestar todas pendentes"** no header da página `/documentos`:
   - Chama `POST /api/v1/robo/manifestar?empresa_id=X` (**já existe** — só plugar UI)
   - Mostra contador "X pendentes" antes de clicar
   - Toast com resultado: "Y manifestadas, Z já estavam, W PDFs baixados"

3. **Coluna "Manifestada" na tabela**:
   - Verde + data se sim
   - Pílula amarela "Pendente" + botão se não

4. **Filtro "Status manifestação"** no header (Todas / Manifestadas / Pendentes)

**Backend — endpoint p/ manifestação individual (faltando):**
```
POST /api/v1/robo/manifestar-uma
body: {"documento_id": 38, "tipo": "ciencia"}
```
Wrapper em torno de `provider.manifestar_nfe_recebida` + atualizar `json_original.manifestado_em` (já tem o pattern em `RoboXMLService.manifestar_e_baixar_pdfs`).

**MDFe — implementação futura:**

A Focus agora vai listar MDFes recebidos pra JOVELINO. Mas o robô atual só consome `/v2/nfes_recebidas` e `/v2/ctes_recebidos`. MDFe não é DF-e padrão — é canal separado SEFAZ. Precisaria:
- Verificar endpoint Focus pra MDFe recebidos (provavelmente `/v2/mdfes_recebidos`)
- Adicionar `TipoDocumento.MDFE` no enum (hoje só NFE/CTE/NFSE) — migration necessária
- Eventos MDFe são diferentes: encerramento, cancelamento, inclusão de condutor/DF-e (não é "ciencia")
- Frontend: adicionar MDFE no filtro de tipos

**Por ora**: MDFe fica como pendência mapeada. Não implementar até user pedir explicitamente.
