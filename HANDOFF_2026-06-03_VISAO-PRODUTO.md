# HANDOFF 03/06/2026 — Visão de produto + roadmap revisado

> **Estado**: 🟢 Focus NFe distribuição funcionando em prod. CLAVEAUX integrada. 9 commits backend no remoto (último: `1e3139d` — JSON+base64 + datas DF-e). Frontend deployed.
> **Mudança estratégica HOJE**: do "construir PAC Downloads" pro **"substituir o Jettax 360"** — mas SEM ser cópia. Direção: produto superior aos 10 concorrentes analisados.
> **Próximo passo ao retomar**: definir Fase 0 do roadmap revisado (escolher 1-2 diferenciais pra atacar antes de migrar a carteira).

---

## TL;DR — em 5 bullets

1. **O Jettax é só UM modelo**. Analisamos hoje 10 sistemas (Domínio, Onvio, Questor, Alterdata, Sage, Calima, Folhamatic, e-Auditoria, Prosoft WK, Nibo) — ver [`docs/ANALISE-CONCORRENCIAL-2026.md`](docs/ANALISE-CONCORRENCIAL-2026.md).
2. **A carteira é 102 empresas**, 82% Simples Nacional, 97% em GO, 94% com cert digital. Dados completos em [`docs/CARTEIRA-PAC-TRIBUTARIA.md`](docs/CARTEIRA-PAC-TRIBUTARIA.md).
3. **PAC já é superior ao Jettax** em automação (Robô SEFAZ-GO baixou 815 NFes em prod ontem; Jettax não tem isso). Falta UI e camada de inteligência.
4. **3 diferenciais que ninguém faz bem** (top oportunidades): Reforma Tributária core • Inteligência de carteira • Comunicador tributário pro cliente final.
5. **Posicionamento sugerido**: "O sistema feito por contador que entende Reforma Tributária — não por engenheiro de software com consultor terceirizado".

---

## 1. Estado atual do sistema PAC

### O que funciona em prod (Easypanel + Supabase)

| Capacidade | Status | Evidência |
|---|---|---|
| Robô SEFAZ-GO baixando XMLs emitidos | ✅ | **815 NFes em prod** (812 CLAVEAUX + 3 JOVELINO) |
| Focus NFe Distribuição (DF-e) | ✅ | CLAVEAUX 200 OK, JOVELINO importou 3 NFes |
| Auto-cadastrar Focus (JSON+base64) | ✅ | Commit `1e3139d` pronto (falta deploy) |
| Endpoint `/version` pra debug | ✅ | Commit `d62e75e` |
| CNDs (RFB/PGFN, Trab, FGTS, Estaduais) | ✅ | Via Infosimples + Integra Contador |
| Parcelamentos PGFN + Simples + MEI | ✅ | |
| Guias DAS / DCTFWeb / FGTS Digital | ✅ | Em mock — falta cert escritório pra real |
| Diagnóstico cert A1 sem chamar Focus | ✅ | Commit `1e3139d` |
| 5 empresas cadastradas | ✅ | CLAVEAUX, JOVELINO, AGIMED, 2 outras |

### Commits pendentes de deploy (em ordem)

```
1e3139d fix(focus): JSON+base64 + data_inicio_recebimento_nfe/cte
d62e75e fix(robo): limite 25 NFes/request + endpoint /version
92d0c82 fix(robo): try/except em /robo/distribuicao
a5d2f3b fix(focus): flags obrigatórios (habilita_nfe, discrimina_impostos)
0e02c8a fix(focus): normalizar tipos (regime int)
9d86c8f build(docker): cache buster
132b9e7 fix(focus): timeout + try/except
2528420 feat(focus): botão Auto-cadastrar individual
5ca71e2 diag(focus): expor body de erro Focus
```

### Gaps conhecidos (técnico)

- 🔴 **Deploy 1e3139d** ainda não rodou → precisa ativar `/empresas/7/focus/ativar-recebimento` na CLAVEAUX
- 🟡 **Cert escritório (Procurador) não está no servidor** → bloqueia Integra Contador REAL
- 🟡 **USE_MOCK_INTEGRA=true ainda no .env de prod** → robô Integra retorna mocks
- 🟢 **97 das 102 empresas ainda fora do sistema** → migração Jettax pendente

---

## 2. Análise da carteira PAC Tributária (102 empresas)

> Dados completos em [`docs/CARTEIRA-PAC-TRIBUTARIA.md`](docs/CARTEIRA-PAC-TRIBUTARIA.md).

