# Handoff — Agente SEFAZ-GO v2 (bugs corrigidos + integração PAC)

**Data:** 22/05/2026
**Status:** ✅ Bugs #10 e #11 fechados, sistema de agendamento integrado ao PAC.

Continuação direta do `HANDOFF_2026-05-21_AGENTE-SEFAZ-GO.md`.

---

## 1. O que mudou nesta sessão

### 1.1 Bug #10 — datepicker do SEFAZ-GO ignorava `.fill()` (CORRIGIDO)

**Causa raiz:** Portal usa **jQuery UI Datepicker** (input com `class="hasDatepicker"`). O widget mantém estado interno em `$.datepicker._curInst` — setar `value` direto não atualiza o widget.

**Solução:** Nova função `preencher_datepickers()` em `agent/sefaz-go/pac_sefaz_agent.py:409` com 3 camadas de fallback:
1. `$('#input').datepicker('setDate', new Date(y, m-1, d))` — API oficial
2. `click → fill → keyboard Tab` (fecha popup + dispara blur)
3. Dispatch DOM puro de `change` + `blur`

**Evidência de validação:**
```
datepicker: jQuery UI Datepicker disponivel? True
datepicker: ✓ Datas setadas via jQuery UI datepicker.setDate: 01/04/2026 — 30/04/2026
Período no DOM após setDate: inicio='01/04/2026' fim='30/04/2026'
```

### 1.2 Bug #11 — agente baixava ZIP antigo da tabela (CORRIGIDO)

**Causa raiz:** Código pegava `tr:has-text('Concluído').first` — primeira linha "Concluído" da tabela, que podia ser ZIP velho.

**Solução:** Nova versão de `aguardar_e_baixar_zip()` em `agent/sefaz-go/pac_sefaz_agent.py:836`:
- Filtra rows por `tr[id^="{cnpj}_{ddmmyyyy_ini}_{ddmmyyyy_fim}_"]`
- Entre os que sobram, escolhe o de **timestamp mais recente** (col-data)
- Aguarda essa linha específica virar "Concluído"
- Clica no `<a>` daquela linha (não de outra)

Estrutura da linha (descoberta no HTML salvo):
```html
<tr id="{cnpj}_{ddmmyyyy_ini}_{ddmmyyyy_fim}_{seq}.zip">
    <td class="col-situacao">Aguardando... | Concluído</td>
    <td class="col-arquivo">{filename}</td>
    <td class="col-data">DD/MM/YYYY HH:MM:SS</td>
    <td class="col-observacoes">Sem resultados</td>  <!-- importante! -->
    <td class="col-acoes"><a href="...arquivo/{filename}">Baixar XML</a></td>
</tr>
```

### 1.3 Sub-bug — caso "Sem resultados" não tratado (CORRIGIDO)

Descoberto durante o teste do bug #11: quando empresa não tem notas no período, portal retorna `situação="Concluído"` + `observações="Sem resultados"` **sem link de download**. Código ficava em loop esperando o link aparecer (nunca apareceria) até timeout (10min).

**Solução:**
- Novo dataclass `DownloadFila` com 3 estados: `zip_path` (sucesso), `sem_resultados` (vazio mas OK), `motivo_erro` (timeout/falha)
- JS agora captura `col-observacoes` também
- Se `situação="Concluído"` + observação contém "sem resultado"/"nenhum" → retorna imediatamente com `sem_resultados=True`
- `ResultadoEmpresa` ganhou flag `sem_resultados: bool = False`
- Resumo final mostra: `X com ZIP | Y sem notas | Z erros`

**Validação:** JOVELINO (empresa 5) sem notas em abril/2026 → terminou em **11 segundos de polling** (vs 10 min do timeout antigo):
```
Linha alvo: id=...01042026_30042026_7887.zip situacao='Aguardando...' (it 1)
Linha alvo: id=...01042026_30042026_7887.zip situacao='Concluído' observacoes='Sem resultados' (it 2)
✓ Linha alvo Concluída SEM RESULTADOS — período não tem notas pra esse CNPJ
==== Concluído: 0 com ZIP | 1 sem notas | 0 erros (total 1) ====
```

Exit code também ajustado: 0 quando `erros == 0`, mesmo com 0 ZIPs (sem_resultados é sucesso vazio).

---

## 2. Feature nova: Sistema de agendamento integrado ao PAC

### 2.1 Backend (novo)

