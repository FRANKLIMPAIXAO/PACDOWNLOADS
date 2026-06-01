# PAC XML Downloader

Sistema interno para escritórios contábeis baixarem, organizarem e controlarem XMLs fiscais de clientes usando a **Focus NFe** como provider.

## O que esta entrega cobre

- Backend em FastAPI com SQLAlchemy, Alembic, Celery e Redis.
- Provider da Focus NFe com HTTP Basic Auth (token por empresa) e modo mock.
- Robô de download de NF-e RECEBIDAS via DF-e/manifestação do destinatário.
- Armazenamento físico de XML por empresa, ano e mês.
- Parser de XML com extração de dados essenciais.
- Relatório Excel em abas usando OpenPyXL.
- Frontend em Next.js com dashboard inicial profissional e autenticação real.
- Segurança básica com autenticação de usuários e segredo isolado no `.env`.

## Integração com a Focus NFe

Autenticação: HTTP Basic Auth com **token por empresa** (token como username, senha vazia). Não há OAuth, não há token global. Cada empresa cadastrada na Focus tem seu próprio token, salvo em `empresas.focus_token`.

Endpoints principais usados:

- `POST /v2/empresas` (multipart) — cadastra empresa + certificado A1 (.pfx) + senha.
- `GET /v2/empresas/{cnpj}` — consulta dados/cobertura.
- `PUT /v2/empresas/{cnpj}` (multipart) — atualiza dados ou troca certificado.
- `GET /v2/nfes_recebidas?cnpj=...&nsu=N` — lista NF-es recebidas (paginação por NSU).
- `GET /v2/nfes_recebidas/{chave}/xml` — baixa o XML de uma NF-e recebida.

O projeto continua funcionando ponta a ponta com `USE_MOCK_FOCUS_NFE=true` para validação local.

### Limitações conhecidas

- A Focus NFe **não oferece** endpoint para baixar XMLs de notas que a empresa cliente emitiu por outros sistemas (SAP, Bling, ERPs próprios). O robô diário cobre apenas NF-es **recebidas** (entradas) via DF-e/manifestação.
- A cobertura de NFSe varia por município (apenas prefeituras integradas com a Focus). NFSe ainda não está habilitada no robô.
- A janela de SEFAZ para distribuição é de **90 dias**. Manifestação automática (que estende essa janela) está pendente para o próximo ciclo.

## DF-e Distribuição (notas RECEBIDAS)

Para baixar XMLs de NF-es **emitidas contra o CNPJ da empresa** (entradas), o robô usa as notas recebidas da Focus NFe:

- `GET /v2/nfes_recebidas?cnpj={cnpj}&nsu={nsu}` — lista incremental.
- `GET /v2/nfes_recebidas/{chave}/xml` — baixa XML por chave.

**Pré-requisitos:**

- Empresa cadastrada na Focus NFe com certificado A1 ativo.
- `empresas.focus_token` preenchido (via `PUT /api/v1/empresas/{id}/focus/token` ou via cadastro multipart `PUT /api/v1/empresas/{id}/focus`).
- Janela SEFAZ: últimos **90 dias**.

**Persistência:**

- O último NSU consumido é gravado em `empresas.ultimo_nsu_distribuicao`. Execuções subsequentes não retornam documentos já processados.
- Os XMLs recebidos são gravados em `storage/xmls/{cnpj}/nfe/{ano}/{mes}/{chave}.xml`.
- `documentos_fiscais.origem` marca `recebida` para entradas (`emitida` reservado para futuro fluxo de emissão via Focus).

Exemplo de chamada:

```http
POST /api/v1/robo/distribuicao
Authorization: Bearer <token>
Content-Type: application/json

{
  "empresa_id": 1,
  "data_inicio": "2026-04-01T00:00:00",
  "data_fim": "2026-04-30T23:59:59"
}
```

## Estrutura

```text
pac-xml-downloader/
  backend/
  frontend/
  storage/
```

## Requisitos para Windows

1. Python 3.12+
2. Node.js 20+
3. PostgreSQL 15+
4. Redis 7+

## Local do projeto

`C:\dev\pac-xml-downloader\` (fora do OneDrive — OneDrive sincronizando arquivos
durante I/O do Node causa erros `UNKNOWN: unknown error, read` no Next.js).

## Backend no Windows

1. Abra o PowerShell em `C:\dev\pac-xml-downloader\backend`.
2. Crie o ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Instale as dependências:

```powershell
pip install -r requirements.txt
```

4. Copie `.env.example` para `.env` e ajuste:

```powershell
Copy-Item .env.example .env
```

5. Rode as migrations:

```powershell
alembic upgrade head
```

6. Suba a API:

```powershell
uvicorn app.main:app --reload
```

7. Em outro terminal, suba o worker do Celery:

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

8. Para o agendamento automático às 07:00, suba também o beat:

```powershell
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