### Perfil dominante

- **82% Simples Nacional** (84 empresas) — alvo natural pra **Reforma Tributária / Simples Híbrido**
- **97% GO** — concentração geográfica → robô SEFAZ-GO atende a carteira inteira
- **94% têm cert digital ativo** — vencimentos espalhados em 2025-2027
- Apenas 11/102 têm login Prefeitura (poucas NFS-e) — desfoca esforço em NFS-e municipal
- 8 Lucro Real + 7 Lucro Presumido = 15 empresas que demandam ECD/ECF complexo
- 3 MEI — risco de estouro de R$ 81k (acompanhar com `apuracao-mei`)

### Insight estratégico

A carteira é **homogênea o suficiente pra automação massiva**: ~80 empresas SN-GO com cert A1, todas no mesmo SEFAZ, todas precisando do mesmo DAS mensal + CNDs trimestrais. **Um único robô bem feito atende 80% da operação**.

---

## 3. Análise concorrencial (resumo)

> Análise completa em [`docs/ANALISE-CONCORRENCIAL-2026.md`](docs/ANALISE-CONCORRENCIAL-2026.md).

### Lacunas COMUNS dos 10 concorrentes

1. **Suporte humano lento e despreparado** (Domínio, Onvio, Alterdata, Questor, Sage, Folhamatic, Prosoft, Jettax) — 4-14 dias de resposta, chat-only
2. **Instabilidade nos picos de obrigação** (Onvio sempre cai na primeira quinzena, Alterdata perde lançamentos) — justo nos dias 5/15/20/25
3. **Captura/conciliação XML com falhas** (Jettax falha na entrada, Onvio Messenger não entrega)

### Features killer que NENHUM faz bem

1. **Reforma Tributária end-to-end** — cClassTrib + simulador Híbrido Simples + monitor split payment embarcados em todas as telas
2. **Comunicação automatizada com cliente final** — Nibo chega perto, mas trata cliente como usuário do escritório
3. **Diagnóstico proativo de créditos retroativos** — só e-Auditoria tem (como módulo extra)

### O que cada concorrente faz BEM (copiar)

| De | Copiar |
|---|---|
| **Nibo** | UX moderna, app mobile, portal do cliente bonito |
| **e-Auditoria** | Motor de auditoria pré-SPED + diagnóstico de créditos |
| **Questor** | Robotização visível de obrigações (DCTFWeb, eSocial) |
| **Calima** | Modelo freemium (PAC Free até 10 empresas) |
| **Prosoft WK** | Legislação contextual dentro do lançamento |

### O que fazer DIFERENTE (ser superior)

1. **Reforma Tributária como CORE, não bolt-on** — todos correndo atrás, ninguém entregou
2. **Suporte humano radical** — gap tão grande que SLA 4h vira moat
3. **Inteligência de CARTEIRA, não por empresa** — painel de portfólio: quem virou Híbrido, quem tem crédito retroativo, quem corre risco split payment 2027
4. **Estabilidade nos picos** — Celery + autoscaling = "o sistema que não cai no dia 20"
5. **Voz autoral Família TributárIA** — comunicados automáticos no tom do Franklim → impossível de copiar

---

## 4. Visão de produto — o PAC que NÃO é cópia do Jettax

### Tese central

O Jettax (e todos os concorrentes) são **prontuários eletrônicos contábeis** — espelho digital das obrigações. O PAC deve ser um **agente fiscal proativo** — recomenda decisões, identifica oportunidades, executa rotinas sozinho.

### As 5 camadas do PAC

```
┌─────────────────────────────────────────────────────┐
│ 5. COMUNICADOR (Família TributárIA voz autoral)      │  ← Nenhum tem
│    WhatsApp/email pro cliente final automático       │
├─────────────────────────────────────────────────────┤
│ 4. INTELIGÊNCIA DE CARTEIRA                          │  ← Nenhum tem
│    Painel portfólio: 102 empresas, Reforma, créditos │
├─────────────────────────────────────────────────────┤
│ 3. REFORMA TRIBUTÁRIA EMBARCADA                      │  ← Diferencial #1
│    cClassTrib + Simulador Híbrido + Split Payment    │
├─────────────────────────────────────────────────────┤
│ 2. AUTOMAÇÃO (robôs Serpro + SEFAZ + Focus)          │  ← PAC já tem isso ✅
│    Robô SEFAZ-GO 815 NFes • Focus DF-e • Integra     │
├─────────────────────────────────────────────────────┤
│ 1. CADASTRO + REGISTROS (CRUD básico)                │  ← Commodity (igual Jettax)
│    Empresas, NFes, CNDs, parcelamentos, etc          │
└─────────────────────────────────────────────────────┘
```

