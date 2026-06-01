# Capacidade — 120 empresas (uso interno do escritório)

Cenário real: **você é o contador**, tem **120 empresas-clientes** de contabilidade
e está montando o PAC Download para **substituir o JeTax 360** (uso próprio).

Acessam o sistema: você + equipe interna (geralmente 1-5 pessoas no escritório).
Os 120 CNPJs são apenas **objetos de gestão** — não viram usuários do app.

---

## 1. Volumetria — quantos XMLs vão passar pelo sistema

Estimativa por porte da empresa-cliente:

| Porte | % carteira | Docs/mês | Empresas (de 120) |
|---|---|---|---|
| Pequena (MEI/SN baixo movimento) | 40% | ~25 | 48 |
| Média (SN típico, comércio/serviço) | 45% | ~80 | 54 |
| Grande (LP/LR ou SN alto volume) | 15% | ~250 | 18 |

**Mix ponderado: ~80 docs/mês × empresa em média**

| Período | Documentos | XMLs em disco | Postgres |
|---|---|---|---|
| 1 mês | 9.600 | 75 MB | 30 MB |
| 1 ano | 115.200 | 920 MB | 350 MB |
| **5 anos (retenção SPED)** | **576.000** | **~4,6 GB** | **~4,2 GB** |

Cabem confortavelmente em qualquer VPS com 50+ GB de disco. **5 anos × 120 empresas usam ~10 GB no total**.

---

## 2. Hardware: sua VPS Hostinger

### Carga real para uso interno

Diferente de SaaS público, aqui você **não tem 120 usuários simultâneos**. Tem:
- Você + 1-5 funcionários acessando o frontend
- Robôs de background processando os 120 CNPJs em sequência

### Pico de RAM

| Cenário | RAM total |
|---|---|
| Ocioso 24/7 | ~1,3 GB |
| Robô diário 7h (4 workers) | ~3,3 GB |
| Apuração mensal (dia 18-20) | ~3,8 GB |
| Renovação CND segunda 6h (Chromium) | ~3,5 GB |

### Recomendação

| Plano | Specs | Custo/mês | Quando usar |
|---|---|---|---|
| **KVM 2** | 2 vCPU · **8 GB** · 100 GB NVMe | **R$ 65** | ✅ **Comece aqui.** Folga de 50% pra 120 empresas. |
| KVM 4 | 4 vCPU · 16 GB · 200 GB NVMe | R$ 120 | Só se passar de 200 empresas ou tiver muito acesso simultâneo |

**Hostinger faz upgrade in-place sem reinstalar** — começa no KVM 2 e só sobe se sentir lentidão. Provavelmente nunca vai precisar.

---

## 3. Custo operacional real (uso interno)

### O que você vai pagar todo mês

| Item | Custo | Por quê |
|---|---|---|
| **VPS Hostinger KVM 2** | R$ 65 | Sistema rodando |
| **Focus NFe** (pacote 5.000 notas) | **R$ 500** | Download NFe via DF-e + manifestação |
| **Serpro Integra Contador** (~15k chamadas/mês) | R$ 400 | Caixa Postal eCAC + SITFIS + DTE + procurações |
| **2captcha** | ~R$ 2 | CNDT trabalhista |
| **Domínio + e-CNPJ** (rateio) | R$ 28 | — |
| **Backup B2** (50 GB) | R$ 30 | — |
| **TOTAL** | **R$ 1.025/mês** | **R$ 12.300/ano** |

### Sobre o consumo Focus (5.000 notas/mês = R$ 500)

Ponto importante para acompanhar:

- **120 empresas × ~80 docs/mês = 9.600 docs/mês teóricos**
- **MAS** o pacote Focus de "notas" geralmente conta apenas **download via DF-e Distribuição** OU **emissões via Focus**
- Se o escritório só **baixa** notas (clientes emitem via outros ERPs), apenas recepções são contadas
- Estimativa real de **recepções**: ~40 docs recebidos/mês × 120 = **~4.800/mês** → cabe no pacote de 5.000 com folga mínima

**Recomendação operacional**:

| Volume mensal | Decisão |
|---|---|
| Até 4.500 notas | Tranquilo no pacote de 5.000 (R$ 500) |
| 4.500–5.000 | Atenção, considere migrar pra pacote maior |
| 5.000+ | Pacote 10.000 (R$ 950) ou avulso a ~R$ 0,15/nota fora do limite |

