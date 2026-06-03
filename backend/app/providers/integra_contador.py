"""Cliente para a API Integra Contador (Serpro).

Autenticacao
------------
1. POST https://autenticacao.sapi.serpro.gov.br/authenticate
   - Headers:
     * Authorization: Basic base64(consumer_key:consumer_secret)
     * Role-Type: TERCEIROS
     * Content-Type: application/x-www-form-urlencoded
   - Body: grant_type=client_credentials
   - Cert SSL: e-CNPJ A1 (.pfx) do contratante
   - Resposta: {access_token, jwt_token, expires_in (~33min)}

2. Em cada chamada de servico:
   - URL: {gateway}/(Apoiar|Consultar|Declarar|Emitir|Monitorar)
   - Headers: Authorization: Bearer {access_token}, jwt_token: {jwt_token}
   - Body padrao:
     {
       "contratante":     {"numero": cnpj_contratante, "tipo": 2},
       "autorPedidoDados":{"numero": cnpj_autor,       "tipo": 2},
       "contribuinte":    {"numero": cnpj_contribuinte,"tipo": 2},
       "pedidoDados": {
         "idSistema":     "<CAIXAPOSTAL|SITFIS|PROCURACOES|...>",
         "idServico":     "<MSGCONTRIBUINTE61|...>",
         "versaoSistema": "1.0",
         "dados":         "<JSON escapado em string>"
       }
     }

Mocks
-----
USE_MOCK_INTEGRA=true devolve fixtures deterministicos sem fazer chamada de rede,
util para desenvolver/testar sem credenciais Serpro reais.
"""
from __future__ import annotations

import base64
import json
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import requests

from app.config import get_settings


settings = get_settings()


# --- Path do gateway por categoria de servico ---
PATH_APOIAR = "/Apoiar"
PATH_CONSULTAR = "/Consultar"
PATH_DECLARAR = "/Declarar"
PATH_EMITIR = "/Emitir"
PATH_MONITORAR = "/Monitorar"


# --- Helper de PDF mock ---


