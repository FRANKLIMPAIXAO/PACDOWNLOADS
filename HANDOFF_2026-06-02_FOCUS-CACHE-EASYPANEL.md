# HANDOFF 02/06/2026 — Focus cache Easypanel + roadmap Integra Contador real

> **Estado**: 🟡 Backend em prod NÃO está rodando o código novo. Easypanel mostra "deploy verde" mas a imagem container é antiga. Cache buster commitado pra forçar rebuild amanhã.
> **Próximo passo**: testar deploy `9d86c8f`, validar que pega código novo, depois partir pra Integra Contador REAL.

---

## 🎯 TL;DR — onde paramos

1. **HOJE fizemos** 4 commits novos sobre Focus (auto-cadastrar reusando cert A1 + UI individual + diagnóstico + timeout/try-except). Tudo no `origin/main`.
2. **Easypanel não está propagando o código novo**. Logs em prod mostram código pré-`132b9e7` (linha 104 = sync_empresa direto, sem try/except). Stack mostra Python 3.10 do `mcr.microsoft.com/playwright/python:v1.48.0-jammy` (imagem correta), mas com source code antigo.
3. **Cache buster commitado** (`9d86c8f`) no `Dockerfile.backend` pra invalidar TODAS camadas. Amanhã testamos o deploy.
4. **DESCOBERTA TARDE — CLAVEAUX NÃO ESTÁ no painel Focus** (confirmado por screenshot do `app-v2.focusnfe.com.br/minhas_empresas/empresas`). Empresas presentes: HC GESTÃO, JOVELINO, ROCA, LULIT, PAC INTELIGENCIA. Minha hipótese inicial de "CNPJ duplicado" estava ERRADA. Focus 500 da CLAVEAUX vem de outra causa — investigar amanhã (ver seção "🔍 Investigar Focus 500 CLAVEAUX").
5. **Próximo após validar Focus**: ativar Integra Contador REAL (cert escritório + `USE_MOCK_INTEGRA=false`).

---

## 🚨 BUG PRINCIPAL: Easypanel cache stale

### Sintomas (logs do backend em prod, hoje à noite)

```
POST /api/v1/empresas/7/focus/auto-cadastrar HTTP/1.1" 502 Bad Gateway
PUT  /api/v1/empresas/7/focus HTTP/1.1" 500 Internal Server Error
ERROR: Exception in ASGI application
  File "/app/app/routes/empresas.py", line 104, in cadastrar_ou_atualizar_focus
    return EmpresaIntegracaoService(db).sync_empresa(...)  # ← SEM try/except
  File "/app/app/providers/focus_nfe.py", line 108, in cadastrar_empresa
    return self._request(token_master, "POST", EMPRESAS_ENDPOINT, ...)
requests.exceptions.HTTPError: 500 Internal Server Error - {'status': 500, 'error': 'Internal Server Error'}
```

**Prova de que é código antigo**: no código atual (`132b9e7`), linha 104 é COMENTÁRIO (`# MESMO try/except do auto_cadastrar_focus...`). O `return EmpresaIntegracaoService(db).sync_empresa(...)` agora está na linha 108, **dentro de um `try:` block**.

### Frontend vê

- `POST /focus/auto-cadastrar` → 502 Bad Gateway em ~1.5s
- Content-Type: text/html (página erro Traefik, sem header CORS)
- Navegador bloqueia → `TypeError: Failed to fetch`

### Diagnóstico

8 commits backend NUNCA chegaram em prod (após mudança de imagem Docker em `abaedd4`):

```
9d86c8f build(docker): cache buster pra forcar rebuild backend
132b9e7 fix(focus): evitar 502 do proxy em cadastro Focus (timeout + try/except)
5ca71e2 diag(focus): expor body de erro do Focus + tratar CNPJ ja cadastrado
927a77e feat(focus): auto-cadastro Focus NFe reusando cert A1 salvo no PAC
8f9329d fix(mocks): Integra Contador retornar PDF VALIDO (8 endpoints)
b10f931 fix(agent): bridge env vars backend->agent
01cb964 diag: expor erro real do Playwright em prod
f9401a1 fix(deps): add httpx
bfe7584 fix(deps): brazilfiscalreport==2.1.0 nao existe, usar 0.7.7
```

Easypanel mostra deploys verdes mas a imagem em runtime é antiga. Causa raiz não-100%-certa — pode ser:
- Build cache Docker do Easypanel reaproveitando layers `COPY backend/`
- Easypanel pulando rebuild quando o commit "parece" similar
- Imagem antiga sendo reutilizada do registry interno