**Modelo `ExecucaoRoboSefaz`** (`backend/app/models/execucao_robo_sefaz.py`):
| Campo | Tipo | Notas |
|---|---|---|
| id | int | PK |
| disparo | str | `cron` \| `manual` |
| uf | str | `GO` (preparado pra multi-UF) |
| status | str | `pendente` → `rodando` → `concluido` \| `erro` |
| periodo_inicio / periodo_fim | date | Janela buscada |
| empresa_id | int? | Null = todas as empresas |
| iniciado_em / finalizado_em | datetime | |
| total_empresas, com_zip, sem_notas, erros, persistidos, duplicados | int | Métricas agregadas |
| detalhes | json | Resumo bruto do agente (empresa-a-empresa) |
| motivo_erro | text | |

**Migration:** `backend/alembic/versions/20260522_0014_execucao_robo_sefaz.py`

**Service:** `backend/app/services/robo_sefaz_service.py`
- `criar_execucao(disparo, periodo, empresa_id)` — cria linha pendente
- `executar(execucao_id)` — spawn subprocess do agent, captura resumo JSON, atualiza métricas
- `listar(limit, offset, status)`, `obter(id)`
- Helper `janela_mes_anterior()` que retorna primeiro/último dia do mês anterior independente do dia atual

**Tasks Celery** (`backend/app/workers/tasks.py`):
- `executar_robo_sefaz_mensal` — cron mensal, cria execução `cron` + roda
- `executar_robo_sefaz_manual(execucao_id)` — continua execução manual já criada (via rota)

**Beat schedule** (`backend/app/workers/celery_app.py`):
```python
"robo-sefaz-mensal-dia5-03h": {
    "task": "app.workers.tasks.executar_robo_sefaz_mensal",
    "schedule": crontab(day_of_month=5, hour=3, minute=0),
},
```

**Rotas REST** (`backend/app/routes/robo_sefaz.py`, prefixo `/api/v1/robo-sefaz`):
| Verbo | Endpoint | Função |
|---|---|---|
| GET | `/agendamento` | Info do cron (estático no MVP) |
| GET | `/execucoes` | Lista paginada |
| GET | `/execucoes/{id}` | Detalhes (com info empresa-a-empresa) |
| POST | `/disparar` | Dispara agora (enfileira Celery, retorna 202 com a linha pendente) |

**Schemas Pydantic:** `backend/app/schemas/robo_sefaz_schema.py`

### 2.2 Frontend (novo)

**API client:** `frontend/lib/robo-sefaz.ts`
- Tipos `ExecucaoRoboSefaz`, `ExecucaoRoboSefazDetail`, `AgendamentoInfo`
- Funções `dispararRobo()`, `listarExecucoes()`, `obterExecucao()`, `obterAgendamento()`
- Helpers UI: `statusPillClass`, `statusLabel`, `formatarDuracao`, `formatarPeriodo`

**Página:** `frontend/app/robo-sefaz/page.tsx`
- Card "Agendamento mensal" (cron, UF, descrição)
- Botão "▶ Rodar agora" (dispara `POST /disparar`)
- Tabela de execuções (50 últimas, polling a cada 5s se há execução pendente/rodando)
- Modal de detalhes empresa-a-empresa ao clicar "Detalhes"

**Menu:** Link "Robô SEFAZ" adicionado em `frontend/components/app-header.tsx`.

**CSS:** Estilos `.modal-backdrop`, `.modal`, `.modal-header`, `.modal-body`, `.table-compact` adicionados em `frontend/app/globals.css`.

### 2.3 Como rodar em produção

1. **Agent** continua em `agent/sefaz-go/`. Variável de ambiente `SEFAZ_AGENT_DIR` permite mudar localização em produção.
2. **Backend** precisa do agent acessível via subprocess. Estrutura padrão:
   ```
   /opt/pac-xml/
   ├── backend/
   └── agent/sefaz-go/
   ```
   Default do service procura em `parents[3]/agent/sefaz-go` relativo a `services/robo_sefaz_service.py`.
3. **Celery worker** precisa rodar pra processar tasks `executar_robo_sefaz_mensal` e `executar_robo_sefaz_manual`:
   ```bash
   celery -A app.workers.celery_app worker --loglevel=info
   celery -A app.workers.celery_app beat --loglevel=info
   ```
4. **Timeout** do agent: padrão 8h (configurável via env `SEFAZ_AGENT_TIMEOUT_S`).

---

## 3. Tasks resolvidas / pendentes