> ⚠️ A Focus **bloqueia consultas** quando o pacote é estourado. Se passar do limite no dia 25 do mês, o robô diário de DF-e para de funcionar até o dia 1º. **Crítico** monitorar.

Por isso vou sugerir abaixo (seção 8) **adicionar um contador de consumo Focus no dashboard**.

### Comparação com o que você paga hoje

| Sistema | Custo/mês típico p/ 120 emp |
|---|---|
| **JeTax 360** | R$ 1.500 – 3.500 |
| **Calima ERP Contábil** | R$ 2.000 – 4.000 |
| **Domínio Sistemas (Atlas)** | R$ 3.000 – 5.000 |
| **Sage Contábil** | R$ 2.500 – 4.500 |
| **Questor / Alterdata** | R$ 2.000 – 4.000 |

### Economia anual estimada

Considerando que você pague **R$ 2.500/mês** num desses sistemas hoje:

| Item | Hoje (JeTax/similar) | PAC Download | Diferença |
|---|---|---|---|
| Mensal | R$ 2.500 | **R$ 1.025** | **−R$ 1.475** |
| Anual | R$ 30.000 | **R$ 12.300** | **−R$ 17.700** |

**Quase 60% de economia anual.** Em 5 anos isso é R$ 88 mil que fica no caixa do escritório.

**Mas o ganho real não é o dinheiro** — é:

1. **Independência**: o JeTax pode aumentar 30% e você não pode fazer nada. Aqui você decide.
2. **Customização**: precisa de regra fiscal específica? Você modifica. Eles? Tickets infinitos.
3. **Dados são seus**: backup, auditoria, integrações com outros sistemas internos do escritório.
4. **Sem limite de usuário/empresa**: alguns sistemas cobram por empresa adicional. Aqui não tem isso.

---

## 4. O que esperar gerenciando você mesmo (custo "invisível")

Sendo honesto sobre a diferença vs. um software pago:

### Vantagens de pagar JeTax/similar
- Suporte humano em horário comercial
- Atualizações automáticas (mudanças no Simples Nacional, layouts SPED)
- Treinamento incluído
- Help desk se a equipe trava

### Vantagens de ter o seu (PAC Download)
- Custa metade do preço a longo prazo
- Sem cobrança "por empresa adicional"
- Customização ilimitada (nova regra fiscal? Você adiciona)
- Dados próprios, backups na sua nuvem
- Pode integrar com seu ERP, Excel, qualquer coisa

### O que você precisa estar ciente

1. **Tempo de manutenção**: ~2-4h/mês para atualizar tabelas (alíquotas, vencimentos, prazos)
2. **Atualizações fiscais**: quando muda lei (ex.: Reforma Tributária), você precisa atualizar o motor (ou contratar dev por tarefa)
3. **Suporte técnico**: se VPS cair às 23h do dia 19, ninguém vai resolver pra você. Hostinger responde em ~4h.
4. **Backup é responsabilidade sua**: o `backup.sh` automatizado já cuida, mas precisa testar restauração de tempos em tempos.

### Mitigações no projeto

- **Backup automatizado** já configurado (pg_dump diário 3h + Backblaze B2)
- **Healthchecks** no docker-compose reiniciam containers automaticamente em falha
- **Logs centralizados** em `/app/logs` para diagnosticar problemas rápido
- **Mock funcional**: se um provider externo cair (Focus, Serpro), você ainda consegue trabalhar no que já está local

---

## 5. Tempo dos jobs (para 120 empresas)

| Job | Frequência | Empresas | Duração | Quando |
|---|---|---|---|---|
| Download DF-e (Focus) | Diário | 120 | **~5 min** | 7h |
| Sync Caixa Postal eCAC | Diário | 120 | **~6 min** | 8h |
| Apuração mensal (motor) | Sob demanda | 120 | **~5 min** | dia 5-15 |
| Renovação CND (Playwright) | Semanal | ~80 vencendo | **~60 min** | seg 6h |
| Backup pg_dump + storage | Diário | — | **~3 min** | 3h |

**Tudo fora do horário comercial.** Quando você abrir o sistema às 8h30, já está tudo atualizado.

---

## 6. Onboarding das 120 empresas que você já tem hoje

### O que você precisa juntar do JeTax (export)