### O que tem que ser feito amanhã

1. Easypanel → serviço **backend** → Histórico → "Implantar" no commit **`9d86c8f`**
2. Após terminar, recarrega `/empresas/7` (CLAVEAUX) e clica **▶ Auto-cadastrar agora**
3. **Resultados esperados** (qualquer um valida que o código novo pegou):
   - HTTP 409 com texto "Esta empresa já está cadastrada na sua conta Focus NFe..."
   - HTTP 502 com texto "Focus NFe rejeitou o cadastro: 500 Internal Server Error - {'status': 500, ...}"
   - HTTP 504 com texto "Focus NFe demorou demais (> 45s)..."
4. **Se voltar 502 HTML + "Failed to fetch"** = cache ainda preso. Próximos passos:
   - No Easypanel: tentar **Stop → Start** do serviço backend (não Restart)
   - Ou: no painel do Easypanel, opção "Reconstruir" / "Build sem cache" / "Clear cache" (varia entre versões)
   - Último recurso: dropar a imagem manualmente via SSH no VPS:
     ```bash
     docker images | grep backend
     docker rmi <hash-da-imagem-antiga>
     # depois deploy novamente no Easypanel
     ```

---

## 🔍 Investigar Focus 500 CLAVEAUX (referência rápida)

### Por que descartamos "CNPJ duplicado"

Screenshot do painel Focus (`app-v2.focusnfe.com.br/minhas_empresas/empresas`)
em 02/06/2026 à noite mostra estas empresas cadastradas na conta do escritório:

| Nome | CNPJ | Status |
|---|---|---|
| HC GESTÃO DE CONTRATOS | 47.870.071/0001-09 | Válido até 19/02/2027 |
| JOVELINO E ACILDA LTDA | 10.930.732/0001-34 | ✅ Funcionou ontem |
| ROCA LTDA | 63.052.142/0001-12 | Válido até 07/10/2026 |
| LULIT SOLUTIONS | 38.387.077/0001-39 | Válido até 18/09/2026 |
| PAC INTELIGENCIA TRIBUTARIA | 37.165.535/0001-22 | Exclusivo |

**CLAVEAUX (Indústria de Laticínios) NÃO aparece**. Logo, Focus 500 ao
cadastrar NÃO é por duplicidade.

### Stack do erro (do log que pegamos)

```
File "/app/app/routes/empresas.py", line 104, in cadastrar_ou_atualizar_focus
    return EmpresaIntegracaoService(db).sync_empresa(...)
File "/app/app/services/empresa_integracao.py", line 74, in sync_empresa
    data = self.provider.cadastrar_empresa(...)
File "/app/app/providers/focus_nfe.py", line 108, in cadastrar_empresa
    return self._request(token_master, "POST", EMPRESAS_ENDPOINT, ...)
requests.exceptions.HTTPError: 500 Internal Server Error - {'status': 500, 'error': 'Internal Server Error'}
```

(Nota: linha 104 mostra código ANTIGO — stack vai mudar quando deploy
`9d86c8f` propagar. Mas a chamada Focus que retorna 500 é a mesma.)

### Hipóteses por ordem de probabilidade

1. **Senha do cert errada** (mais provável). Quando subimos o `.pfx` da
   CLAVEAUX no PAC, a senha pode ter sido digitada errada ou veio com espaço
   no final. O PAC SALVA cifrado sem validar, então a senha errada só explode
   na hora de usar — no Focus, vira 500.
   - Testar:
     ```bash
     openssl pkcs12 -in claveaux.pfx -info -noout -password pass:'SENHA-AQUI'
     ```
     Se devolver `MAC verified OK` = senha certa. Se `MAC verify failed` =
     senha errada.

2. **Cert vencido**. CLAVEAUX tem cert A1 vencido ou prestes a vencer →
   Focus rejeita. Checar `cert_a1_validade_ate` no PAC.

3. **CNPJ irregular na Receita**. Se `situacao_cadastral` da CLAVEAUX no PAC
   não for "Ativa" (pode ser "Suspensa", "Baixada", "Inapta") → Focus rejeita.

4. **Endereço/IE mal formatado**. Comparar campos cadastrais CLAVEAUX vs
   JOVELINO. CEP precisa de 8 dígitos, IE GO tem 9 dígitos.

5. **Focus tá com bug** intermitente — pouco provável, mas possível.

### Workaround pra desbloquear (se a investigação demorar)