## Frontend no Windows

1. Abra o PowerShell em `C:\dev\pac-xml-downloader\frontend`.
2. Instale os pacotes:

```powershell
npm install
```

3. Rode em desenvolvimento:

```powershell
npm run dev
```

## Robô SEFAZ — emissão automática de CNDs

Por padrão, todas as emissões usam **mocks** (`USE_MOCK_SEFAZ=true`). Para emitir
CNDs reais, é preciso:

### CNDT Trabalhista (TST) — pronto para ativar

1. Instalar Playwright e baixar o Chromium:
   ```powershell
   pip install playwright==1.48.0
   playwright install chromium
   ```
2. Criar conta em [2captcha.com](https://2captcha.com) (~US$ 1 / 1000 captchas)
   e copiar a `API_KEY`.
3. Editar `.env`:
   ```
   USE_MOCK_SEFAZ=false
   CAPTCHA_API_KEY=<sua-api-key>
   ```
4. Reiniciar o backend.
5. Em `/prevencao` clicar **🤖 Robô SEFAZ — renovar todas vencendo** ou em
   `/empresas/{id}` no card CND clicar **Renovar agora** no tile Trabalhista.

A cada execução o robô:
- Abre o portal `cndt-certidao.tst.jus.br/gerarCertidao.faces`
- Preenche CNPJ
- Lê o captcha de imagem e resolve via 2captcha (~5–15s)
- Submete formulário e baixa o PDF
- Detecta se a CND voltou **positiva** (com débitos) → marca como erro
- Em sucesso, salva PDF em `storage/cnds/{cnpj}/TRABALHISTA_{data}_{numero}.pdf`
  e cria nova `Certidao` válida por 180 dias

### CND Federal (RFB+PGFN) e CRF FGTS

Estão como stubs (raise SefazRobotError) — implementação na próxima rodada.
Federal é mais complexo (reCAPTCHA OU eCNPJ via SAML), FGTS exige Conectividade
Social Caixa.

### Worker semanal

Toda **segunda-feira às 6h** o Celery beat dispara
`renovar_cnds_vencendo(janela_dias=7)` automaticamente, renovando CNDs vencendo
ou já vencidas em todas as empresas ativas. Para isso o backend precisa estar
configurado com `USE_MOCK_SEFAZ=false`.

## Endpoints principais

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/empresas`
- `PUT /api/v1/empresas/{id}/focus` (multipart: `payload_json` + `senha_certificado` + `arquivo_certificado`)
- `PUT /api/v1/empresas/{id}/focus/certificado` (multipart: renovação só do certificado)
- `PUT /api/v1/empresas/{id}/focus/token` (importa token gerado no painel Focus)
- `GET /api/v1/empresas/{id}/focus/status`
- `GET /api/v1/documentos`
- `POST /api/v1/robo/empresa`
- `POST /api/v1/robo/multiempresas`
- `POST /api/v1/robo/distribuicao` (notas recebidas via DF-e)
- `GET /api/v1/relatorios/geral/excel`
- `GET /api/v1/relatorios/resumo-mensal`

## Fluxo recomendado de ativação

1. Comece com `USE_MOCK_FOCUS_NFE=true`.
2. Cadastre empresas no banco local (`POST /api/v1/empresas`).
3. Execute o robô manualmente (`POST /api/v1/robo/distribuicao`) e valide storage, parser e Excel.
4. No painel da Focus NFe, cadastre cada empresa real com o certificado A1 e copie o token gerado.
5. Importe cada token via `PUT /api/v1/empresas/{id}/focus/token`.
6. Altere para `USE_MOCK_FOCUS_NFE=false` no `.env`.
7. Execute o robô em produção e valide os XMLs reais em `storage/xmls/`.

## Melhorias sugeridas para a próxima etapa

- Tela no frontend para upload de certificado e import de token.
- Manifestação automática do destinatário (`POST /v2/nfes_recebidas/{chave}/manifesto`) para estender a janela SEFAZ além de 90 dias.
- Criptografia em repouso do `focus_token` (Fernet com chave derivada de `SECRET_KEY`).
- Cobertura de CT-e recebidos (provider já tem o método; falta integrar no `RoboXMLService`).
- Paginação, filtros e busca textual nas listagens.
- Observabilidade com Sentry e logs estruturados.
- Testes automatizados para parser e provider.