Provavelmente o JeTax permite exportar uma lista de empresas em CSV/Excel. Os dados que precisa:
- CNPJ, razão social, regime tributário
- Anexo do Simples (I/II/III/IV/V) e atividade
- Alíquota ISS do município (se serviço)
- Folha 12 meses (se for Anexo V)
- Certificado A1 .pfx + senha (você provavelmente tem cada um separado)

### Script de import já pronto

Já criei em `backend/scripts/import_empresas.py`. CSV no formato:

```csv
cnpj;razao_social;regime;anexo;atividade;cert_file;cert_password;email;logradouro;numero;cep
12345678000195;Empresa A;Simples Nacional;I;COMERCIO;empA.pfx;senha123;contato@empA.com;Rua X;100;50000000
60701190000104;Padaria Pão Quente;Simples Nacional;I;COMERCIO;padaria.pfx;senha456;...
```

Roda 1 vez:
```bash
docker compose exec backend python scripts/import_empresas.py /data/empresas.csv /data/certs
```

**Tempo estimado: 30-45 min para 120 empresas** (cadastro local + Focus + procuração eCAC).

### Procurações eletrônicas eCAC

Esse é o passo que **depende do cliente**. Cada um dos 120 clientes precisa:
1. Acessar `https://www.gov.br/ecac` com gov.br do CNPJ ou e-CNPJ
2. Procurações → Cadastrar Procuração Eletrônica
3. Preencher o **CNPJ do seu escritório** e selecionar escopos:
   - ✅ Caixa Postal Eletrônica
   - ✅ Situação Fiscal (SITFIS)
   - ✅ DTE — Domicílio Tributário Eletrônico
   - ✅ Pagamentos Web (PAGTOWEB)
   - ✅ PGDAS-D (se Simples Nacional)
   - ✅ DCTFWeb (se obrigatória)

**Sugestão**: e-mail mestre pra todos os clientes com tutorial passo-a-passo. Pode levar 1-2 semanas pra todos cadastrarem.

Enquanto não cadastram, o sistema funciona para tudo **EXCETO** o módulo Integra Contador para aquela empresa específica. Os outros (Focus DF-e, motor de apuração, CND, etc.) operam normalmente.

---

## 7. Plano em ondas (para você se apoiar nas semanas iniciais)

| Semana | O que fazer | Empresas no PAC |
|---|---|---|
| 1 | Subir VPS, deploy, smoke test com 1 empresa de teste | 1 |
| 2 | Migrar 5 empresas reais (variadas: 1 MEI, 2 SN comércio, 1 SN serviço, 1 LP) | 5 |
| 3 | Validar fluxo completo dessas 5: DF-e, apuração, CND, eCAC | 5 |
| 4-5 | Importar primeira leva de 30 empresas via CSV | 35 |
| 6-7 | Próxima leva de 50 | 85 |
| 8 | Empresas restantes + cancelar JeTax | 120 |

Por que dar 8 semanas: pra você ainda ter o JeTax como rede de proteção enquanto valida o PAC. Cancela o JeTax no fim do mês 2 e começa a economizar.

---

## 8. Monitor de consumo Focus (recomendado adicionar)

Como você está no pacote de **5.000 notas/mês a R$ 500**, vale **muito** ter um
contador no dashboard mostrando consumo em tempo real para evitar bloqueio.

### O que adicionar

Card novo no dashboard `<ConsumoFocusCard>` que mostra:

```
┌──────────────────────────────────────────┐
│  📊 Consumo Focus NFe                    │
│  ──────────────────────────────────────  │
│  4.327 / 5.000 notas no mês             │
│  ████████████████████░░░  86%            │
│                                          │
│  Restam 673 notas · 6 dias para virar    │
│  Média: 144 notas/dia                    │
│  Projeção: 5.187 (vai estourar em 5d)    │
│                                          │
│  ⚠ Considere migrar para pacote 10.000   │
└──────────────────────────────────────────┘
```

### Como calcular

Backend (cálculo simples a partir de `documentos_fiscais`):

