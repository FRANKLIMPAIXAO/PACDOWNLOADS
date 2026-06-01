"""Provider Infosimples — API autorizada de scraping para CNDs + PGFN.

POR QUE INFOSIMPLES (decisão registrada em HANDOFF_2026-05-13_CND-RESEARCH.md):
- Alternativa a Playwright + 2captcha (que é caro de manter e quebra a cada
  mudança de portal).
- Infosimples fala com Receita, PGFN, Caixa, TST e SEFAZs por baixo dos panos
  e devolve JSON pronto.
- Pré-pago por VOLUME (faixas):
    1–500    consultas/mês: R$ 0,20 cada
    501–2k:                 R$ 0,16 cada
    2k–5k:                  R$ 0,14 cada
    5k–10k:                 R$ 0,13 cada
    10k+:                   R$ 0,11 ou menos
  Franquia mínima R$ 100/mês mesmo com pouco uso.
  Cache agressivo é OBRIGATÓRIO pra ficar na faixa barata.

ENDPOINTS COBERTOS HOJE (cada um precisa estar habilitado no painel do cliente):
- `consultas/caixa/regularidade` — CRF FGTS (mensal, validade 30d)
- `consultas/sefaz/{uf}/certidao-debitos` — CND Estadual (por UF)
- `consultas/fgts/guia-rapida` — Emite guia DARF FGTS Digital (mensal, modo Procurador)
- `consultas/fgts/guia` — Lista histórico de guias FGTS Digital (modo Procurador)

MODO PROCURADOR (FGTS Digital):
O cert A1 do ESCRITÓRIO contábil é cadastrado UMA VEZ no painel Infosimples.
Toda chamada usa esse cert pra autenticar via procuração eletrônica gov.br
em nome do cliente (CNPJ representado). Não precisa cadastrar credencial
gov.br por empresa nem mandar pkcs12_cert no payload — só `representado`
+ `periodo` + `token`.

FORA DO ESCOPO (decisão consciente):
- CND Conjunta RFB+PGFN (FEDERAL_OFICIAL) → vem via Integra Contador (Serpro).
  Mais barato (~R$ 0,03 vs R$ 0,20 do Infosimples). Não duplicar aqui.
- Situação Fiscal interna (FEDERAL/SITFIS) → idem, via Integra Contador.
- CNDT Trabalhista → consultas raras (só licitação/banco), não compensa o custo
  recorrente. Mantemos cadastro manual via /cnds.
- PGFN parcelamentos → não tem produto Infosimples. Cadastro manual via
  /parcelamentos-pgfn até descobrirmos outra fonte (parser SITFIS PDF,
  scraper REGULARIZE, ou PARC-PAEX quando RFB liberar API).

ANTI-PADRÕES EVITADOS:
- Retry agressivo (5+): queima saldo se erro for permanente (produto não
  habilitado, CNPJ inválido). Aqui máx 2 retries com backoff.
- Cache flat por CNPJ: CND válida vale 30d, vencida vale 1d. TTL dinâmico.
- Log de token em texto plano. Token só aparece em headers, nunca em logs.

TODOS OS MÉTODOS PÚBLICOS RESPEITAM `use_mock_infosimples=true` (modo mock
retorna payload determinístico pra dev local sem queimar saldo).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

from app.config import get_settings


logger = logging.getLogger(__name__)


# ============================================================================
# Exceções tipadas (caller distingue cada caso, evita swallow generic)
# ============================================================================


class InfosimplesError(Exception):
    """Base — qualquer erro do Infosimples."""

    def __init__(self, mensagem: str, *, codigo: int | None = None, body: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.body = body


class InfosimplesProdutoNaoHabilitado(InfosimplesError):
    """Produto/endpoint não está ativo na conta do cliente."""


class InfosimplesSaldoInsuficiente(InfosimplesError):
    """Conta sem saldo pré-pago. Caller deve PARAR (não retry) e avisar usuário."""


class InfosimplesRateLimit(InfosimplesError):
    """Excedeu rate limit. Caller pode retry com backoff."""


class InfosimplesCnpjInvalido(InfosimplesError):
    """CNPJ malformado ou não existe na Receita. Não retry."""


class InfosimplesTimeout(InfosimplesError):
    """Portal de origem demorou demais. Caller pode retry uma vez."""


# ============================================================================
# Dataclasses de resposta — shape estável independente da resposta bruta
# ============================================================================


@dataclass(slots=True)
class CndInfosimples:
    """Resultado de consulta de CND via Infosimples."""

    cnpj: str
    tipo: str  # "FGTS" | "ESTADUAL" — outras CNDs vêm de outros providers / cadastro manual
    numero: str | None
    data_emissao: date | None
    data_validade: date | None
    situacao: str  # "regular" | "irregular" | "indisponivel"
    pdf_url: str | None  # URL pro PDF da certidão hospedado pelo Infosimples
    pdf_bytes: bytes | None  # Se já baixado
    raw: dict
    # Telemetria do Infosimples — quanto custou essa consulta (centavos) e
    # se foi cobrada (header.billable). Útil pra somar gasto mensal real.
    custo_centavos: int = 0
    billable: bool = True
    mensagem: str | None = None  # Mensagem livre do portal (útil quando irregular)


@dataclass(slots=True)
class GuiaFgtsRapidaInfosimples:
    """Guia DARF FGTS Digital emitida via endpoint guia-rapida.

    Modo Procurador: cert do escritório no painel Infosimples + CNPJ
    representado (cliente). Sem login gov.br por empresa.
    """

    cnpj: str  # CNPJ representado (cliente)
    competencia: str | None  # YYYYMM ou "12/2024" — depende do retorno
    data_vencimento: date | None
    valor_total: float | None
    valor_mensal: float | None
    valor_rescisorio: float | None
    valor_compensatorio: float | None
    valor_encargos: float | None
    quantidade_trabalhadores: int | None
    empregador: dict | None  # razao_social, cnpj, etc.
    procurador: dict | None  # nome, cpf
    consignado: dict | None
    guia_pdf_url: str | None
    site_receipt: str | None
    raw: dict
    custo_centavos: int = 0
    billable: bool = True


@dataclass(slots=True)
class GuiaFgtsListaInfosimples:
    """Resposta do endpoint guia (lista de guias FGTS de um período)."""

    cnpj: str
    empregador: dict | None
    procurador: dict | None
    total_guias: int
    total_paginas: int
    pagina: int
    guias: list[dict]  # cada item: numero, tipo, situacao, valor_total, data_limite_pagamento, ...
    raw: dict
    custo_centavos: int = 0
    billable: bool = True


@dataclass(slots=True)
class ParcelamentoPgfnInfosimples:
    """Parcelamento PGFN ativo (Dívida Ativa)."""

    numero: str  # número da inscrição/parcelamento
    modalidade: str  # ex: "Parcelamento Ordinário", "RegPag", "Transação"
    data_pedido: date | None
    situacao: str
    valor_total: float | None  # consolidado
    valor_total_pago: float | None
    quantidade_parcelas: int | None
    parcelas_pagas: int | None
    raw: dict


# ============================================================================
# Provider
# ============================================================================


class InfosimplesProvider:
    """HTTP simples + retry conservador + auth via token no body.

    Stateless: pode ser instanciado por request sem custo. Usa `requests.Session`
    pra reaproveitar conexão TCP/SSL nas chamadas em batch (cron mensal).
    """

    def __init__(self) -> None:
        s = get_settings()
        self.token = s.infosimples_token
        self.base_url = s.infosimples_base_url.rstrip("/")
        self.timeout = s.infosimples_timeout
        self.use_mock = s.use_mock_infosimples or not self.token
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Métodos públicos — CND
    # NOTA: CND Conjunta RFB+PGFN (FEDERAL_OFICIAL) NÃO está aqui —
    # vem via Integra Contador (Serpro), mais barato. Veja
    # `IntegraContadorService.gerar_situacao_fiscal`.
    # ------------------------------------------------------------------

    def crf_fgts(
        self, cnpj: str,
        *,
        preferencia_emissao: str = "2via",
        aceita_resultado_parcial: int = 0,
    ) -> CndInfosimples:
        """Certificado de Regularidade FGTS (Caixa).

        Endpoint REAL: `/consultas/caixa/regularidade` (NÃO `/caixa/fgts`).
        Confirmado pela doc oficial Infosimples.

        Args:
            cnpj: CNPJ com ou sem máscara
            preferencia_emissao: "2via" (padrão — busca CRF já emitida)
                ou "nova" (força emissão nova). 2via é mais barato e rápido
                quando a empresa já tem CRF válida no Caixa.
            aceita_resultado_parcial: 0 = só devolve com CRF completa,
                1 = devolve mesmo se faltarem campos. Padrão 0 (mais rigoroso).
        """
        if self.use_mock:
            return self._mock_cnd(cnpj, "FGTS")
        payload = {
            "cnpj": self._so_digitos(cnpj),
            "preferencia_emissao": preferencia_emissao,
            "aceita_resultado_parcial": aceita_resultado_parcial,
        }
        data = self._post("/consultas/caixa/regularidade", payload)
        return self._parse_cnd(cnpj, "FGTS", data)

    def cnd_sefaz_estadual(self, cnpj: str, uf: str) -> CndInfosimples:
        """CND Estadual SEFAZ — endpoint `/consultas/sefaz/{uf}/certidao-debitos`.

        UF é code de 2 letras (GO, SP, MG, RJ, etc.). Cada SEFAZ tem seu
        portal e captcha próprios — Infosimples normaliza tudo em um endpoint
        por UF. Hoje a maioria das UFs tem cobertura.

        Args:
            cnpj: CNPJ com ou sem máscara
            uf: sigla UF (case-insensitive)
        """
        uf_norm = (uf or "").strip().lower()
        if len(uf_norm) != 2:
            raise InfosimplesError(f"UF inválida: {uf!r} (esperado 2 letras)")
        if self.use_mock:
            return self._mock_cnd(cnpj, "ESTADUAL")
        payload = {"cnpj": self._so_digitos(cnpj)}
        data = self._post(f"/consultas/sefaz/{uf_norm}/certidao-debitos", payload)
        cnd = self._parse_cnd(cnpj, "ESTADUAL", data)
        # Anota UF no raw pra histórico
        cnd.raw = {**data, "_uf_consultada": uf_norm.upper()}
        return cnd

    # ------------------------------------------------------------------
    # FGTS Digital — modo Procurador (cert do escritório no painel)
    # ------------------------------------------------------------------

    def fgts_emitir_guia_rapida(
        self, cnpj_representado: str, periodo: str,
    ) -> GuiaFgtsRapidaInfosimples:
        """Emite Guia Rápida de Arrecadação do FGTS Digital.

        Endpoint: `/consultas/fgts/guia-rapida`.

        Args:
            cnpj_representado: CNPJ da empresa cliente (com ou sem máscara)
            periodo: competência YYYYMM (ex: '202412' pra dezembro/2024)
        """
        cnpj_norm = self._so_digitos(cnpj_representado)
        if not periodo or len(periodo) != 6 or not periodo.isdigit():
            raise InfosimplesError(
                f"Período inválido: {periodo!r} (esperado YYYYMM)",
            )
        if self.use_mock:
            return self._mock_fgts_guia_rapida(cnpj_norm, periodo)
        payload = {
            "representado": cnpj_norm,
            "periodo": periodo,
        }
        data = self._post("/consultas/fgts/guia-rapida", payload)
        return self._parse_fgts_guia_rapida(cnpj_norm, data)

    def fgts_consultar_guias(
        self, cnpj_representado: str,
        *,
        periodo: str | None = None,
        pagina: int = 1,
    ) -> GuiaFgtsListaInfosimples:
        """Consulta lista de guias FGTS Digital de um período (modo Procurador).

        Endpoint: `/consultas/fgts/guia`. Devolve até 10 guias por página.

        Args:
            cnpj_representado: CNPJ da empresa cliente
            periodo: YYYYMM (opcional — sem filtro retorna últimas guias)
            pagina: 1-indexed
        """
        cnpj_norm = self._so_digitos(cnpj_representado)
        if periodo is not None and (
            len(periodo) != 6 or not periodo.isdigit()
        ):
            raise InfosimplesError(
                f"Período inválido: {periodo!r} (esperado YYYYMM)",
            )
        if self.use_mock:
            return self._mock_fgts_consultar_guias(cnpj_norm, periodo, pagina)
        payload: dict[str, Any] = {
            "representado": cnpj_norm,
            "pagina": pagina,
        }
        if periodo:
            payload["periodo"] = periodo
        data = self._post("/consultas/fgts/guia", payload)
        return self._parse_fgts_consultar_guias(cnpj_norm, pagina, data)

    # ------------------------------------------------------------------
    # HTTP — POST com retry conservador (máx 2 tentativas)
    # ------------------------------------------------------------------

    def _post(self, path: str, body: dict) -> dict:
        """POST autenticado. Adiciona `token` ao body (padrão Infosimples).

        CRITICAL: Infosimples API v2 espera body FORM-ENCODED (application/x-www-form-urlencoded),
        NÃO application/json. Bug clássico — usei `json=` no design inicial e
        os requests retornavam erro 600 (parâmetro faltando) porque o token
        ia no body JSON mas o servidor não parseava.

        Também adicionamos `timeout` ao body (segundos que o Infosimples vai
        esperar o portal de origem) — separado do `requests.timeout` que é o
        tempo do nosso socket.

        Retries:
        - Erro 429 (rate limit) → espera 30s e tenta de novo (1 vez só).
        - Timeout → tenta de novo (1 vez só).
        - 4xx que não seja 429 → NÃO retry (CNPJ inválido / produto desabilitado).
        - 5xx → retry com backoff 1x.
        """
        url = f"{self.base_url}{path}"
        # Token + timeout vão no body — padrão da Infosimples API v2.
        # `timeout` no payload = segundos que Infosimples espera o portal origem.
        # `self.timeout` no requests = segundos que nosso socket aceita.
        # Damos 30s de folga ao socket vs ao portal.
        timeout_portal = max(60, self.timeout - 30)
        payload = {**body, "token": self.token, "timeout": timeout_portal}

        max_tentativas = 2
        ultima_excecao: Exception | None = None
        for tentativa in range(max_tentativas):
            try:
                # Log SEM o token (evita vazamento)
                logger.info(
                    "Infosimples POST %s (tentativa %d/%d)",
                    path, tentativa + 1, max_tentativas,
                )
                resp = self.session.post(url, data=payload, timeout=self.timeout)
                return self._tratar_resposta(resp, path)
            except (InfosimplesRateLimit, InfosimplesTimeout) as exc:
                ultima_excecao = exc
                if tentativa + 1 < max_tentativas:
                    espera = 30 if isinstance(exc, InfosimplesRateLimit) else 5
                    logger.warning(
                        "Infosimples %s — %s. Esperando %ds e retry.",
                        path, exc, espera,
                    )
                    time.sleep(espera)
                    continue
                raise
            except (
                InfosimplesProdutoNaoHabilitado,
                InfosimplesSaldoInsuficiente,
                InfosimplesCnpjInvalido,
            ):
                # NÃO retry — erros permanentes ou que travam tudo
                raise
            except requests.RequestException as exc:
                ultima_excecao = exc
                if tentativa + 1 < max_tentativas:
                    logger.warning("Erro rede Infosimples %s: %s. Retry.", path, exc)
                    time.sleep(3)
                    continue
                raise InfosimplesError(f"Erro de rede: {exc}") from exc

        # Não deveria chegar aqui, mas pra type-checker
        raise InfosimplesError(
            f"Falhou após {max_tentativas} tentativas: {ultima_excecao}",
        )

    def _tratar_resposta(self, resp: requests.Response, path: str) -> dict:
        """Mapeia status HTTP + códigos Infosimples → exceções tipadas.

        Infosimples API v2 usa um campo `code` no JSON:
        - 200 = sucesso
        - 600-699 = erro do usuário (CNPJ inválido, parâmetro faltando)
        - 700-799 = erro de saldo / autenticação
        - 800-899 = erro do portal de origem (RFB fora do ar)
        """
        # Erros HTTP brutos (rede, gateway)
        if resp.status_code == 429:
            raise InfosimplesRateLimit("Rate limit (HTTP 429)", codigo=429)
        if resp.status_code >= 500:
            raise InfosimplesError(
                f"Erro servidor Infosimples (HTTP {resp.status_code})",
                codigo=resp.status_code,
                body=resp.text[:500],
            )

        # Tenta parsear JSON
        try:
            data = resp.json()
        except ValueError as exc:
            raise InfosimplesError(
                f"Resposta não-JSON do Infosimples (HTTP {resp.status_code})",
                codigo=resp.status_code,
                body=resp.text[:500],
            ) from exc

        # API v2 retorna {code, code_message, header, data: [...]}
        codigo = data.get("code")
        msg = data.get("code_message") or data.get("header", {}).get("message") or "?"

        if codigo == 200:
            return data
        if codigo in (612, 613, 614):  # CNPJ inválido / não encontrado
            raise InfosimplesCnpjInvalido(f"CNPJ inválido: {msg}", codigo=codigo, body=data)
        if codigo in (701, 702):  # Sem saldo / autenticação inválida
            raise InfosimplesSaldoInsuficiente(
                f"Sem saldo ou token inválido: {msg}", codigo=codigo, body=data,
            )
        if codigo == 703:  # Produto não habilitado
            raise InfosimplesProdutoNaoHabilitado(
                f"Produto não habilitado na conta: {msg}", codigo=codigo, body=data,
            )
        if codigo in (820, 821, 822):  # Portal de origem fora do ar / lento
            raise InfosimplesTimeout(
                f"Portal de origem indisponível: {msg}", codigo=codigo, body=data,
            )
        # Qualquer outro código não-200 vira erro genérico
        raise InfosimplesError(
            f"Infosimples retornou code={codigo}: {msg}", codigo=codigo, body=data,
        )

    # ------------------------------------------------------------------
    # Parsers — convertem JSON cru em dataclass tipado
    # ------------------------------------------------------------------

    def _parse_cnd(self, cnpj: str, tipo: str, data: dict) -> CndInfosimples:
        """Extrai dados da CND do payload Infosimples.

        Shape real (confirmado pela doc oficial de SEFAZ-GO):
            {
              "code": 200,
              "code_message": "...",
              "header": {
                "billable": true,
                "price": 0.45,
                "api_version": "v2",
                ...
              },
              "data_count": 1,
              "data": [{
                "conseguiu_emitir_certidao_negativa": true,
                "certidao_codigo": "12345...",
                "emissao_data": "DD/MM/YYYY HH:MM:SS",
                "validade_data": "DD/MM/YYYY",
                "mensagem": "Certidão emitida com sucesso",
                ...
              }]
            }

        Endpoints diferentes podem usar nomes parecidos (numero_certidao,
        certidao_codigo, codigo_certidao). Parser tenta vários fallbacks.
        """
        items = data.get("data") or []
        item = items[0] if items else {}
        header = data.get("header") or {}

        # Telemetria de custo (sempre fora do mock)
        billable = bool(header.get("billable", True))
        price_reais = header.get("price") or 0
        try:
            custo_centavos = int(round(float(price_reais) * 100))
        except (TypeError, ValueError):
            custo_centavos = 0

        # Detecta situação por múltiplos caminhos (cada endpoint Infosimples usa
        # um nome de campo diferente):
        # - SEFAZ Estadual: `conseguiu_emitir_certidao_negativa` (bool)
        # - CRF FGTS: `situacao` em UPPERCASE ("REGULAR"/"IRREGULAR")
        # - CNDT Trabalhista: `situacao` em PT-BR ("Negativa"/"Positiva")
        # - CND Conjunta RFB+PGFN: `situacao` ou `tipo_certidao` ("Negativa"/"Positiva com efeitos de Negativa"/"Positiva")
        conseguiu = item.get("conseguiu_emitir_certidao_negativa")
        situacao_txt = (
            item.get("situacao")
            or item.get("status")
            or item.get("tipo_certidao")
            or ""
        ).lower()
        mensagem = (
            item.get("mensagem")
            or item.get("message")
            or item.get("descricao")
            or None
        )

        if conseguiu is True:
            situacao = "regular"
        elif conseguiu is False:
            situacao = "irregular"
        elif (
            "regular" in situacao_txt
            or "negativa" in situacao_txt
            or "positiva com efeitos" in situacao_txt
        ):
            situacao = "regular"
        elif "irregular" in situacao_txt or "positiva" in situacao_txt:
            situacao = "irregular"
        else:
            situacao = "indisponivel"

        # Fields de data variam muito por endpoint:
        # - SEFAZ Estadual: emissao_data / validade_data
        # - CRF FGTS: validade_inicio_data (= emissão) / validade_fim_data (= validade)
        # - CND Conjunta: data_emissao / data_validade
        emissao_raw = (
            item.get("emissao_data")
            or item.get("validade_inicio_data")  # FGTS: início = emissão
            or item.get("data_emissao")
        )
        validade_raw = (
            item.get("validade_fim_data")  # FGTS: fim = validade
            or item.get("validade_data")
            or item.get("data_validade")
        )

        # Número da certidão também varia:
        # - SEFAZ Estadual: certidao_codigo
        # - CRF FGTS: crf
        # - CNDT/Conjunta: numero_certidao
        numero = (
            item.get("crf")  # FGTS
            or item.get("certidao_codigo")
            or item.get("numero_certidao")
            or item.get("codigo_certidao")
            or item.get("codigo_controle")
            or item.get("numero")
        )

        return CndInfosimples(
            cnpj=cnpj,
            tipo=tipo,
            numero=str(numero) if numero else None,
            data_emissao=self._parse_data_br(emissao_raw),
            data_validade=self._parse_data_br(validade_raw),
            situacao=situacao,
            pdf_url=(
                item.get("url_certidao")
                or item.get("certidao_url")
                or item.get("pdf_url")
                or item.get("link_certidao")
            ),
            pdf_bytes=None,
            raw=data,
            custo_centavos=custo_centavos,
            billable=billable,
            mensagem=mensagem,
        )

    def _parse_parcelamentos(self, data: dict) -> list[ParcelamentoPgfnInfosimples]:
        """Extrai lista de parcelamentos do payload.

        Estrutura esperada (varia):
            {
              "code": 200,
              "data": [{
                "numero": "...",
                "modalidade": "Parcelamento Ordinário",
                "data_pedido": "DD/MM/YYYY",
                "situacao": "Ativo",
                "valor_total_consolidado": "R$ 1.234,56",
                "valor_total_pago": "R$ 100,00",
                "quantidade_parcelas": 60,
                "parcelas_pagas": 5,
                ...
              }]
            }
        """
        items = data.get("data") or []
        resultado: list[ParcelamentoPgfnInfosimples] = []
        for item in items:
            resultado.append(
                ParcelamentoPgfnInfosimples(
                    numero=str(item.get("numero") or item.get("inscricao") or ""),
                    modalidade=item.get("modalidade") or "PGFN",
                    data_pedido=self._parse_data_br(item.get("data_pedido")),
                    situacao=item.get("situacao") or "ativo",
                    valor_total=self._parse_brl(item.get("valor_total_consolidado") or item.get("valor_total")),
                    valor_total_pago=self._parse_brl(item.get("valor_total_pago")),
                    quantidade_parcelas=self._parse_int(item.get("quantidade_parcelas")),
                    parcelas_pagas=self._parse_int(item.get("parcelas_pagas")),
                    raw=item,
                )
            )
        return resultado

    # ------------------------------------------------------------------
    # Parsers FGTS Digital
    # ------------------------------------------------------------------

    def _parse_fgts_guia_rapida(
        self, cnpj: str, data: dict,
    ) -> GuiaFgtsRapidaInfosimples:
        """Extrai dados da resposta de /consultas/fgts/guia-rapida.

        Estrutura típica (data[0]):
            {
              "empregador": {...},
              "competencia": "12/2024",
              "data_vencimento": "DD/MM/YYYY",
              "valor_mensal": "1234.56",
              "valor_rescisorio": "...",
              "valor_compensatorio": "...",
              "valor_encargos": "...",
              "valor_total": "1500.00",
              "quantidade_trabalhadores": 10,
              "guia_pdf_url": "https://...",
              "procurador": {...},
              "consignado": {...},
              "site_receipt": "..."
            }
        """
        items = data.get("data") or []
        item = items[0] if items else {}
        header = data.get("header") or {}

        billable = bool(header.get("billable", True))
        price_reais = header.get("price") or 0
        try:
            custo_centavos = int(round(float(price_reais) * 100))
        except (TypeError, ValueError):
            custo_centavos = 0

        return GuiaFgtsRapidaInfosimples(
            cnpj=cnpj,
            competencia=item.get("competencia"),
            data_vencimento=self._parse_data_br(item.get("data_vencimento")),
            valor_total=self._parse_brl(item.get("valor_total")),
            valor_mensal=self._parse_brl(item.get("valor_mensal")),
            valor_rescisorio=self._parse_brl(item.get("valor_rescisorio")),
            valor_compensatorio=self._parse_brl(item.get("valor_compensatorio")),
            valor_encargos=self._parse_brl(item.get("valor_encargos")),
            quantidade_trabalhadores=self._parse_int(
                item.get("quantidade_trabalhadores"),
            ),
            empregador=item.get("empregador"),
            procurador=item.get("procurador"),
            consignado=item.get("consignado"),
            guia_pdf_url=item.get("guia_pdf_url") or item.get("pdf_url"),
            site_receipt=item.get("site_receipt"),
            raw=data,
            custo_centavos=custo_centavos,
            billable=billable,
        )

    def _parse_fgts_consultar_guias(
        self, cnpj: str, pagina: int, data: dict,
    ) -> GuiaFgtsListaInfosimples:
        """Extrai dados da resposta de /consultas/fgts/guia (lista paginada)."""
        items = data.get("data") or []
        item = items[0] if items else {}
        header = data.get("header") or {}

        billable = bool(header.get("billable", True))
        price_reais = header.get("price") or 0
        try:
            custo_centavos = int(round(float(price_reais) * 100))
        except (TypeError, ValueError):
            custo_centavos = 0

        return GuiaFgtsListaInfosimples(
            cnpj=cnpj,
            empregador=item.get("empregador"),
            procurador=item.get("procurador"),
            total_guias=int(item.get("total_guias") or 0),
            total_paginas=int(item.get("total_paginas") or 0),
            pagina=pagina,
            guias=item.get("guias") or [],
            raw=data,
            custo_centavos=custo_centavos,
            billable=billable,
        )

    # ------------------------------------------------------------------
    # Helpers de parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _so_digitos(cnpj: str) -> str:
        return "".join(c for c in (cnpj or "") if c.isdigit())

    @staticmethod
    def _parse_data_br(s: Any) -> date | None:
        if not s:
            return None
        s = str(s).strip()
        # Tenta full datetime primeiro, depois date
        for fmt in (
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d-%m-%Y",
        ):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_brl(s: Any) -> float | None:
        if s is None or s == "":
            return None
        if isinstance(s, (int, float)):
            return float(s)
        # "R$ 1.234,56" → 1234.56
        s = str(s).replace("R$", "").strip().replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def _parse_int(s: Any) -> int | None:
        if s is None or s == "":
            return None
        try:
            return int(str(s).strip())
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # MOCKS — payload determinístico pra dev local sem queimar saldo
    # ------------------------------------------------------------------

    def _mock_cnd(self, cnpj: str, tipo: str) -> CndInfosimples:
        """Mock — devolve CND válida fictícia. Determinístico por (cnpj, tipo)."""
        cnpj_d = self._so_digitos(cnpj)
        # Validade calculada por dia da semana do CNPJ pra ter variação:
        # válida na maioria, mas algumas vencem em <30d pra testar UI
        seed = int(hashlib.md5(f"{cnpj_d}{tipo}".encode()).hexdigest()[:8], 16)
        if seed % 10 == 0:
            # 10% das empresas mockadas: VENCIDA
            validade = date.today() - timedelta(days=15)
            situacao = "irregular"
        elif seed % 10 < 3:
            # 20%: A_VENCER
            validade = date.today() + timedelta(days=15)
            situacao = "regular"
        else:
            # 70%: VALIDA
            validade = date.today() + timedelta(days=120)
            situacao = "regular"
        numero = f"MOCK-{tipo}-{cnpj_d[-4:]}-{seed % 100000:05d}"
        return CndInfosimples(
            cnpj=cnpj,
            tipo=tipo,
            numero=numero,
            data_emissao=date.today() if situacao == "regular" else None,
            data_validade=validade,
            situacao=situacao,
            pdf_url=None,
            pdf_bytes=None,
            raw={"mock": True, "tipo": tipo, "cnpj": cnpj_d},
        )

    def _mock_parcelamentos(self, cnpj: str) -> list[ParcelamentoPgfnInfosimples]:
        """Mock — 1 parcelamento ativo pra 30% das empresas, vazio pro resto."""
        cnpj_d = self._so_digitos(cnpj)
        seed = int(hashlib.md5(f"{cnpj_d}pgfn".encode()).hexdigest()[:8], 16)
        if seed % 10 >= 3:
            return []  # 70% sem parcelamento
        return [
            ParcelamentoPgfnInfosimples(
                numero=f"MOCK-PGFN-{cnpj_d[-6:]}",
                modalidade="Parcelamento Ordinário",
                data_pedido=date.today() - timedelta(days=180),
                situacao="Ativo",
                valor_total=float(50_000 + (seed % 100_000)),
                valor_total_pago=float(5_000 + (seed % 10_000)),
                quantidade_parcelas=60,
                parcelas_pagas=6,
                raw={"mock": True, "cnpj": cnpj_d},
            )
        ]

    def _mock_fgts_guia_rapida(
        self, cnpj: str, periodo: str,
    ) -> GuiaFgtsRapidaInfosimples:
        """Mock — guia FGTS Digital fictícia. Determinístico por (cnpj, periodo)."""
        cnpj_d = self._so_digitos(cnpj)
        seed = int(hashlib.md5(f"{cnpj_d}{periodo}fgts".encode()).hexdigest()[:8], 16)
        # 10% das empresas mockadas: sem trabalhadores no mês → guia vazia
        if seed % 10 == 0:
            return GuiaFgtsRapidaInfosimples(
                cnpj=cnpj_d,
                competencia=f"{periodo[4:]}/{periodo[:4]}",
                data_vencimento=None,
                valor_total=0.0,
                valor_mensal=0.0,
                valor_rescisorio=0.0,
                valor_compensatorio=0.0,
                valor_encargos=0.0,
                quantidade_trabalhadores=0,
                empregador={"cnpj": cnpj_d, "razao_social": "MOCK EMPRESA LTDA"},
                procurador={"nome": "MOCK ESCRITÓRIO CONTÁBIL", "cpf": "***.***.***-**"},
                consignado=None,
                guia_pdf_url=None,
                site_receipt=None,
                raw={"mock": True, "cnpj": cnpj_d, "periodo": periodo, "vazia": True},
            )
        # 90%: guia com valores fictícios coerentes
        qtd_trab = 3 + (seed % 30)
        valor_mensal = qtd_trab * (250 + (seed % 500))  # ~R$ 750/trab médio
        valor_total = valor_mensal + (seed % 100) * 0.5  # encargos
        # Vencimento: dia 20 do mês seguinte ao período
        ano = int(periodo[:4])
        mes = int(periodo[4:])
        if mes == 12:
            ano_venc, mes_venc = ano + 1, 1
        else:
            ano_venc, mes_venc = ano, mes + 1
        try:
            vencimento = date(ano_venc, mes_venc, 20)
        except ValueError:
            vencimento = date.today() + timedelta(days=15)
        return GuiaFgtsRapidaInfosimples(
            cnpj=cnpj_d,
            competencia=f"{periodo[4:]}/{periodo[:4]}",
            data_vencimento=vencimento,
            valor_total=round(valor_total, 2),
            valor_mensal=round(valor_mensal, 2),
            valor_rescisorio=0.0,
            valor_compensatorio=0.0,
            valor_encargos=round(valor_total - valor_mensal, 2),
            quantidade_trabalhadores=qtd_trab,
            empregador={"cnpj": cnpj_d, "razao_social": "MOCK EMPRESA LTDA"},
            procurador={"nome": "MOCK ESCRITÓRIO CONTÁBIL", "cpf": "***.***.***-**"},
            consignado=None,
            guia_pdf_url=f"https://mock.infosimples.com/fgts/{cnpj_d}/{periodo}.pdf",
            site_receipt="<mock-html-receipt/>",
            raw={"mock": True, "cnpj": cnpj_d, "periodo": periodo},
        )

    def _mock_fgts_consultar_guias(
        self, cnpj: str, periodo: str | None, pagina: int,
    ) -> GuiaFgtsListaInfosimples:
        """Mock — lista 3 guias fictícias na 1ª página, vazio nas seguintes."""
        cnpj_d = self._so_digitos(cnpj)
        seed = int(hashlib.md5(f"{cnpj_d}lista".encode()).hexdigest()[:8], 16)
        if pagina > 1:
            return GuiaFgtsListaInfosimples(
                cnpj=cnpj_d,
                empregador={"cnpj": cnpj_d, "razao_social": "MOCK EMPRESA LTDA"},
                procurador={"nome": "MOCK ESCRITÓRIO"},
                total_guias=3, total_paginas=1, pagina=pagina, guias=[],
                raw={"mock": True},
            )
        guias_mock = [
            {
                "numero": f"GFD-{cnpj_d[-4:]}-{i:04d}",
                "tipo": "Mensal",
                "situacao": "Em aberto" if i == 0 else "Paga",
                "valor_total": str(round(1500 + (seed + i) % 3000, 2)),
                "data_limite_pagamento": (date.today() + timedelta(days=10 - i*30)).strftime("%d/%m/%Y"),
                "competencia": (date.today().replace(day=1) - timedelta(days=i*30)).strftime("%m/%Y"),
            }
            for i in range(3)
        ]
        return GuiaFgtsListaInfosimples(
            cnpj=cnpj_d,
            empregador={"cnpj": cnpj_d, "razao_social": "MOCK EMPRESA LTDA"},
            procurador={"nome": "MOCK ESCRITÓRIO CONTÁBIL"},
            total_guias=3,
            total_paginas=1,
            pagina=pagina,
            guias=guias_mock,
            raw={"mock": True, "cnpj": cnpj_d, "periodo": periodo},
        )