### ✅ Resolvidas nesta sessão
- #10 Bug datepicker — fix com `setDate` + 3 fallbacks
- #11 Bug primeira linha Concluído — filtro por CNPJ_PERIODO + timestamp mais recente
- #12 Sistema de agendamento — modelo + migration + service + tasks + rotas + página
- **#17 Guias DAS Simples Nacional atrasadas** — modelo `GuiaDAS` + migration 0015 + service `GuiaDASService` + 5 rotas + Celery task diária + página `/das`
- **#18 Guias DAS atualizadas (valor corrigido)** — endpoint `POST /guias-das/{id}/atualizar` chama PGDASD GERARDAS12 da Serpro, salva PDF em `storage/guias/{cnpj}/das_{periodo}_{ts}.pdf`, retorna número DAS + código de barras. Botão "Atualizar" + "PDF" na UI
- **#16 Parcelamentos Simples (PARCSN ordinário)** — modelo `ParcelamentoSimples` + migration 0016 + service com PEDIDOSPARC163 (listar) + OBTERPARC164 (detalhe) + PARCELASPARAGERAR162 (parcelas disponíveis) + GERARDAS161 (emitir DAS de parcela) + 5 rotas + página `/parcelamentos-simples`. **Validado real: 7 parcelamentos JOVELINO importados, DAS parcela 05/2026 emitida (R$ 322,85, PDF 159KB).**
- **#21 Guias DCTFWeb (ativa + andamento)** — modelo `GuiaDctfweb` + migration 0016 + service com GERARGUIA31 + GERARGUIAANDAMENTO313 + 4 rotas + página `/dctfweb` com seletor categoria (40 GERAL_MENSAL, 41 13º, 45 ESPETACULO, 44 AFERICAO, 46 RECLAMATORIA etc) + ano/mês inteligente (desabilita mês pra 13º). **Validado real: DCTFWeb 04/2025 categoria GERAL_MENSAL emitida (PDF 117KB).**

### 🔄 Pendente
- **#13 Testar ciclo completo com upload PAC (sem `--dry-run`)** — falta empresa com NFes reais
  no portal pra validar o caminho "Concluído COM href" + upload PAC. JOVELINO não tem NFe em abril/2026.

### ✅ Fix do #19 + validação Serpro REAL (sessão 22/05 tarde)

Após Franklim fornecer o catálogo Serpro completo, descobri:

**Endpoints corretos identificados:**
- `CONSDECLARACAO13` (não `CONSDECREC13` que eu chutei) — lista declarações do ano
- `CONSDECREC15` — consulta declaração específica (mas só devolve PDF, sem JSON estruturado)
- `CONSEXTRATO16` — espera `numeroDas` (não `periodoApuracao`), também só PDF
- `GERARDAS12` — DAS no prazo
- **`GERARDASCOBRANCA17`** ← NOVO, descoberto via catálogo: DAS atrasada com Selic+mora atualizados (em produção desde 27/11/2024). Service agora escolhe automaticamente entre este e GERARDAS12.

**Estrutura real de resposta CONSDECLARACAO13:**
```json
{"anoCalendario": 2025, "periodos": [
  {"periodoApuracao": 202501, "operacoes": [
    {"tipoOperacao": "Original", "indiceDeclaracao": {"numeroDeclaracao": "...", "dataHoraTransmissao": "20250211142814"}},
    {"tipoOperacao": "Geração de DAS", "indiceDas": {"numeroDas": "...", "dasPago": true|false}}
  ]}
]}
```
- Refatorei `_upsert_declaracao` → `_upsert_periodo` pra entender essa estrutura
- O campo `dasPago` ELIMINA a necessidade do PAGAMENTOS71 (não preciso mais cruzar)

**Estrutura real de resposta GERARDASCOBRANCA17:**
```json
{"pdf": "<base64>", "cnpjCompleto": "...", "detalhamentoDas": {
  "numeroDocumento": "07202614593079936",
  "dataVencimento": "20250220",
  "dataLimiteAcolhimento": "20260525",
  "valores": {"principal": 948.08, "multa": 189.62, "juros": 160.51, "total": 1298.21},
  "composicao": [...]  // tributo a tributo (ICMS, ISS GO, ISS Aparecida, etc)
}}
```

**Validação E2E com produção (JOVELINO):**
- Sync 2025: 12 períodos importados, 3 pagas + 9 atrasadas detectadas corretamente
- Atrasos calculados: 125d até 459d
- Caminho #18 testado real: emitiu DARF com Selic+mora atualizados, PDF de 156KB salvo. Valor R$ 948,08 + R$ 350,13 mora = **R$ 1.298,21** corretamente capturado.

**TODO de melhoria (não bloqueia produção):**
- Valor `valor_principal` no sync inicial vem 0 porque CONSEXTRATO16/CONSDECREC15 só devolvem PDF. Pra ter valor real sem clicar "Atualizar" em cada uma: ou parsear o PDF (pdfplumber), ou chamar `GERARDASCOBRANCA17` pra cada uma no sync (custa 1 chamada Serpro/competência mas traz total preciso).