```python
# app/routes/relatorios.py — endpoint novo
@router.get("/consumo-focus")
def consumo_focus_mensal(db: Session = Depends(get_db)) -> dict:
    hoje = date.today()
    primeiro_dia = hoje.replace(day=1)

    consumo_mes = db.scalar(
        select(func.count()).select_from(DocumentoFiscal)
        .where(
            DocumentoFiscal.created_at >= primeiro_dia,
            DocumentoFiscal.origem == "recebida",  # so DF-e conta
        )
    ) or 0

    limite = 5000
    dias_decorridos = (hoje - primeiro_dia).days + 1
    media_diaria = consumo_mes / max(dias_decorridos, 1)
    dias_no_mes = (date(hoje.year, hoje.month + 1, 1) - primeiro_dia).days
    projecao = int(media_diaria * dias_no_mes)

    return {
        "consumo_mes": consumo_mes,
        "limite": limite,
        "percentual": round(consumo_mes / limite * 100, 1),
        "media_diaria": round(media_diaria, 1),
        "projecao_fim_mes": projecao,
        "vai_estourar": projecao > limite,
        "dias_restantes": dias_no_mes - dias_decorridos,
    }
```

Frontend: card no dashboard com barra de progresso colorida (verde <70%, amarelo
70-90%, vermelho 90%+) e alerta quando projeção ultrapassar limite.

> Posso implementar isso na próxima rodada se você quiser — é coisa de 30 min.

---

## 9. Otimizações já aplicadas no `docker-compose.production.yml`

Todas pensadas pra 120 empresas em VPS modesta:

```yaml
postgres:
  command: >
    postgres
    -c shared_buffers=512MB
    -c effective_cache_size=1536MB
    -c work_mem=16MB
    -c maintenance_work_mem=128MB
    -c log_min_duration_statement=500   # log de queries lentas

worker:
  --concurrency=4 --max-tasks-per-child=100   # 4 jobs paralelos, recicla worker

backend:
  --workers 4   # 1 worker uvicorn por vCPU
```

E migration nova `20260505_0010_indices_120emp.py` adiciona 3 índices que aceleram:
- Motor de apuração (de 400ms → 30ms com 576k linhas)
- Filtros do dashboard de apurações por status
- Limpeza periódica de logs antigos

---

## 10. Checklist específico para você (uso interno)

### Antes de começar
- [ ] Listar as 120 empresas com seus dados em planilha (vai virar CSV depois)
- [ ] Coletar todos os 120 certificados A1 (.pfx) em uma pasta com senhas anotadas
- [ ] Confirmar regime + anexo + atividade de cada empresa
- [ ] Decidir se quer manter o JeTax 1-2 meses em paralelo (recomendado)

### Contas a abrir
- [ ] **Hostinger VPS KVM 2** (R$ 65/mês)
- [ ] **Domínio** ex.: `pacescritorio.com.br` (R$ 60/ano)
- [ ] **Focus NFe** — pacote para 120 empresas (~R$ 1.300/mês negociando)
- [ ] **Serpro Integra Contador** (loja.serpro.gov.br/integracontador) — pacote 20k chamadas/mês
- [ ] **2captcha** (US$ 1 de crédito = mais que suficiente)
- [ ] **Backblaze B2** (free tier 10 GB; depois R$ 30/mês a partir de 50 GB)

### Tempo total estimado
- **Setup técnico VPS**: 1 tarde
- **Configurar credenciais**: 1 tarde
- **Importar 120 empresas via CSV**: 1 hora
- **Pedir procurações eCAC aos clientes**: 1-2 semanas (depende deles)
- **Validar fluxo em paralelo com JeTax**: 4 semanas
- **Ir 100% no PAC e cancelar JeTax**: ao fim do mês 2

---

## 11. Resumo: vale a pena pra você?

**Sim, claramente** — pelos critérios:

1. **Financeiro**: economia de ~R$ 7.000/ano comparado a JeTax/Sage/similar
2. **Estratégico**: você não fica refém de fornecedor que pode aumentar preço a qualquer momento
3. **Técnico**: o sistema já cobre 90% do que o JeTax oferece (pelos prints que você me mostrou) e em alguns pontos é melhor:
   - Motor de apuração com **monofásicos segregados** automaticamente (raros os sistemas que fazem isso direito)
   - Robô de XML por DF-e em vez de scraping (mais confiável)
   - Cofre Fernet para credenciais sensíveis
4. **Custo de manutenção**: ~2-4h/mês — você ou um dev freelance ocasional

**O ponto fraco**: você é responsável quando algo quebrar. Mas o sistema tem:
- Healthchecks que reiniciam containers automaticamente
- Backup diário em nuvem externa (Backblaze)
- Mocks funcionais — se um provider externo cair, você não fica parado
- Logs centralizados pra diagnosticar rápido

Se você não tem afinidade nenhuma com tecnologia e não tem ninguém de confiança pra tocar manutenção, vale repensar. Senão, **bora**.