**Camadas 1 e 2 a gente JÁ TEM** (parcialmente). É onde o Jettax para. Pra ganhar, **construir 3, 4 e 5** — e fazer 1 + 2 muito bem feito visualmente.

### Posicionamento de mercado

> **"O sistema feito por contador que entende Reforma Tributária — não por engenheiro de software com consultor terceirizado."**

**Público-alvo**: contadores de carteira 30-300 empresas, perfil técnico, dispostos a pagar 2x por algo que resolva Reforma Tributária E libere 20h/semana de obrigações repetitivas.

**Promessa**:
1. **Você nunca mais perde prazo** (automação + alertas)
2. **Seu cliente entende o que está pagando** (comunicador tributário)
3. **Você descobre dinheiro deixado na mesa** (diagnóstico de créditos)
4. **Você sabe a foto da sua carteira em 1 tela** (inteligência de portfólio)

---

## 5. Roadmap revisado (não é cópia Jettax)

### Fase 0 — TERMINAR Focus + ativar Integra REAL (esta semana)

Sem essa base, nada do resto faz sentido.

- [ ] Deploy `1e3139d` no Easypanel backend
- [ ] Verificar `/version` mostra commit correto
- [ ] Ativar recebimento DFe na CLAVEAUX (POST `/empresas/7/focus/ativar-recebimento`)
- [ ] Aguardar 24h e confirmar Focus puxa NFes recebidas da CLAVEAUX
- [ ] Subir cert do **escritório (Procurador)** no servidor → `/app/storage/certs/escritorio.pfx`
- [ ] Setar `USE_MOCK_INTEGRA=false` no Easypanel
- [ ] Testar 1 chamada Integra real: SITFIS na CLAVEAUX (consulta status fiscal)

### Fase 1 — Migrar 102 empresas do Jettax (semana 2)

- [ ] Endpoint `POST /empresas/importar-xlsx` (lê o XLSX direto)
- [ ] Cruza código IBGE com sheet cidades (importar 5573 cidades pra lookup local OU usar API IBGE)
- [ ] Mapeamento `SN → "Simples Nacional"`, `LR → "Lucro Real"`, etc
- [ ] Página `/empresas/importar` (drag + drop XLSX + preview + dry-run)
- [ ] Importar 102 empresas (dry_run primeiro, depois real)
- [ ] Upload em batch dos certs A1 (formato ZIP com `<CNPJ>.pfx` + planilha de senhas)
- [ ] Auto-cadastrar todas no Focus (endpoint batch já existe)

### Fase 2 — Inteligência de carteira (semanas 3-5)

**Esse é o primeiro diferencial real sobre todos os concorrentes.**

Dashboard novo `/carteira` cruzando os 102 clientes:

- [ ] **Painel de regime tributário** — gráfico distribuição + alertas (MEI próximo de R$ 81k, SN próximo de R$ 4,8mi)
- [ ] **Painel Reforma Tributária** — quantos viraram Híbrido, quantos pendentes de decisão, simulador batch
- [ ] **Painel de obrigações** — calendário consolidado com X obrigações vencendo nos próximos 7 dias
- [ ] **Painel de pendências** — quem tem CND vencida, quem tem mensagem e-CAC não lida
- [ ] **Painel financeiro** — DAS apurado vs pago, parcelamentos ativos por valor

### Fase 3 — Comunicador tributário (semana 6)

Segundo diferencial — comunicado automático pro cliente final.

- [ ] Tabela `comunicado_template` (rascunhos por evento: novo DAS, CND vencendo, mudança de lei)
- [ ] Editor de templates com voz Família TributárIA já configurada
- [ ] Integração WhatsApp (Twilio, Z-API ou Evolution API)
- [ ] Fila de envio assíncrono (Celery)
- [ ] Histórico de comunicados por cliente

### Fase 4 — Reforma Tributária core (semanas 7-10)

Diferencial #3 — embarcar no produto.

- [ ] Tabela `classificacao_ncm` (CST + cClassTrib por NCM, já temos skill `classificacao-ncm-reforma-tributaria`)
- [ ] Importador de planilha estoque (xlsx) — devolve classificação
- [ ] Simulador Híbrido Simples (já temos skill `analisador-cenarios-simples-nacional`) — rodar batch nas 84 SN
- [ ] Monitor split payment (alerta quando empresa-cliente é tomadora de serviço com retenção IBS)