def _mock_pdf_bytes(titulo: str, linhas: list[str] | None = None) -> bytes:
    """Gera um PDF VÁLIDO mínimo pra fixtures de mock.

    Antes os mocks retornavam `b"%PDF-1.4 mock SITFIS para CNPJ"` — uma string
    que começa como PDF mas NÃO é PDF válido. Browsers tentavam abrir e
    falhavam com "0 de 0 páginas" / "Algo deu errado".

    Esta função usa fpdf2 (já vem com brazilfiscalreport) pra gerar 1 página
    A4 com título + linhas. Pequeno (~1.5 KB) e abre em qualquer leitor.
    """
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        # ASCII-only pra evitar encoding errors do Helvetica core font
        titulo_safe = titulo.encode("latin-1", "replace").decode("latin-1")
        pdf.cell(0, 12, text=titulo_safe[:200],
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, text="(documento gerado em modo MOCK - somente teste)",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(8)
        if linhas:
            for linha in linhas[:30]:
                txt = str(linha).encode("latin-1", "replace").decode("latin-1")
                pdf.cell(0, 5, text=txt[:200],
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5,
                 text=f"Gerado em {datetime.now().isoformat(timespec='seconds')}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return bytes(pdf.output())  # fpdf2 retorna bytearray; converte pra bytes
    except Exception:
        # Fallback: PDF mínimo válido inline (1 página em branco A4).
        # Pra caso fpdf não esteja disponível por algum motivo.
        return (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f\n"
            b"0000000010 00000 n\n"
            b"0000000060 00000 n\n"
            b"0000000109 00000 n\n"
            b"trailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n170\n%%EOF\n"
        )


# --- Exceptions ---


class IntegraContadorError(Exception):
    """Erro generico Integra Contador."""


class IntegraAuthError(IntegraContadorError):
    """Falha na autenticacao Serpro (consumer-key/secret/cert)."""


class IntegraConfigError(IntegraContadorError):
    """Configuracao do .env incompleta para chamadas reais."""


class IntegraServicoError(IntegraContadorError):
    """Erro retornado por um servico (codigo + mensagem da Serpro)."""

    def __init__(self, codigo: str, mensagem: str, raw: Any = None) -> None:
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.raw = raw


# --- Token cache thread-safe ---


@dataclass(slots=True)
class IntegraTokenCache:
    access_token: str | None = None
    jwt_token: str | None = None
    expires_at: float = 0.0


# --- Provider ---


class IntegraContadorProvider:
    """Cliente HTTP da API Integra Contador.

    Stateless por requisicao mas mantem cache de token (refresh automatico).
    """

    def __init__(self) -> None:
        self.gateway_url = settings.serpro_gateway_url.rstrip("/")
        self.auth_url = settings.serpro_auth_url
        self.session = requests.Session()
        self._token_cache = IntegraTokenCache()
        self._token_lock = Lock()
        self._cert_tempfile: Path | None = None

    # --- Autenticacao ---

    def autenticar(self) -> tuple[str, str]:
        """Retorna (access_token, jwt_token) renovando se necessario."""
        if settings.use_mock_integra:
            return ("mock-access", "mock-jwt")

        with self._token_lock:
            if (
                self._token_cache.access_token
                and self._token_cache.jwt_token
                and self._token_cache.expires_at - time.time() > 120
            ):
                return (self._token_cache.access_token, self._token_cache.jwt_token)

            self._validar_config_real()
            credentials = f"{settings.serpro_consumer_key}:{settings.serpro_consumer_secret}"
            basic = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
            cert = self._cert_for_requests()

            try:
                response = self.session.post(
                    self.auth_url,
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Role-Type": "TERCEIROS",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data="grant_type=client_credentials",
                    cert=cert,
                    timeout=15,  # reduzido de 30s pra caber no orcamento total Traefik
                )
            except requests.RequestException as exc:
                raise IntegraAuthError(f"Falha de rede no auth Serpro: {exc}") from exc

            if response.status_code != 200:
                raise IntegraAuthError(
                    f"Auth Serpro retornou {response.status_code}: {response.text[:300]}"
                )

            payload = response.json()
            self._token_cache = IntegraTokenCache(
                access_token=payload["access_token"],
                jwt_token=payload["jwt_token"],
                expires_at=time.time() + int(payload.get("expires_in", 0)),
            )
            return (self._token_cache.access_token, self._token_cache.jwt_token)

    # --- Servicos: Caixa Postal eCAC ---

    def caixa_postal_listar(
        self,
        contribuinte_cnpj: str,
        *,
        status_leitura: str = "0",
        indicador_pagina: str = "0",
        ponteiro_pagina: str = "00000000000000",
    ) -> dict[str, Any]:
        """MSGCONTRIBUINTE61 - lista mensagens da caixa postal eCAC.

        - status_leitura: "0" todas, "1" lidas, "2" nao lidas
        - paginacao via indicadorPagina + ponteiroPagina
        """
        if settings.use_mock_integra:
            return self._mock_caixa_postal_lista(contribuinte_cnpj)
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="CAIXAPOSTAL",
            id_servico="MSGCONTRIBUINTE61",
            versao_sistema="1.0",
            dados={
                "statusLeitura": status_leitura,
                "indicadorPagina": indicador_pagina,
                "ponteiroPagina": ponteiro_pagina,
            },
        )

    def caixa_postal_detalhe(self, contribuinte_cnpj: str, isn_msg: str) -> dict[str, Any]:
        """MSGDETALHAMENTO62 - detalhe completo de uma mensagem (HTML/conteudo).

        Campo correto no payload Serpro: `isn` (nao isnMsg).
        """
        if settings.use_mock_integra:
            return self._mock_caixa_postal_detalhe(isn_msg)
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="CAIXAPOSTAL",
            id_servico="MSGDETALHAMENTO62",
            versao_sistema="1.0",
            dados={"isn": isn_msg},
        )

    def caixa_postal_indicador(self, contribuinte_cnpj: str) -> dict[str, Any]:
        """INNOVAMSG63 - indicador de novas mensagens (true/false).

        Categoria MONITORAR no catalogo Serpro (nao CONSULTAR).
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({"indicadorNovaMensagem": True, "qtdMsgNova": 2}),
            }
        return self._executar(
            PATH_MONITORAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="CAIXAPOSTAL",
            id_servico="INNOVAMSG63",
            versao_sistema="1.0",
            dados={},
        )

    # --- Servicos: Procuracoes ---

    def consultar_procuracao(self, contribuinte_cnpj: str) -> dict[str, Any]:
        """OBTERPROCURACAO41 - consulta procuracao ativa do contribuinte
        outorgada ao escritorio (autorPedidoDados)."""
        if settings.use_mock_integra:
            return self._mock_procuracao(contribuinte_cnpj)
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PROCURACOES",
            id_servico="OBTERPROCURACAO41",
            versao_sistema="1.0",
            dados={},
        )

    # --- Servicos: PGDAS-D (Simples Nacional) ---

    def pgdas_transmitir_declaracao(
        self,
        contribuinte_cnpj: str,
        *,
        ano_mes: str,           # "YYYYMM"
        receita_bruta: float,
        receitas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """TRANSDECLARACAO11 - transmite declaracao mensal PGDAS-D.

        `receitas`: lista de {atividade, codigoServico/cnae, valor} segregando
        receita por tipo. No mock retorna recibo + valor devido ficticio.
        """
        if settings.use_mock_integra:
            valor_devido = round(receita_bruta * 0.06, 2)  # mock 6% (DAS Anexo I médio)
            return {
                "status": 200,
                "dados": json.dumps({
                    "numeroDeclaracao": f"PGDAS-{ano_mes}-{contribuinte_cnpj[-6:]}",
                    "dataTransmissao": datetime.now(timezone.utc).isoformat(),
                    "recibo": f"REC-{ano_mes}-{int(time.time())}",
                    "valorDevido": valor_devido,
                    "receitaBruta": receita_bruta,
                    "competencia": ano_mes,
                }),
            }
        return self._executar(
            PATH_DECLARAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="TRANSDECLARACAO11",
            versao_sistema="1.0",
            dados={
                "periodoApuracao": ano_mes,
                "receitaBruta": receita_bruta,
                "receitas": receitas or [],
            },
        )

    def pgdas_gerar_das(
        self,
        contribuinte_cnpj: str,
        *,
        ano_mes: str,
    ) -> dict[str, Any]:
        """GERARDAS12 - gera DAS Simples Nacional em PDF (base64) + codigo de barras."""
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "numeroDocumento": f"DAS-{ano_mes}-{contribuinte_cnpj[-4:]}{int(time.time()) % 100000}",
                    "codigoBarras": "85800000000123456789012345678901234567890123",
                    "dataVencimento": f"{ano_mes[:4]}-{ano_mes[4:]}-20",
                    "valorTotal": 0.0,
                    "pdf": base64.b64encode(
                        _mock_pdf_bytes(
                            f"DAS Simples Nacional (mock)",
                            [f"Período de apuração: {ano_mes}"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="GERARDAS12",
            versao_sistema="1.0",
            dados={"periodoApuracao": ano_mes},
        )

    def pgdas_consultar_ultima_declaracao(
        self, contribuinte_cnpj: str
    ) -> dict[str, Any]:
        """CONSULTIMADECREC14 - consulta ultima declaracao + recibo."""
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "competencia": datetime.now().strftime("%Y%m"),
                    "numeroDeclaracao": f"PGDAS-MOCK-{contribuinte_cnpj[-6:]}",
                    "valorDevido": 1250.55,
                    "receitaBruta": 20842.50,
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="CONSULTIMADECREC14",
            versao_sistema="1.0",
            dados={},
        )

    def pgdas_consultar_declaracao(
        self, contribuinte_cnpj: str, *, numero_declaracao: str
    ) -> dict[str, Any]:
        """CONSDECREC15 - consulta declaração específica + recibo (pdf base64).

        Catálogo Serpro: PGDASD / CONSDECREC15 (código 1.5). Diferente do
        CONSEXTRATO16 (que pede número do DAS), este recebe o
        `numeroDeclaracao` retornado por CONSDECLARACAO13.

        Resposta inclui pdf da declaração (base64) e estrutura com valores
        apurados por tributo.
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "numeroDeclaracao": numero_declaracao,
                    "valorTotalDevido": 1250.55,
                    "pdf": base64.b64encode(
                        _mock_pdf_bytes(
                            "Recibo Declaração PGDAS-D (mock)",
                            [f"Número declaração: {numero_declaracao}"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="CONSDECREC15",
            versao_sistema="1.0",
            dados={"numeroDeclaracao": numero_declaracao},
        )

    def pgdas_gerar_das_cobranca(
        self, contribuinte_cnpj: str, *, ano_mes: str
    ) -> dict[str, Any]:
        """GERARDASCOBRANCA17 - gera DAS referente a período NO SISTEMA DE COBRANÇA RFB.

        Catálogo Serpro: PGDASD / GERARDASCOBRANCA17 (código 1.7), em produção
        desde 27/11/2024. **Mais apropriado que GERARDAS12 para DAS atrasadas**
        — usa a base de cobrança da RFB onde os valores já estão atualizados
        com Selic, multa de mora e juros até a data de hoje.

        Resposta esperada: idem GERARDAS12 — numeroDocumento, codigoBarras,
        dataVencimento, valorTotal, pdf (base64).
        """
        if settings.use_mock_integra:
            from random import seed, uniform
            seed(int(ano_mes))
            valor_base = round(uniform(800, 2000), 2)
            valor_atualizado = round(valor_base * 1.27, 2)  # mock Selic+mora ~27%
            return {
                "status": 200,
                "dados": json.dumps({
                    "numeroDocumento": f"DASCOB-{ano_mes}-{contribuinte_cnpj[-4:]}{int(time.time()) % 100000}",
                    "codigoBarras": "85800000000223456789012345678901234567890123",
                    "dataVencimento": (datetime.now().date()).isoformat()[:-2] + "30",
                    "valorTotal": valor_atualizado,
                    "valorOriginal": valor_base,
                    "selic": round(valor_base * 0.15, 2),
                    "multa": round(valor_base * 0.10, 2),
                    "juros": round(valor_base * 0.02, 2),
                    "pdf": base64.b64encode(
                        _mock_pdf_bytes(
                            "DAS Cobrança Atualizado (mock)",
                            [f"Período: {ano_mes}",
                             "Valor com Selic + multa de mora simulados"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="GERARDASCOBRANCA17",
            versao_sistema="1.0",
            dados={"periodoApuracao": ano_mes},
        )

    def pgdas_listar_declaracoes(
        self, contribuinte_cnpj: str, *, ano: str
    ) -> dict[str, Any]:
        """CONSDECLARACAO13 - lista todas as declarações PGDAS-D entregues no ano.

        Catálogo Serpro: PGDASD / CONSDECLARACAO13 (código 1.3) - "Consultar
        Declarações transmitidas". Em produção desde 23/09/2022.

        Resposta esperada: `{"declaracoes": [{competencia, numeroDeclaracao,
        valorDevido, dataTransmissao, recibo}, ...]}`.

        Útil pra varrer um ano inteiro de declarações com 1 chamada só (vs
        12× CONSULTIMADECREC14). Combinado com PAGAMENTOS71 indica quais DAS
        ficaram em aberto.
        """
        if settings.use_mock_integra:
            # Mock que reflete a estrutura REAL Serpro (CONSDECLARACAO13):
            # {anoCalendario, periodos: [{periodoApuracao, operacoes: [...]}]}
            from random import seed, choice
            seed(int(contribuinte_cnpj))
            periodos = []
            for mes in range(1, 13):
                competencia = f"{ano}{mes:02d}"
                pa_int = int(competencia)
                ts = f"{ano}{mes:02d}15083000"
                das_pago = choice([True, True, True, False])  # 75% pagas
                periodos.append({
                    "periodoApuracao": pa_int,
                    "operacoes": [
                        {
                            "tipoOperacao": "Original",
                            "indiceDeclaracao": {
                                "numeroDeclaracao": f"{contribuinte_cnpj[:8]}{competencia}001",
                                "dataHoraTransmissao": ts,
                                "malha": "",
                            },
                            "indiceDas": None,
                        },
                        {
                            "tipoOperacao": "Geração de DAS",
                            "indiceDeclaracao": None,
                            "indiceDas": {
                                "numeroDas": f"07{competencia}{int(time.time()) % 100000:05d}",
                                "datahoraEmissaoDas": ts,
                                "dasPago": das_pago,
                            },
                        },
                    ],
                })
            return {
                "status": 200,
                "dados": json.dumps({
                    "anoCalendario": int(ano),
                    "periodos": periodos,
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="CONSDECLARACAO13",
            versao_sistema="1.0",
            dados={"anoCalendario": ano},
        )

    def pgdas_consultar_extrato_das(
        self, contribuinte_cnpj: str, *, numero_das: str
    ) -> dict[str, Any]:
        """CONSEXTRATO16 - extrato detalhado de UM DAS específico.

        Catálogo Serpro: PGDASD / CONSEXTRATO16 (código 1.6). Diferente do que
        eu pensei antes — recebe `numeroDas` (que vem do `indiceDas.numeroDas`
        retornado por CONSDECLARACAO13), NÃO a competência.

        Resposta traz `valorTotalDevido` + `pdf` (base64) do extrato.
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "numeroDas": numero_das,
                    "valorTotalDevido": 1250.55,
                    "pdf": base64.b64encode(
                        _mock_pdf_bytes(
                            "Extrato DAS (mock)",
                            [f"Número DAS: {numero_das}"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="CONSEXTRATO16",
            versao_sistema="1.0",
            dados={"numeroDas": numero_das},
        )

    def pgdas_consultar_extrato(
        self, contribuinte_cnpj: str, *, ano_mes: str
    ) -> dict[str, Any]:
        """CONSEXTRATO16 (versão antiga / não recomendada).

        DEPRECATED: o catálogo Serpro mostra que CONSEXTRATO16 espera
        `numeroDas`, não `periodoApuracao`. Use `pgdas_consultar_extrato_das`
        em vez disso. Mantido só pra retrocompat / mock.
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "competencia": ano_mes,
                    "linhas": [
                        {"codigo": "ICMS", "valor": 380.00},
                        {"codigo": "IRPJ", "valor": 90.55},
                        {"codigo": "CSLL", "valor": 80.00},
                        {"codigo": "PIS",  "valor": 100.00},
                        {"codigo": "COFINS", "valor": 200.00},
                        {"codigo": "CPP",  "valor": 400.00},
                    ],
                    "valorTotal": 1250.55,
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PGDASD",
            id_servico="CONSEXTRATO16",
            versao_sistema="1.0",
            dados={"periodoApuracao": ano_mes},
        )

    # --- Servicos: PARCSN (Parcelamento Simples Nacional ordinario) ---

    def parcsn_listar_pedidos(self, contribuinte_cnpj: str) -> dict[str, Any]:
        """PEDIDOSPARC163 - lista pedidos de parcelamento PARCSN ordinario.

        Formato real Serpro: numero sequencial (1, 2, 3...) por empresa.
        Datas como int YYYYMMDD (ex: 20170112).
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "parcelamentos": [
                        {
                            "numero": 1,
                            "dataDoPedido": 20240115,
                            "situacao": "Encerrado por liquidação",
                            "dataDaSituacao": 20250531,
                        },
                        {
                            "numero": 2,
                            "dataDoPedido": 20251218,
                            "situacao": "Em parcelamento",
                            "dataDaSituacao": 20251223,
                        },
                    ],
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PARCSN",
            id_servico="PEDIDOSPARC163",
            versao_sistema="1.0",
            dados="",  # Serpro: ER_N007 se enviar {}
        )

    def parcsn_obter_parcelamento(
        self, contribuinte_cnpj: str, *, numero: int
    ) -> dict[str, Any]:
        """OBTERPARC164 - detalhe de UM parcelamento PARCSN."""
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "numero": numero,
                    "dataDoPedido": int(time.time() * 1000),
                    "situacao": "Em parcelamento",
                    "dataDaSituacao": int(time.time() * 1000),
                    "valorTotalConsolidado": 12500.55,
                    "quantidadeParcelas": 60,
                    "parcelasPagas": 12,
                    "valorTotalPago": 2500.00,
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PARCSN",
            id_servico="OBTERPARC164",
            versao_sistema="1.0",
            dados={"numero": numero},
        )

    def parcsn_listar_parcelas_geraveis(self, contribuinte_cnpj: str) -> dict[str, Any]:
        """PARCELASPARAGERAR162 - parcelas disponiveis pra emissao do DAS."""
        if settings.use_mock_integra:
            from datetime import date as _date, timedelta as _td
            hoje = _date.today()
            return {
                "status": 200,
                "dados": json.dumps({
                    "listaParcelas": [
                        {
                            "parcela": int((hoje + _td(days=30)).strftime("%Y%m")),
                            "valor": 250.55,
                        },
                        {
                            "parcela": int((hoje + _td(days=60)).strftime("%Y%m")),
                            "valor": 250.55,
                        },
                    ],
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PARCSN",
            id_servico="PARCELASPARAGERAR162",
            versao_sistema="1.0",
            dados="",  # ER_N007 se enviar {}
        )

    def parcsn_gerar_das_parcela(
        self, contribuinte_cnpj: str, *, parcela_ano_mes: int
    ) -> dict[str, Any]:
        """GERARDAS161 - emite DAS de UMA parcela PARCSN (PDF base64)."""
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "docArrecadacaoPdfB64": base64.b64encode(
                        _mock_pdf_bytes(
                            "DAS Parcelamento PARCSN (mock)",
                            [f"Parcela: {parcela_ano_mes}"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PARCSN",
            id_servico="GERARDAS161",
            versao_sistema="1.0",
            dados={"parcelaParaEmitir": parcela_ano_mes},
        )

    def parcsn_detalhar_pagamento(
        self, contribuinte_cnpj: str, *, numero_parcelamento: int, ano_mes_parcela: int,
    ) -> dict[str, Any]:
        """DETPAGTOPARC165 - detalhe de pagamento de uma parcela DAS PARCSN."""
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "numeroParcelamento": numero_parcelamento,
                    "anoMesParcela": ano_mes_parcela,
                    "valorPago": 250.55,
                    "dataArrecadacao": "2025-01-15",
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PARCSN",
            id_servico="DETPAGTOPARC165",
            versao_sistema="1.0",
            dados={
                "numeroParcelamento": numero_parcelamento,
                "anoMesParcela": ano_mes_parcela,
            },
        )

    # --- Servicos: DCTFWeb ---

    def dctfweb_gerar_guia(
        self,
        contribuinte_cnpj: str,
        *,
        categoria: str | int = "GERAL_MENSAL",
        ano_pa: str,
        mes_pa: str | None = None,
        dia_pa: str | None = None,
        cno_afericao: int | None = None,
        num_proc_reclamatoria: str | None = None,
        data_acolhimento_proposta: int | None = None,
        ids_sistema_origem: list[int] | None = None,
        numero_recibo_entrega: int | None = None,
    ) -> dict[str, Any]:
        """GERARGUIA31 - emite DARF DCTFWeb para declaracao na situacao ATIVA.

        Catalogo Serpro: DCTFWEB / GERARGUIA31 (3.1), em producao desde 23/09/2022.
        Categorias mais comuns: 40 GERAL_MENSAL, 50 PF_MENSAL, 41 GERAL_13o_SALARIO,
        51 PF_13o_SALARIO, 45 ESPETACULO_DESPORTIVO, 44 AFERICAO, 46 RECLAMATORIA.
        Resposta: PDFByteArrayBase64 (DARF pronto pra pagar).
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "PDFByteArrayBase64": base64.b64encode(
                        _mock_pdf_bytes(
                            "Guia DCTFWeb Ativa (mock)",
                            [f"Categoria: {categoria}",
                             f"Período: {mes_pa}/{ano_pa}"],
                        )
                    ).decode("ascii"),
                }),
            }
        dados: dict[str, Any] = {"categoria": categoria, "anoPA": ano_pa}
        if mes_pa is not None:
            dados["mesPA"] = mes_pa
        if dia_pa is not None:
            dados["diaPA"] = dia_pa
        if cno_afericao is not None:
            dados["cnoAfericao"] = cno_afericao
        if num_proc_reclamatoria is not None:
            dados["numProcReclamatoria"] = num_proc_reclamatoria
        if data_acolhimento_proposta is not None:
            dados["DataAcolhimentoProposta"] = data_acolhimento_proposta
        if ids_sistema_origem is not None:
            dados["idsSistemaOrigem"] = ids_sistema_origem
        if numero_recibo_entrega is not None:
            dados["numeroReciboEntrega"] = numero_recibo_entrega
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="DCTFWEB",
            id_servico="GERARGUIA31",
            versao_sistema="1.0",
            dados=dados,
        )

    def dctfweb_gerar_guia_andamento(
        self,
        contribuinte_cnpj: str,
        *,
        categoria: str | int = "GERAL_MENSAL",
        ano_pa: str,
        mes_pa: str | None = None,
        dia_pa: str | None = None,
        cno_afericao: int | None = None,
        num_proc_reclamatoria: str | None = None,
        ids_sistema_origem: list[int] | None = None,
    ) -> dict[str, Any]:
        """GERARGUIAANDAMENTO313 - emite DARF DCTFWeb para declaracao EM ANDAMENTO.

        Catalogo Serpro: DCTFWEB / GERARGUIAANDAMENTO313 (3.13), producao 28/03/2025.
        Igual ao GERARGUIA31 mas pra declaracoes que ainda nao foram transmitidas
        (apuracao em andamento). Util pra MIT (Lucro Real) usar categoria 40.
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "PDFByteArrayBase64": base64.b64encode(
                        _mock_pdf_bytes(
                            "Guia DCTFWeb em Andamento (mock)",
                            [f"Categoria: {categoria}",
                             f"Período: {mes_pa}/{ano_pa}"],
                        )
                    ).decode("ascii"),
                }),
            }
        dados: dict[str, Any] = {"categoria": categoria, "anoPA": ano_pa}
        if mes_pa is not None:
            dados["mesPA"] = mes_pa
        if dia_pa is not None:
            dados["diaPA"] = dia_pa
        if cno_afericao is not None:
            dados["cnoAfericao"] = cno_afericao
        if num_proc_reclamatoria is not None:
            dados["numProcReclamatoria"] = num_proc_reclamatoria
        if ids_sistema_origem is not None:
            dados["idsSistemaOrigem"] = ids_sistema_origem
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="DCTFWEB",
            id_servico="GERARGUIAANDAMENTO313",
            versao_sistema="1.0",
            dados=dados,
        )

    # --- Servicos: SITFIS (Situacao Fiscal) ---

    def sitfis_solicitar_protocolo(self, contribuinte_cnpj: str) -> dict[str, Any]:
        """SOLICITARPROTOCOLO91 - solicita protocolo p/ gerar relatorio fiscal.

        Resposta inclui `protocoloRelatorio` (string) e potencialmente
        `tempoEspera` (segundos a aguardar antes de chamar `sitfis_emitir_relatorio`).
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "protocoloRelatorio": f"MOCK-PROT-{contribuinte_cnpj}-{int(time.time())}",
                    "tempoEspera": 0,
                }),
            }
        return self._executar(
            PATH_APOIAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="SITFIS",
            id_servico="SOLICITARPROTOCOLO91",
            versao_sistema="2.0",
            dados="",  # body sem dados
        )

    def sitfis_emitir_relatorio(
        self, contribuinte_cnpj: str, protocolo: str
    ) -> dict[str, Any]:
        """RELATORIOSITFIS92 - emite o relatorio (PDF base64) usando o protocolo.

        Pode retornar `tempoEspera` > 0 indicando que ainda nao esta pronto;
        cabe ao chamador fazer retry.
        """
        if settings.use_mock_integra:
            # PDF fake: 1 byte do PDF header em base64
            return {
                "status": 200,
                "dados": json.dumps({
                    "tempoEspera": 0,
                    "pdf": base64.b64encode(
                        _mock_pdf_bytes(
                            "Relatório SITFIS (mock)",
                            [f"CNPJ: {contribuinte_cnpj}",
                             "Situação Fiscal Federal — relatório simulado",
                             "Sem pendências (modo desenvolvimento)"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="SITFIS",
            id_servico="RELATORIOSITFIS92",
            versao_sistema="2.0",
            dados={"protocoloRelatorio": protocolo},
        )

    # --- Servicos: Pagamentos (PAGTOWEB) ---

    def pagamentos_listar(
        self,
        contribuinte_cnpj: str,
        *,
        data_inicial: str,
        data_final: str,
    ) -> dict[str, Any]:
        """PAGAMENTOS71 - lista pagamentos realizados em um periodo (yyyy-mm-dd).

        Usa o sistema PAGTOWEB. Retorna lista com numeroDocumento, valor, data, etc.
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "pagamentos": [
                        {
                            "numeroDocumento": "0001234567890",
                            "codigoReceita": "0220",
                            "descricaoReceita": "DARF IRRF",
                            "dataArrecadacao": "2026-04-15",
                            "valorTotal": 1250.55,
                        },
                        {
                            "numeroDocumento": "0009876543210",
                            "codigoReceita": "1410",
                            "descricaoReceita": "DARF PIS/COFINS",
                            "dataArrecadacao": "2026-04-20",
                            "valorTotal": 480.22,
                        },
                    ],
                }),
            }
        return self._executar(
            PATH_CONSULTAR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PAGTOWEB",
            id_servico="PAGAMENTOS71",
            versao_sistema="1.0",
            dados={"dataInicial": data_inicial, "dataFinal": data_final},
        )

    def pagamentos_emitir_comprovante(
        self, contribuinte_cnpj: str, numero_documento: str
    ) -> dict[str, Any]:
        """COMPARRECADACAO72 - emite comprovante PDF (base64) de arrecadacao."""
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "pdf": base64.b64encode(
                        _mock_pdf_bytes(
                            "Comprovante de Arrecadação (mock)",
                            [f"Número documento: {numero_documento}"],
                        )
                    ).decode("ascii"),
                }),
            }
        return self._executar(
            PATH_EMITIR,
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema="PAGTOWEB",
            id_servico="COMPARRECADACAO72",
            versao_sistema="1.0",
            dados={"numeroDocumento": numero_documento},
        )

    # --- Servicos: DTE ---

    def dte_consultar(self, contribuinte_cnpj: str) -> dict[str, Any]:
        """Status de adesao ao Domicilio Tributario Eletronico.

        TODO: confirmar idSistema/idServico no catalogo Serpro. As tentativas
        com CAIXAPOSTAL/CONSULTASITUACAODTE111 deram Erro-052 (servico nao
        existe no catalogo). Mantido como mock-only ate ajuste.
        """
        if settings.use_mock_integra:
            return {
                "status": 200,
                "dados": json.dumps({
                    "cnpj": contribuinte_cnpj,
                    "indicadorOptante": True,
                    "dataAdesao": "2024-08-15",
                }),
            }
        # TODO: descobrir codigo correto consultando o catalogo Serpro.
        # Por ora, retorna estrutura vazia para nao quebrar callers.
        return {
            "status": 200,
            "dados": json.dumps({
                "cnpj": contribuinte_cnpj,
                "indicadorOptante": None,
                "_pendente": "endpoint DTE nao mapeado no provider",
            }),
        }

    # --- Helpers internos ---

    def _executar(
        self,
        path: str,
        *,
        contribuinte_cnpj: str,
        id_sistema: str,
        id_servico: str,
        versao_sistema: str,
        dados: dict[str, Any] | str,
        contribuinte_tipo: int = 2,
    ) -> dict[str, Any]:
        """Monta o body padrao Integra Contador, autentica e POSTa no gateway."""
        access_token, jwt_token = self.autenticar()
        body = self._montar_pedido(
            contribuinte_cnpj=contribuinte_cnpj,
            id_sistema=id_sistema,
            id_servico=id_servico,
            versao_sistema=versao_sistema,
            dados=dados,
            contribuinte_tipo=contribuinte_tipo,
        )

        try:
            response = self.session.post(
                f"{self.gateway_url}{path}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "jwt_token": jwt_token,
                    "Content-Type": "application/json",
                },
                json=body,
                cert=self._cert_for_requests(),
                timeout=15,  # reduzido de 120s — Traefik corta em ~60s. 2 chamadas back-to-back precisam caber.
            )
        except requests.RequestException as exc:
            raise IntegraContadorError(f"Falha de rede em {id_servico}: {exc}") from exc

        if response.status_code == 401:
            # Token expirado: forca refresh e tenta uma vez
            self._token_cache = IntegraTokenCache()
            access_token, jwt_token = self.autenticar()
            response = self.session.post(
                f"{self.gateway_url}{path}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "jwt_token": jwt_token,
                    "Content-Type": "application/json",
                },
                json=body,
                cert=self._cert_for_requests(),
                timeout=15,  # reduzido de 120s — Traefik corta em ~60s. 2 chamadas back-to-back precisam caber.
            )

        if response.status_code >= 400:
            try:
                payload = response.json()
                msgs = payload.get("mensagens") or []
                primeiro = msgs[0] if msgs else {}
                raise IntegraServicoError(
                    str(primeiro.get("codigo") or response.status_code),
                    str(primeiro.get("texto") or response.text[:300]),
                    raw=payload,
                )
            except (ValueError, KeyError):
                raise IntegraServicoError(
                    str(response.status_code), response.text[:300], raw=response.text
                )

        # Serpro pode responder 200 com body vazio (ex: SITFIS quando protocolo
        # foi solicitado ha pouco tempo, ou serviços async em processamento).
        if not response.content or not response.text.strip():
            return {"status": 200, "dados": None, "_empty": True}
        try:
            return response.json()
        except ValueError:
            return {"status": 200, "dados": response.text, "_raw_text": True}

    @staticmethod
    def _montar_pedido(
        *,
        contribuinte_cnpj: str,
        id_sistema: str,
        id_servico: str,
        versao_sistema: str,
        dados: dict[str, Any] | str,
        contribuinte_tipo: int = 2,
    ) -> dict[str, Any]:
        contratante = (settings.serpro_contratante_cnpj or "").strip()
        autor = (settings.serpro_autor_pedido_cnpj or contratante).strip()
        if not contratante and not settings.use_mock_integra:
            raise IntegraConfigError("SERPRO_CONTRATANTE_CNPJ obrigatorio.")
        dados_str = dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False)
        return {
            "contratante": {"numero": contratante, "tipo": 2},
            "autorPedidoDados": {"numero": autor, "tipo": 2},
            "contribuinte": {"numero": contribuinte_cnpj, "tipo": contribuinte_tipo},
            "pedidoDados": {
                "idSistema": id_sistema,
                "idServico": id_servico,
                "versaoSistema": versao_sistema,
                "dados": dados_str,
            },
        }

    def _validar_config_real(self) -> None:
        faltando: list[str] = []
        if not settings.serpro_consumer_key:
            faltando.append("SERPRO_CONSUMER_KEY")
        if not settings.serpro_consumer_secret:
            faltando.append("SERPRO_CONSUMER_SECRET")
        if not settings.serpro_cert_path:
            faltando.append("SERPRO_CERT_PATH")
        if not settings.serpro_cert_password:
            faltando.append("SERPRO_CERT_PASSWORD")
        if not settings.serpro_contratante_cnpj:
            faltando.append("SERPRO_CONTRATANTE_CNPJ")
        if faltando:
            raise IntegraConfigError(
                "Vars Serpro faltando no .env: " + ", ".join(faltando)
            )

    def _cert_for_requests(self) -> tuple[str, str] | None:
        """Prepara o argumento `cert=` do requests.

        requests aceita (cert_pem_path, key_pem_path) ou caminho de PEM com
        cert+key. Para .pfx precisamos converter via cryptography para um PEM
        temporario (cache em memoria/disco enquanto o processo vive).
        """
        if settings.use_mock_integra:
            return None
        if self._cert_tempfile and self._cert_tempfile.exists():
            return (str(self._cert_tempfile), str(self._cert_tempfile))

        pfx_path = settings.serpro_cert_path
        password = settings.serpro_cert_password
        if not pfx_path:
            raise IntegraConfigError("SERPRO_CERT_PATH nao configurado.")
        try:
            from cryptography.hazmat.primitives.serialization import (
                BestAvailableEncryption,
                Encoding,
                NoEncryption,
                PrivateFormat,
                pkcs12,
            )
        except ImportError as exc:
            raise IntegraContadorError(
                "cryptography nao instalada (necessaria para converter .pfx)."
            ) from exc

        with open(pfx_path, "rb") as f:
            pfx_bytes = f.read()
        private_key, certificate, additional = pkcs12.load_key_and_certificates(
            pfx_bytes, password.encode("utf-8"),
        )
        if private_key is None or certificate is None:
            raise IntegraConfigError("PFX sem chave privada ou certificado.")

        pem_parts: list[bytes] = []
        pem_parts.append(certificate.public_bytes(Encoding.PEM))
        for extra in additional or []:
            pem_parts.append(extra.public_bytes(Encoding.PEM))
        pem_parts.append(
            private_key.private_bytes(
                Encoding.PEM, PrivateFormat.PKCS8, NoEncryption(),
            )
        )

        # Tempfile com permissao restrita (Windows: cleanup ao final do processo).
        fd = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False, mode="wb",
        )
        try:
            fd.write(b"".join(pem_parts))
        finally:
            fd.close()
        self._cert_tempfile = Path(fd.name)
        return (str(self._cert_tempfile), str(self._cert_tempfile))

    # --- Mocks ---

    @staticmethod
    def _mock_caixa_postal_lista(cnpj: str) -> dict[str, Any]:
        agora = datetime.now(timezone.utc).replace(microsecond=0)
        mensagens = [
            {
                "isnMsg": "1001",
                "assunto": "Comunicado Sefaz - SPED",
                "remetente": "Receita Federal do Brasil",
                "dataEnvio": agora.isoformat(),
                "indicadorLeitura": "0",
                "indicadorRelevancia": "ALTA",
            },
            {
                "isnMsg": "1002",
                "assunto": "Notificacao - DCTFWeb pendente",
                "remetente": "Receita Federal do Brasil",
                "dataEnvio": agora.isoformat(),
                "indicadorLeitura": "0",
                "indicadorRelevancia": "MEDIA",
            },
            {
                "isnMsg": "1003",
                "assunto": "Resposta processo 12345/2025",
                "remetente": "Receita Federal do Brasil",
                "dataEnvio": agora.isoformat(),
                "indicadorLeitura": "1",
                "indicadorRelevancia": "BAIXA",
            },
        ]
        return {
            "status": 200,
            "dados": json.dumps({
                "listaMensagens": mensagens,
                "indicadorPagina": "0",
                "proxPonteiroPagina": "00000000000000",
                "qtdMsg": len(mensagens),
            }),
        }

    @staticmethod
    def _mock_caixa_postal_detalhe(isn_msg: str) -> dict[str, Any]:
        return {
            "status": 200,
            "dados": json.dumps({
                "isnMsg": isn_msg,
                "assunto": f"Mensagem {isn_msg} - mock",
                "remetente": "Receita Federal do Brasil",
                "dataEnvio": datetime.now(timezone.utc).isoformat(),
                "conteudoHtml": (
                    "<html><body><p>Conteudo simulado da mensagem "
                    f"<b>{isn_msg}</b>.</p><p>Este e um mock para desenvolvimento.</p>"
                    "</body></html>"
                ),
            }),
        }

    @staticmethod
    def _mock_procuracao(cnpj: str) -> dict[str, Any]:
        return {
            "status": 200,
            "dados": json.dumps({
                "cnpjOutorgante": cnpj,
                "cnpjOutorgado": settings.serpro_autor_pedido_cnpj or "00000000000000",
                "dataInicio": "2025-01-01",
                "dataFim": "2026-12-31",
                "situacao": "ATIVA",
                "servicosAutorizados": [
                    "CAIXA_POSTAL", "SITFIS", "DTE", "PAGTOWEB", "PROCURACOES",
                ],
            }),
        }


def parse_dados(payload: dict[str, Any]) -> dict[str, Any]:
    """O campo `dados` no retorno vem como string JSON; decodifica para dict."""
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("dados")
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
    return {}