Cadastrar CLAVEAUX MANUALMENTE pelo painel Focus
(`app-v2.focusnfe.com.br/minhas_empresas/empresas` → botão laranja **ADICIONAR
EMPRESA**). O painel pode dar mensagem de erro melhor que a API. Se aceitar,
copiar o token gerado e importar no PAC via "Importar token Focus".

---

## ✅ O que ficou pronto hoje (já em git)

### Backend

- **`backend/app/routes/empresas.py`**
  - `POST /empresas/{id}/focus/auto-cadastrar` — cadastra na Focus REUSANDO cert A1 + dados PAC. Trata 409 (CNPJ já cadastrado), 502 (Focus erro), 504 (timeout)
  - `POST /empresas/focus/auto-cadastrar-todas` — versão batch
  - `PUT /empresas/{id}/focus` (manual) — ganhou MESMO try/except do auto

- **`backend/app/providers/focus_nfe.py`**
  - `_request` aceita parâmetro `timeout` opcional (default 60s)
  - `cadastrar_empresa` agora usa `timeout=45s` (margem antes do Traefik cortar)
  - Error handler já expõe body Focus (commit anterior `5ca71e2`)

- **`backend/app/services/empresa_integracao.py`** — `sync_empresa` ainda intocada (já funcionava)

### Frontend

- **`frontend/lib/empresas.ts`**
  - `autoCadastrarFocus(empresaId)` → POST `/empresas/{id}/focus/auto-cadastrar`
  - `autoCadastrarFocusTodas()` → POST `/empresas/focus/auto-cadastrar-todas`
  - Types: `AutoCadastrarResultado`, `AutoCadastrarTodasResultado`

- **`frontend/app/empresas/page.tsx`** (lista de empresas)
  - Botão `🔗 Auto-cadastrar N no Focus` no header (só aparece se há elegíveis: ativa + cert A1 + sem focus_token)
  - Toast com resultado batch (sucesso/falhas/ja_tinham/sem_cert) + detalhes expansíveis

- **`frontend/app/empresas/[id]/page.tsx`** (página individual)
  - `FocusCard` ganhou bloco verde **▶ Auto-cadastrar agora** quando empresa tem cert A1 + sem focus_token
  - Mostra toast verde/vermelho com resultado
  - Botão manual virou secundário (label "Cadastrar manualmente (subir cert novo)")

- **`frontend/app/documentos/page.tsx`**
  - Botão `⬇ Sincronizar Focus NFe` + modal de empresa + período
  - Pull DF-e (NFes recebidas) via Focus distribuição

### Commits hoje (newest first)

```
9d86c8f build(docker): cache buster pra forcar rebuild backend no Easypanel
132b9e7 fix(focus): evitar 502 do proxy em cadastro Focus (timeout + try/except)
2528420 feat(focus): botão Auto-cadastrar destaque na tela individual da empresa
5ca71e2 diag(focus): expor body de erro do Focus + tratar CNPJ ja cadastrado
927a77e feat(focus): auto-cadastro Focus NFe reusando cert A1 salvo no PAC
67737b0 feat(docs): UI Sincronizar Focus NFe distribuicao (DF-e)
8f9329d fix(mocks): Integra Contador retornar PDF VALIDO (8 endpoints)
```

---

## 📋 Checklist pra amanhã, ordem de execução

### 1. Validar deploy backend (10 min)

- [ ] Easypanel → backend → Implantar `9d86c8f`
- [ ] Aguardar build verde + container Running
- [ ] Testar `▶ Auto-cadastrar agora` em CLAVEAUX → esperar HTTP 409 JSON (não 502 HTML)
- [ ] Se 502 persistir: ver seção "BUG PRINCIPAL" acima — Stop/Start ou Reconstruir sem cache

### 2. CLAVEAUX: descobrir motivo do Focus 500 (10-20 min)

⚠️ **Hipótese descartada**: CLAVEAUX NÃO está cadastrada no Focus (confirmado em
screenshot `app-v2.focusnfe.com.br/minhas_empresas/empresas` em 02/06 à noite).
Logo, não é caso de "CNPJ duplicado" — é Focus rejeitando o cadastro por outro
motivo (cert, senha, dados, situação irregular).

Plano de investigação:

- [ ] Após validar o deploy `9d86c8f`, clicar `▶ Auto-cadastrar agora` em
      CLAVEAUX e ler a mensagem de erro JSON real (não mais "Failed to fetch")
- [ ] Mensagem esperada: `Focus NFe rejeitou o cadastro: 500 Internal Server
      Error - {'status': 500, 'error': 'Internal Server Error'}` ou mais
      específica se Focus retornar algo melhor