### Fase 5 — Auditoria e créditos retroativos (semanas 11-12)

Inspirado em e-Auditoria mas embarcado.

- [ ] Importador SPED (EFD ICMS, EFD Contribuições, ECD, ECF)
- [ ] Motor de auditoria: detecta inconsistências (CFOP vs CST, valor PIS/COFINS divergente)
- [ ] Diagnóstico de créditos não aproveitados (Tema 69 STF, Tema 779 STJ, monofásicos)
- [ ] Relatório consolidado por cliente: "R$ X recuperáveis nos últimos 60 meses"

### Fase 6 — UI Tier 1 (semanas 13-14)

Tela de NFEs com totalizadores (tipo Jettax) — **só depois que as 5 camadas anteriores estiverem prontas**. Tela bonita é commodity; inteligência é o que vende.

### Fase 7 — Modelo freemium (semana 15)

- [ ] PAC Free: até 10 empresas, sem Integra Contador
- [ ] PAC Pro: até 100 empresas, com tudo
- [ ] PAC Enterprise: 100+ empresas, com SLA 4h e onboarding dedicado

---

## 6. Ordem de execução pra retomada

### Próximo passo IMEDIATO (segunda-feira)

1. **Deploy `1e3139d` no Easypanel backend**
   - Easypanel → backend → Histórico → Implantar
   - Aguardar verde
   - Abrir `https://backend.../version` → deve mostrar commit `1e3139d`

2. **Ativar DFe na CLAVEAUX**
   - DevTools Console em `/empresas/7`:
     ```javascript
     fetch('https://backend.../api/v1/empresas/7/focus/ativar-recebimento', {
       method:'POST',
       headers:{'Authorization':'Bearer '+localStorage.getItem('pac_xml_token')}
     }).then(r=>r.json()).then(j=>console.log(JSON.stringify(j,null,2)))
     ```
   - Esperar `{ok: true, data_inicio_recebimento_nfe: "2026-06-04", ...}`

3. **Decidir Fase 0 ou Fase 1**
   - **Fase 0** (Integra REAL): cert escritório + Serpro + procurações = 2-3 dias
   - **Fase 1** (migrar 102 empresas): importador XLSX + ZIP certs = 1 semana

Recomendação: **Fase 0 primeiro**. Sem Integra real, os 80 SN da carteira não geram valor. Com Integra real, cada empresa migrada já vem "viva" no sistema.

---

## 7. Decisões em aberto pra discussão

1. **WhatsApp pro comunicador**: Twilio (caro mas confiável) vs Z-API (BR, médio) vs Evolution API (open-source)?
2. **Tabela de cidades**: importar 5573 no PAC ou usar API IBGE on-demand?
3. **Reforma Tributária**: começamos pelo simulador SN-Híbrido ou pela classificação NCM?
4. **Pricing**: PAC Free vs PAC Pro vs PAC Enterprise — quanto cobrar?
5. **Marca**: o produto continua "PAC Downloads" ou vira algo como "TributárIA" alinhado à Família TributárIA?

---

## 8. Arquivos relacionados a essa estratégia

- [`docs/CARTEIRA-PAC-TRIBUTARIA.md`](docs/CARTEIRA-PAC-TRIBUTARIA.md) — 102 empresas detalhadas
- [`docs/ANALISE-CONCORRENCIAL-2026.md`](docs/ANALISE-CONCORRENCIAL-2026.md) — 10 sistemas analisados
- [`HANDOFF_2026-06-02_FOCUS-CACHE-EASYPANEL.md`](HANDOFF_2026-06-02_FOCUS-CACHE-EASYPANEL.md) — handoff anterior (Focus bug)
- Branch `main` no GitHub: `https://github.com/FRANKLIMPAIXAO/PACDOWNLOADS.git`

---

## 9. Boa noite 🌙

A gente saiu de "construir um sistema de downloads de XML" pra **"construir um agente fiscal proativo que substitui o Jettax E é superior aos 10 concorrentes"**. Salto enorme em uma sessão.

A boa notícia: **80% da automação já tá pronta** (Robô SEFAZ-GO, Focus, Integra). Falta colocar a **inteligência + comunicador + Reforma Tributária** por cima.

Quando retomar, lê esse handoff + os 2 docs anexos, e a gente decide se vai pela Fase 0 (Integra real) ou pula pra Fase 1 (migrar 102 empresas).

Boa pausa.
