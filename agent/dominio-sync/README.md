# Agente Domínio-Sync

Baixa automaticamente os XMLs do PAC pra uma pasta que o **Domínio** monitora —
sem clique humano. O Domínio importa sozinho, roteando cada nota pelo CNPJ.

```
PAC (nuvem) ──API──> este agente (seu servidor) ──grava──> pasta OneDrive
                                                                 │ espelha
                                                                 ▼
                                       máquina do Domínio (pasta monitorada)
                                       → importação automática por CNPJ
```

## Por que funciona

- O PAC **já tem** os XMLs (NFe via DF-e + robô SEFAZ; CTe via distribuição).
- O agente puxa **só o que é novo** (cursor incremental) e o que foi **manifestado
  tardiamente** (rescan dos últimos N dias).
- **Dedup por arquivo**: nunca regrava um XML que já está na pasta. E o Domínio
  ainda deduplica por chave — reenvio é inofensivo.
- **Escrita atômica** (`.tmp` + rename): o monitor do Domínio nunca pega arquivo
  pela metade.

## Setup (no servidor que tem o OneDrive)

1. **Python 3.10+** instalado.
2. Copie esta pasta (`dominio-sync/`) pro servidor.
3. Instale a dependência:
   ```
   pip install -r requirements.txt
   ```
4. Copie `config.example.env` → `config.env` e preencha:
   - `PAC_BASE_URL` = `https://api.pacgestao.com.br`
   - `PAC_EMAIL` / `PAC_PASSWORD` = um usuário **operador** do PAC (não precisa ser admin).
   - `PASTA_BASE` = a pasta do OneDrive que o Domínio vai monitorar.
   - `TIPOS` = `NFE,CTE` (fase 1).
5. Teste **sem gravar nada**:
   ```
   python dominio_sync.py --dry-run
   ```
   Ele lista quantos XMLs baixaria. Depois rode de verdade:
   ```
   python dominio_sync.py
   ```
6. Confira a pasta — os XMLs devem aparecer em `<base>/<CNPJ>/<AAAA-MM>/NFE|CTE/`.

## Configurar o Domínio (uma vez)

Na importação automática de XML do Domínio, aponte a **pasta monitorada** pra
`PASTA_BASE` (a mesma do `config.env`). Como ele roteia pelo CNPJ de dentro do
XML, não precisa mapear empresa por empresa.

> Se o seu Domínio **não varrer subpastas**, troque no `config.env`
> `LAYOUT=plano` — aí o agente joga todos os XMLs direto na pasta monitorada
> (nome `CNPJ_TIPO_chave.xml`).

## Agendar (Agendador de Tarefas do Windows)

Crie uma tarefa básica que roda a cada 1–2 horas:

- **Programa/script:** `python`
- **Argumentos:** `dominio_sync.py`
- **Iniciar em:** o caminho desta pasta (ex.: `C:\dev\dominio-sync`)
- Marque "Executar estando o usuário conectado ou não".

Ou via PowerShell (ajuste os caminhos):
```powershell
$acao = New-ScheduledTaskAction -Execute "python" -Argument "dominio_sync.py" -WorkingDirectory "C:\dominio-sync"
$gatilho = New-ScheduledTaskTrigger -Once -At 7am -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "PAC Dominio-Sync" -Action $acao -Trigger $gatilho -RunLevel Highest
```

## Comandos

| Comando | O que faz |
|---------|-----------|
| `python dominio_sync.py` | Incremental + rescan (uso normal / agendado) |
| `python dominio_sync.py --dry-run` | Mostra o que baixaria, sem gravar |
| `python dominio_sync.py --reset` | Zera o cursor e re-baixa tudo (1ª carga / backfill) |
| `python dominio_sync.py --so-incremental` | Pula o rescan (rodada rápida) |
| `python dominio_sync.py --rescan-dias 30` | Rescan de 30 dias nesta rodada |

## Arquivos

- `config.env` — suas credenciais e a pasta (NÃO comitar; tem senha).
- `estado.json` — cursor (`ultimo_id`) e stats da última rodada.
- `logs/dominio_sync.log` — histórico de execução.

## Como o PAC entrega (backend)

`GET /api/v1/documentos/sync-manifest` (exige login):
- `desde_id` — cursor incremental (id > desde_id).
- `dias` — rescan: docs criados nos últimos N dias (pega manifestação tardia).
- `tipos` — `NFE,CTE,NFSE`.
- Só retorna doc com **XML completo** (`xml_path != ''`) — resumo nunca entra.

O XML em si vem por `GET /api/v1/documentos/{id}/download`.

## Roadmap

- **Fase 1 (agora):** NFe + CTe → pasta → Domínio importa.
- **Fase 2:** somar NFSe (ADN), após confirmar que o Domínio aceita o XML.
- **Fase 3:** painel no PAC com "última sincronização / XMLs por empresa".
