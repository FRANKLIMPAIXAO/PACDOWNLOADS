# Agente Domínio-Sync

Baixa automaticamente os XMLs do PAC pras pastas que o **Domínio** monitora —
sem clique humano. O Domínio importa sozinho via as rotinas automáticas.

```
PAC (nuvem) ──API──> este agente (servidor) ──grava──> pasta OneDrive
                                                            │ espelha
                                                            ▼
                                  máquina do Domínio (pastas monitoradas)
                                  → importação automática por <código>-<apelido>
```

## Como o Domínio acha a empresa (IMPORTANTE)

O Domínio **não** roteia pelo CNPJ do XML. Ele espera, dentro da pasta monitorada,
uma subpasta por empresa nomeada **`<código>-<apelido>`** (o *código* é o número
interno da empresa **no Domínio**), com os **XMLs soltos** lá dentro. E tem uma
**rotina de importação separada por tipo** (NF-e, NFC-e, CT-e, NFS-e), então cada
tipo vai pra uma pasta diferente.

Layout que o agente gera (`LAYOUT=dominio`):
```
XML-DOMINIO\
   NFE\   2-LATICINIOS CLAVEAUX\ <chave>.xml   ← NF-e (modelo 55)
   NFCE\  87-NEVES E MIRANDA\    <chave>.xml   ← NFC-e (modelo 65, cupom)
   CTE\   39-LG AGRO\            <chave>.xml   ← CT-e
   NFSE\  6-AGIMED\              <chave>.xml   ← NFS-e (Padrão Nacional / ADN)
```

### Configurar o Domínio (uma vez) — aponte cada rotina pra sua pasta:
| Importação no Domínio | Pasta |
|------------------------|-------|
| NF-e Arquivo XML | `...\XML-DOMINIO\NFE` |
| NFC-e Arquivo XML | `...\XML-DOMINIO\NFCE` |
| CT-e Arquivo XML | `...\XML-DOMINIO\CTE` |
| NFS-e Arquivo XML — **Padrão Nacional** | `...\XML-DOMINIO\NFSE` |

## O mapa CNPJ → código (`empresas_dominio.csv`)

O PAC só conhece o CNPJ; o *código* é interno do Domínio. O agente lê o arquivo
`empresas_dominio.csv` (colunas `cnpj,codigo,apelido`) pra nomear as pastas. Gere
ele da "Relação de Empresas" do Domínio. CNPJ fora do mapa cai em
`<TIPO>\_SEM_CODIGO\<cnpj>\` (nunca perde a nota — é só adicionar ao mapa).

## Setup (no servidor que tem o OneDrive)

1. Python 3.10+ e `pip install -r requirements.txt`.
2. `config.example.env` → `config.env`, preencha PAC_EMAIL/PAC_PASSWORD (operador)
   e PASTA_BASE (a pasta do OneDrive). Ajuste COMPETENCIA/MODELOS.
3. Coloque o `empresas_dominio.csv` ao lado do script.
4. Teste: `python dominio_sync.py --dry-run` → depois `python dominio_sync.py`.

## Recorte (config.env)

| Chave | Efeito |
|-------|--------|
| `COMPETENCIA=2026-06` | mês desejado (deriva data_min/max) |
| `MODELOS=55,65` | 55=NF-e, 65=NFC-e (cupom). Só `55` = sem cupons |
| `TIPOS=NFE,CTE,NFSE` | tipos de documento |
| `EXCLUIR_CNPJS=...` | CNPJs a ignorar (ex.: empresa de altíssimo volume) |
| `DIAS_RESCAN=15` | rescan p/ manifestação tardia de recebida |

> Ao trocar de competência/modelos, rode uma vez com `--reset` (zera o cursor) pra
> varrer o novo recorte do zero. O dedup é por arquivo — não re-baixa o que já tem.

## Comandos

| Comando | O que faz |
|---------|-----------|
| `python dominio_sync.py` | Incremental + rescan (uso normal / agendado) |
| `python dominio_sync.py --dry-run` | Mostra o que baixaria, sem gravar |
| `python dominio_sync.py --reset` | Zera o cursor (re-varre o recorte) |
| `python reorg.py [--mover]` | Move XMLs do layout antigo (arvore) pro novo |

## Agendar (Agendador de Tarefas do Windows)

```powershell
$acao = New-ScheduledTaskAction -Execute "python" -Argument "dominio_sync.py" -WorkingDirectory "C:\dominio-sync"
$gatilho = New-ScheduledTaskTrigger -Once -At 7am -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "PAC Dominio-Sync" -Action $acao -Trigger $gatilho -RunLevel Highest
```

## Backend (PAC)

`GET /api/v1/documentos/sync-manifest` (login): `desde_id`, `dias` (rescan),
`data_min`/`data_max`, `modelos` (55/65), `cnpjs_excluir`, `tipos`. Só devolve doc
com XML completo. O XML vem por `GET /api/v1/documentos/{id}/download`.

## Arquivos locais (gitignored)
`config.env` (senha) · `empresas_dominio.csv` (mapa) · `estado.json` (cursor) ·
`logs/`.