- [ ] Causas prováveis (testar nessa ordem):
  1. **Senha do cert errada no PAC** — abre o `.pfx` localmente com `openssl
     pkcs12 -in claveaux.pfx -info -noout` usando a senha que tá salva no PAC.
     Se openssl rejeitar → senha foi salva errada. Refazer upload do cert.
  2. **Cert vencido ou revogado** — checar validade no PAC. Se vencido, pedir
     cert novo ao cliente.
  3. **CNPJ irregular na Receita** — consultar `situacao_cadastral` da CLAVEAUX
     no `/empresas/7`. Se NÃO for "Ativa", Focus rejeita.
  4. **Dado cadastral mal formatado** — CEP sem dígito, UF inválida, IE no
     formato errado pra GO. Comparar com JOVELINO (que funcionou).
  5. **Conta Focus bloqueada ou sem saldo** — checar painel.
- [ ] Se nada disso: abrir ticket Focus com o `request_id` (header do response
      Focus em caso de 500) pedindo motivo real.

Plano alternativo (workaround pra avançar enquanto debuga):

- [ ] Cadastrar CLAVEAUX MANUALMENTE pelo painel Focus
      (`app-v2.focusnfe.com.br/minhas_empresas/empresas` → ADICIONAR EMPRESA)
- [ ] Copiar token gerado → importar no PAC via `/empresas/7` → "Importar token
      Focus"
- [ ] Testar `⬇ Sincronizar Focus NFe` em /documentos (igual JOVELINO ontem)

### 3. AGIMED: subir cert A1 + auto-cadastrar (5 min)

- [ ] Em `/empresas/{AGIMED-id}` → subir `.pfx` + senha
- [ ] Clicar **▶ Auto-cadastrar agora** (botão verde)
- [ ] Esperar HTTP 200 → token salvo → badge "Token configurado"

### 4. 5 empresas do Excel: certs A1 + auto-cadastrar batch

- [ ] Subir cert A1 de cada uma (5 uploads)
- [ ] Em `/empresas` → botão `🔗 Auto-cadastrar N no Focus` no header → faz batch

---

## 🎯 PRÓXIMO ALVO: Integra Contador REAL

### Status atual

- ✅ **Mocks funcionando** em prod com PDFs válidos (commit `8f9329d`)
- ✅ Endpoints implementados: SITFIS, DAS Simples, DCTFWeb, CONSDECREC, GERARGUIA, PARCSN, PARCMEI, PARCFIPGFN
- ❌ `USE_MOCK_INTEGRA=true` ainda no `.env` de prod (consciência: nada chama Serpro de verdade)
- ❌ Cert do escritório (Procurador) não está no servidor — precisa subir
- ❌ Procurações em cada empresa ainda não verificadas

### O que precisa pra ativar

1. **Cert A1 do ESCRITÓRIO** (do contador, não da empresa) salvo num path do volume — geralmente `/app/storage/certs/escritorio.pfx`
2. **Variáveis de env no Easypanel backend**:
   ```
   USE_MOCK_INTEGRA=false
   INTEGRA_CERT_PATH=/app/storage/certs/escritorio.pfx
   INTEGRA_CERT_PASSWORD=<senha-cifrada-via-Fernet-OU-em-plain>
   INTEGRA_CONSUMER_KEY=<seu-key-Serpro>
   INTEGRA_CONSUMER_SECRET=<seu-secret-Serpro>
   ```
3. **Procuração em cada empresa** (no e-CAC, "Procurações" → o CNPJ do escritório precisa ter procuração ativa de cada empresa cliente — esse é o degrau real)
4. **Testar 1 chamada real** (SITFIS é a mais barata — só consulta status fiscal)

### Endpoints Integra Contador implementados (consultar `backend/app/providers/integra_contador.py`)

| Sistema | Serviço | Função no provider | Custo Serpro |
|---|---|---|---|
| SITFIS | obter situação fiscal | `obter_sitfis(cnpj)` | baixo (consulta) |
| DAS Simples | gerar DAS mês | `gerar_das(cnpj, ano_mes)` | médio |
| DAS Simples | listar DAS atrasados | `listar_das_atrasados(cnpj)` | baixo |
| DAS Simples | gerar DAS atualizado | `gerar_das_atualizado(cnpj, ano_mes)` | médio |
| DCTFWeb | gerar guia ativa | `gerar_guia_dctfweb(cnpj, ano_mes)` | médio |
| DCTFWeb | gerar guia em andamento | `gerar_guia_dctfweb_andamento(cnpj)` | médio |
| CONSDECREC | consultar declaração | `consultar_declaracao(cnpj)` | baixo |
| PARCSN | parcelamentos Simples | `listar_parcelamentos_sn(cnpj)` | baixo |
| PARCMEI | parcelamentos MEI | `listar_parcelamentos_mei(cnpj)` | baixo |
| PARCFIPGFN | parcelamentos PGFN | `listar_parcelamentos_pgfn(cnpj)` | baixo |

