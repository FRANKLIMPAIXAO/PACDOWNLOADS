# Spec TRANSDECLARACAO11 — Transmissão PGDAS-D (Serpro Integra Contador)

> Pesquisado em 04/06/2026. Endpoint `POST /Declarar`, idSistema=PGDASD,
> idServico=TRANSDECLARACAO11, versaoSistema=1.0. `dados` vai como **string JSON**.

## ⚠️ DRY-RUN nativo (mecanismo de segurança)

- **`indicadorTransmissao=false`** → calcula/valida SEM transmitir (dry-run). Retorna valores apurados pela RFB sem gerar declaração definitiva. É o "calcular sem entregar".
- **`indicadorTransmissao=true`** → transmite de verdade, gera declaração + recibo.
- **`indicadorComparacao=true`** + `valoresParaComparacao[]` → RFB compara nossos valores com os dela; se divergir, INTERROMPE (código MSG_ISN_035 lista os dois conjuntos).

**Fluxo seguro**: 1ª chamada dry-run (false) → conferir → 2ª chamada real (true).

## Estrutura do objeto `dados`

```
{
  cnpjCompleto              string 14 díg
  pa                        number AAAAMM (ex 202105)
  indicadorTransmissao      boolean
  indicadorComparacao       boolean
  declaracao {
    tipoDeclaracao          number  1=Original, 2=Retificadora
    receitaPaCompetenciaInterno  number  RBT do PA mercado interno (regime competência)
    receitaPaCompetenciaExterno  number  RBT do PA exportação
    receitaPaCaixaInterno   number|null  (só se regime caixa)
    receitaPaCaixaExterno   number|null
    valorFixoIcms           number|null
    valorFixoIss            number|null
    receitasBrutasAnteriores [ { pa, valorInterno, valorExterno } ]  ← RBT12 meses anteriores
    folhasSalario           [ { pa: AAAAMM, valor } ]  ← Fator R / Anexo V
    naoOptante              objeto|null  (null no caso comum)
    estabelecimentos [ {
        cnpjCompleto        string 14 díg (matriz + cada filial)
        atividades [ {
            idAtividade     number
            valorAtividade  number
            receitasAtividade [ {
                valor                 number
                codigoOutroMunicipio  number|null  (ISS outro município)
                outraUf               string|null  (ICMS outra UF)
                qualificacoesTributarias [ ... ]  ← monofásico/ST/imunidade [INFERIDO]
                isencoes    [ { codTributo, valor, identificador } ]
                reducoes    [ { codTributo, valor, percentualReducao, identificador } ]
                exigibilidadesSuspensas  [ ... ]|null
            } ]
        } ]
    } ]
  }
  valoresParaComparacao [ { codigoTributo, valor } ]
}
```

### codTributo (confirmado)
| Código | Tributo |
|---|---|
| 1001 | IRPJ |
| 1002 | CSLL |
| 1003 | IPI (implícito) |
| 1004 | COFINS |
| 1005 | PIS/Pasep |
| 1006 | CPP (INSS patronal) |
| 1007 | ICMS |
| 1010 | ISS |

### isencoes / reducoes (confirmado verbatim)
```json
"isencoes":  [ { "codTributo": 1007, "valor": 100.00, "identificador": 1 } ]
"reducoes":  [ { "codTributo": 1007, "valor": 1500.00, "percentualReducao": 50.00, "identificador": 1 } ]
```

## Mensagens de retorno (confirmadas)
- `Sucesso-PGDASD-MSG_ISN_033` — transmitida com sucesso (retorna PA, nome, CNPJ, nº declaração)
- `Aviso-PGDASD-MSG_ISN_034` — transmitida FORA DO PRAZO (gera multa MAED + DARF)
- `EntradaIncorreta-PGDASD-MSG_ISN_035` — valores divergem (com indicadorComparacao=true)

## ⚠️ Lacunas [INFERIDO] — confirmar antes de transmissão real

1. **`qualificacoesTributarias[]`** estrutura interna exata (segrega monofásico PIS/COFINS, ST ICMS, imunidade). Páginas `dados_de_dominio` do Serpro estavam com HTTP 500. Pra receita normal: `qualificacoesTributarias: []`.
2. **JSON de retorno completo** (numeroDeclaracao, valoresDevidos[], detalhamentoDasCalculo, recibo base64, declaracaoPdf base64).

**IMPORTANTE pro PAC**: monofásico/ST precisam da qualificação correta senão a RFB taxa PIS/COFINS sobre receita monofásica (imposto a maior). Por isso o fluxo é: **dry-run primeiro**, comparar valor RFB com o calculator do PAC; se divergir no monofásico, refinar qualificacoesTributarias consultando dados_de_dominio (reconsultar quando o Serpro voltar).

## Mapeamento Calculator PAC → payload

| Calculator | Payload PGDAS-D |
|---|---|
| `total_normal + total_st + total_monofasico` (mercado interno) | `receitaPaCompetenciaInterno` |
| `total_exportacao` | `receitaPaCompetenciaExterno` |
| `receita_bruta` | soma interno + externo |
| `folha_12m` (mensal) | `folhasSalario[]` (fator R) |
| RBT12 meses anteriores | `receitasBrutasAnteriores[]` |
| empresa.cnpj | cnpjCompleto + estabelecimentos[0].cnpjCompleto |
| monofásico/ST | qualificacoesTributarias (refinar pós dry-run) |

## Fontes
- https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/cenarios_trial/cenarios_pgdasd/
- https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/solucoes/integra-sn/pgdasd/mensagens/
- Manual PGDAS-D RFB: https://www8.receita.fazenda.gov.br/simplesnacional/arquivos/manual/manual_pgdas-d_2018_v4.pdf