### 🎯 Pré-requisitos antes de subir em produção (anotado pelo user em 22/05)

> "antes de subir em produção, fazer testes com outras empresas, e puxar via a api do
> integra contador, parcelamentos divida ativa, receita, puxar guias simples nacional
> atrasadas e atualizadas já"

**Bloco A — Validação do agente SEFAZ-GO em escala (task #14)**
- Rodar com 3-5 empresas diferentes que tenham NFe REAL no portal em abril/2026 (não NFCe)
- Sem `--dry-run`: validar caminho `Concluído COM href → download ZIP → upload PAC` ponta a ponta
- Confirmar XMLs em `/documentos` após upload
- Validar idempotência (rodar 2x não duplica)
- Validar que Turnstile não bloqueia em fluxo multi-empresa (~30-90s entre captchas, 2Captcha aguenta)

**Bloco B — Integra Contador: parcelamentos + DAS (tasks #15, #16, #17, #18)**
1. **#15 — Parcelamentos PGFN (Dívida Ativa):** consulta + persiste em `parcelamentos_pgfn` + UI no card da empresa + worker semanal
2. **#16 — Parcelamentos RFB (Receita):** ordinário 60x, transação tributária, simplificado. Distinguir tipos porque regras de manutenção variam
3. **#17 — DAS Simples Nacional ATRASADAS:** sincronizar guias em aberto/vencidas via PGDASD13. Dashboard cruzando todas as empresas pra cobrança ágil
4. **#18 — DAS atualizadas (valor corrigido):** botão "Gerar guia atualizada" emite DARF corrigida com Selic + multa mora + juros. Salva PDF em `storage/guias/{cnpj}/`. Atenção à validade curta da guia

### Outras sugestões (post-MVP)
5. Subir Celery worker + beat e testar disparo via UI `/robo-sefaz`
6. Smoke test do botão "Rodar agora" da UI → confirma execução aparece na tabela com status `rodando` → muda pra `concluido`
7. Multi-UF: começar com SP. Estrutura `ExecucaoRoboSefaz.uf` já preparada
8. Tornar config do cron editável via UI (hoje hardcoded no beat_schedule). Tabela `agendamento_robo_sefaz` foi deixada de fora do MVP por simplicidade
9. Webhook do agent pro PAC ao terminar (ao invés de subprocess+poll) — daria menos lock em conexão e mais auditoria
10. Criptografar `focus_token` da empresa em repouso (Fernet com `SECRET_KEY` derivada). Hoje em texto puro (TODO documentado)

---

## 4. Arquivos alterados nesta sessão

### Backend
- `backend/app/models/__init__.py` — registra `ExecucaoRoboSefaz`
- `backend/app/models/execucao_robo_sefaz.py` — modelo novo
- `backend/app/services/robo_sefaz_service.py` — service novo
- `backend/app/routes/robo_sefaz.py` — rotas novas
- `backend/app/schemas/robo_sefaz_schema.py` — schemas novos
- `backend/app/workers/tasks.py` — 2 tasks novas
- `backend/app/workers/celery_app.py` — beat schedule mensal
- `backend/app/main.py` — registra router
- `backend/alembic/versions/20260522_0014_execucao_robo_sefaz.py` — migration nova

### Frontend
- `frontend/lib/robo-sefaz.ts` — camada API nova
- `frontend/app/robo-sefaz/page.tsx` — página nova
- `frontend/components/app-header.tsx` — link no menu
- `frontend/app/globals.css` — estilos `.modal*`, `.table-compact`

### Agent
- `agent/sefaz-go/pac_sefaz_agent.py`:
  - Função `preencher_datepickers()` (novo)
  - Função `aguardar_e_baixar_zip()` reescrita com filtro CNPJ_PERIODO
  - Dataclass `DownloadFila` (novo)
  - Flag `sem_resultados` em `ResultadoEmpresa`
  - Resumo final separa `com_zip / sem_notas / erros`
  - Exit code 0 quando erros=0 (mesmo com 0 ZIPs)

---

## 5. Snapshot do estado fiscal

- **Database:** SQLite local em dev. Migration `20260522_0014` aplicada.
- **Backend:** rodando localmente em `http://127.0.0.1:8000`.
- **Frontend:** Next.js (não rodando, `npm run dev` no diretório `frontend/`).
- **Celery worker:** **NÃO está rodando** no dev local. Precisa subir manualmente pra testar o disparo via UI.
- **Empresa de teste:** JOVELINO (id 5, CNPJ 10930732000134). Cert A1 válido. Sem NFe no portal SEFAZ-GO em abril/2026.