Plano de ativação:
1. Começar com **SITFIS** em UMA empresa só (CLAVEAUX) — provar fim-a-fim
2. Se OK, ativar tudo em todas
3. Cron mensal: gera DAS automático no dia 15

---

## 📂 Arquivos chave (referência rápida)

```
backend/
  app/
    routes/
      empresas.py            ← endpoints Focus auto/manual (linhas 80-285 sao focus)
      documentos.py          ← endpoint /robo/distribuicao Focus
    providers/
      focus_nfe.py           ← cliente Focus + timeout 45s no cadastrar_empresa
      integra_contador.py    ← cliente Serpro (mocks ainda — _mock_pdf_bytes)
    services/
      empresa_integracao.py  ← orquestracao Focus (sync_empresa)
  Dockerfile (NAO USADO em prod — Easypanel usa Dockerfile.backend da raiz)

frontend/
  app/
    empresas/page.tsx         ← lista + botao "Auto-cadastrar N no Focus"
    empresas/[id]/page.tsx    ← FocusCard com botao verde + manual fallback
    documentos/page.tsx       ← botao "Sincronizar Focus NFe" + modal
  lib/
    empresas.ts              ← autoCadastrarFocus / autoCadastrarFocusTodas
    documentos.ts            ← sincronizarFocusEmpresa / sincronizarFocusMultiempresas

Dockerfile.backend           ← RAIZ — USADO em prod (Easypanel build context = . )
docker-compose.production.yml
```

---

## 🔑 Credenciais & infra (memória rápida)

- **GitHub**: `https://github.com/FRANKLIMPAIXAO/PACDOWNLOADS.git`
- **VPS Hostinger**: `72.62.111.136` (Easypanel)
- **Backend URL**: `https://backend.72.62.111.136.nip.io`
- **Frontend URL**: `https://pacdownloads-frontend.ibm21x.easypanel.host`
- **Supabase**: `aws-1-us-east-2.pooler.supabase.com:5432` (session pooler)
- **Email user**: paixaoassessoriacontabil@gmail.com

### Empresas em prod

| ID | Empresa | Cert A1 | Focus token | Auto-cad |
|---|---|---|---|---|
| 6 | JOVELINO | ✅ | ✅ | OK (Focus REAL funcionou — 3 NFes importadas) |
| 7 | CLAVEAUX | ✅ | ❌ | precisa importar token manual (CNPJ duplicado na Focus) |
| ? | AGIMED | ❌ | ❌ | subir cert + auto-cadastrar |
| ? | 4-5 Excel | ❌ | ❌ | subir cert + batch auto-cadastrar |

### Resultado Robô SEFAZ-GO em prod (memória)

🎉 815 NFes baixadas em prod: 812 CLAVEAUX + 3 JOVELINO (execução #11 + posteriores)

---

## 🧪 Comandos úteis pra debug

```bash
# Ver commits backend que faltam aplicar
git log --oneline abaedd4..HEAD -- backend/

# Validar sintaxe Python backend antes de commit
cd backend && python -c "import ast; ast.parse(open('app/routes/empresas.py').read()); print('OK')"

# Type-check frontend
cd frontend && npx tsc --noEmit

# Testar endpoint auto-cadastrar via curl (substituir TOKEN_JWT)
curl -X POST 'https://backend.72.62.111.136.nip.io/api/v1/empresas/7/focus/auto-cadastrar' \
  -H 'Authorization: Bearer TOKEN_JWT' \
  -H 'Content-Type: application/json'
```

---

## 📝 Tasks abertas (TaskList)

- #13 testar ciclo completo agente SEFAZ-GO sem --dry-run
- #14 pré-produção: testar agente com várias empresas
- #20 DAS: trazer valor real no sync
- #22 PARCSN: enriquecer com OBTERPARC164
- #68 **Forçar rebuild Easypanel — backend prod com imagem antiga** ← AMANHÃ

---

## 🎉 Estado emocional do projeto

Sistema está **a 1 deploy de distância** de ter Focus NFe 100% funcionando em prod. Robô SEFAZ-GO já funciona em prod. Integra Contador roda em mock — 1 dia de trabalho pra ativar real. **Boa noite!** 🌙
