from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

import requests

from app.config import get_settings
from app.providers._common import parse_data_emissao


settings = get_settings()


# Endpoints Focus NFe (https://focusnfe.com.br/doc/)
EMPRESAS_ENDPOINT = "/v2/empresas"
EMPRESA_ENDPOINT = "/v2/empresas/{cnpj}"
NFE_EMITIDA_ENDPOINT = "/v2/nfe/{ref}"
CTE_EMITIDO_ENDPOINT = "/v2/cte/{ref}"
NFSE_EMITIDA_ENDPOINT = "/v2/nfse/{ref}"
NFES_RECEBIDAS_ENDPOINT = "/v2/nfes_recebidas"
NFE_RECEBIDA_ENDPOINT = "/v2/nfes_recebidas/{chave}"
NFE_RECEBIDA_XML_ENDPOINT = "/v2/nfes_recebidas/{chave}.xml"
NFE_RECEBIDA_MANIFESTO_ENDPOINT = "/v2/nfes_recebidas/{chave}/manifesto"
CTES_RECEBIDOS_ENDPOINT = "/v2/ctes_recebidos"

# Limite de seguranca para paginacao por NSU.
MAX_PAGES = 100


# --- Exceptions ---


class FocusNFeError(Exception):
    """Erro generico da integracao com Focus NFe."""


class FocusEmpresaNaoCadastradaError(FocusNFeError):
    """Empresa nao encontrada na conta Focus NFe (404 em GET /v2/empresas/{cnpj})."""


class FocusTokenAusenteError(FocusNFeError):
    """Empresa local sem `focus_token` configurado."""


class FocusManifestacaoError(FocusNFeError):
    """Falha ao registrar manifestacao do destinatario."""


# --- Tipos ---


ManifestacaoTipo = Literal["ciencia", "confirmacao", "desconhecimento", "nao_realizada"]


@dataclass(slots=True)
class DocumentoRecebidoFocus:
    """Representacao normalizada de um item de NFe-recebida vinda da Focus."""

    chave: str
    nsu: str
    cnpj_emitente: str
    nome_emitente: str | None = None
    valor_total: Decimal | None = None
    data_emissao: datetime | None = None
    tipo: str = "nfe"
    raw: dict[str, Any] = field(default_factory=dict)


# --- Provider ---


class FocusNFeProvider:
    """Cliente da API Focus NFe.

    Stateless: o token (HTTP Basic, username=token / password vazio) eh passado em
    cada chamada como primeiro parametro. Cada empresa cadastrada na Focus possui
    seu proprio token; este provider nao guarda token no construtor para evitar
    acoplamento ao model `Empresa` e manter thread safety.
    """

    def __init__(self) -> None:
        self.base_url = settings.focus_base_url.rstrip("/")
        self.session = requests.Session()

    # --- Empresas ---

    def cadastrar_empresa(
        self,
        token_master: str,
        payload: dict[str, Any],
        certificado_bytes: bytes,
        certificado_filename: str,
        certificado_password: str,
    ) -> dict[str, Any]:
        """Cadastra uma empresa na Focus NFe (POST /v2/empresas, multipart).

        `token_master` deve ser o token-mestre da conta Focus (configurado em
        `FOCUS_MASTER_TOKEN`). Apos o cadastro, a Focus retorna o token especifico
        da empresa no campo `token_producao` ou `token_homologacao`.
        """
        if settings.use_mock_focus_nfe:
            return self._mock_empresa(payload.get("cnpj") or payload.get("cpf_cnpj") or "")
        files = {"arquivo_certificado": (certificado_filename, certificado_bytes, "application/x-pkcs12")}
        data = {**payload, "senha_certificado": certificado_password}
        return self._request(token_master, "POST", EMPRESAS_ENDPOINT, data=data, files=files)

    def consultar_empresa(self, token: str, cnpj: str) -> dict[str, Any]:
        """Detalhes da empresa.

        A Focus NFe NAO expoe `GET /v2/empresas/{cnpj}` — esse endpoint retorna
        HTTP 422. O caminho real eh listar todas as empresas com o token-mestre
        e filtrar localmente pelo CNPJ.

        Requer token mestre (token de empresa retorna 401 em /v2/empresas).
        """
        if settings.use_mock_focus_nfe:
            return self._mock_empresa(cnpj)
        cnpj_norm = "".join(c for c in cnpj if c.isdigit())
        try:
            empresas = self.listar_empresas(token)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                # Provavelmente token de empresa em vez de master.
                raise FocusNFeError(
                    "Listagem de empresas Focus exige token-mestre."
                ) from exc
            raise
        for emp in empresas:
            emp_cnpj = "".join(c for c in (emp.get("cnpj") or "") if c.isdigit())
            if emp_cnpj == cnpj_norm:
                return emp
        raise FocusEmpresaNaoCadastradaError(
            f"Empresa {cnpj} nao cadastrada na conta Focus NFe."
        )

    def listar_empresas(self, token: str) -> list[dict[str, Any]]:
        if settings.use_mock_focus_nfe:
            return [self._mock_empresa("12345678000195")]
        payload = self._request(token, "GET", EMPRESAS_ENDPOINT)
        if isinstance(payload, list):
            return payload
        return payload.get("data", []) if isinstance(payload, dict) else []

    def atualizar_empresa(
        self,
        token: str,
        cnpj: str,
        payload: dict[str, Any] | None = None,
        certificado_bytes: bytes | None = None,
        certificado_filename: str | None = None,
        certificado_password: str | None = None,
    ) -> dict[str, Any]:
        """PUT /v2/empresas/{cnpj}. Aceita atualizar dados e/ou trocar certificado."""
        if settings.use_mock_focus_nfe:
            return self._mock_empresa(cnpj)
        data = dict(payload or {})
        files = None
        if certificado_bytes is not None:
            if not certificado_filename or certificado_password is None:
                raise ValueError("Para atualizar certificado, envie filename e senha.")
            files = {
                "arquivo_certificado": (
                    certificado_filename,
                    certificado_bytes,
                    "application/x-pkcs12",
                )
            }
            data["senha_certificado"] = certificado_password
        return self._request(token, "PUT", EMPRESA_ENDPOINT.format(cnpj=cnpj), data=data, files=files)

    def excluir_empresa(self, token: str, cnpj: str) -> None:
        if settings.use_mock_focus_nfe:
            return None
        self._request(token, "DELETE", EMPRESA_ENDPOINT.format(cnpj=cnpj), expect_json=False)
        return None

    # --- Notas EMITIDAS via Focus (consulta por `ref` interno) ---

    def consultar_nfe_emitida(self, token: str, ref: str) -> dict[str, Any]:
        if settings.use_mock_focus_nfe:
            return self._mock_emitida_status("nfe", ref)
        return self._request(token, "GET", NFE_EMITIDA_ENDPOINT.format(ref=ref))

    def baixar_xml_nfe_emitida(self, token: str, ref: str) -> str:
        """Baixa o XML autorizado de uma NFe emitida via Focus.

        Fluxo: consulta retorna `caminho_xml_nota_fiscal` (URL absoluta ou relativa);
        este metodo faz GET nessa URL.
        """
        if settings.use_mock_focus_nfe:
            return self._mock_xml_nfe(ref)
        info = self.consultar_nfe_emitida(token, ref)
        caminho = info.get("caminho_xml_nota_fiscal") or info.get("caminho_xml")
        if not caminho:
            raise FocusNFeError(f"Resposta sem caminho_xml_nota_fiscal para ref={ref}")
        url = caminho if caminho.startswith("http") else f"{self.base_url}{caminho}"
        response = self.session.get(url, auth=(token, ""), timeout=60)
        response.raise_for_status()
        return response.text

    def consultar_cte_emitido(self, token: str, ref: str) -> dict[str, Any]:
        if settings.use_mock_focus_nfe:
            return self._mock_emitida_status("cte", ref)
        return self._request(token, "GET", CTE_EMITIDO_ENDPOINT.format(ref=ref))

    def consultar_nfse_emitida(self, token: str, ref: str) -> dict[str, Any]:
        if settings.use_mock_focus_nfe:
            return self._mock_emitida_status("nfse", ref)
        return self._request(token, "GET", NFSE_EMITIDA_ENDPOINT.format(ref=ref))

    # --- NFe RECEBIDAS (DF-e / manifestacao do destinatario) ---

    def listar_nfes_recebidas(
        self,
        token: str,
        cnpj: str,
        *,
        nsu: str | None = None,
        data_inicio: datetime | None = None,
        data_fim: datetime | None = None,
    ) -> list[DocumentoRecebidoFocus]:
        """Lista todas as NFe recebidas pelo CNPJ via DF-e.

        Pagina automaticamente por NSU (incremental, persistivel) ate esgotar.
        Filtros `data_inicio`/`data_fim` sao aplicados client-side em `data_emissao`.
        """
        if settings.use_mock_focus_nfe:
            return self._mock_recebidas(cnpj)

        resultados: list[DocumentoRecebidoFocus] = []
        nsu_atual = nsu
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"cnpj": cnpj}
            if nsu_atual:
                params["nsu"] = nsu_atual
            payload = self._request(token, "GET", NFES_RECEBIDAS_ENDPOINT, params=params)
            itens = self._extrair_itens(payload)
            if not itens:
                break

            for item in itens:
                doc = self._normalizar_recebida(item)
                if not self._dentro_da_janela(doc.data_emissao, data_inicio, data_fim):
                    continue
                resultados.append(doc)

            ultimo_nsu = self._maior_nsu(itens)
            if not ultimo_nsu or ultimo_nsu == nsu_atual:
                break
            nsu_atual = ultimo_nsu
        return resultados

    def consultar_nfe_recebida(self, token: str, chave: str) -> dict[str, Any]:
        if settings.use_mock_focus_nfe:
            return self._mock_recebida_detalhe(chave)
        return self._request(token, "GET", NFE_RECEBIDA_ENDPOINT.format(chave=chave))

    def baixar_xml_nfe_recebida(self, token: str, chave: str) -> str:
        """Baixa o XML de uma NFe recebida (DF-e) pela chave de 44 digitos."""
        if settings.use_mock_focus_nfe:
            return self._mock_xml_nfe(chave)
        headers = {"Accept": "application/xml"}
        response = self.session.get(
            f"{self.base_url}{NFE_RECEBIDA_XML_ENDPOINT.format(chave=chave)}",
            auth=(token, ""),
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        return response.text

    def manifestar_nfe_recebida(
        self,
        token: str,
        chave: str,
        tipo: ManifestacaoTipo = "ciencia",
        justificativa: str | None = None,
    ) -> dict[str, Any]:
        """Registra manifestacao do destinatario para a chave informada.

        Tipos validos Focus: `ciencia`, `confirmacao`, `desconhecimento`,
        `nao_realizada`. Para o caso contabil padrao (apenas registrar que
        recebeu a NF), `ciencia` eh o adequado.

        Resposta inclui `status_sefaz`, `protocolo`, `mensagem_sefaz`. SEFAZ
        retorna status `135` quando aceito ("Evento registrado e vinculado").

        IMPORTANTE: apos manifestar, a Focus precisa de alguns minutos para
        sincronizar e disponibilizar o XML completo (procNFe) e o DANFE PDF.
        Logo, fluxo pratico: robo lista -> manifesta -> aguarda 5min ->
        roda denovo pra baixar XML completo + PDF.
        """
        if settings.use_mock_focus_nfe:
            return {
                "status_sefaz": "135",
                "mensagem_sefaz": "Evento registrado e vinculado a NF-e (mock)",
                "status": "evento_registrado",
                "protocolo": f"MOCK-{chave[-10:]}",
                "tipo": tipo,
            }
        payload: dict[str, Any] = {"tipo": tipo}
        if justificativa and tipo in ("desconhecimento", "nao_realizada"):
            payload["justificativa"] = justificativa
        return self._request(
            token, "POST",
            NFE_RECEBIDA_MANIFESTO_ENDPOINT.format(chave=chave),
            json=payload,
        )

    def baixar_pdf_nfe_recebida(self, token: str, chave: str) -> bytes:
        """Baixa o DANFE em PDF de uma NFe recebida.

        IMPORTANTE: so funciona se a NF ja foi manifestada (operacao 210210
        Ciencia). Caso contrario a Focus retorna HTTP 404. Use
        `manifestar_nfe_recebida` antes e aguarde alguns minutos para sync.
        """
        if settings.use_mock_focus_nfe:
            return b"%PDF-1.4 mock DANFE\n"
        response = self.session.get(
            f"{self.base_url}/v2/nfes_recebidas/{chave}.pdf",
            auth=(token, ""),
            timeout=60,
        )
        response.raise_for_status()
        return response.content

    def listar_ctes_recebidos(
        self,
        token: str,
        cnpj: str,
        *,
        nsu: str | None = None,
        data_inicio: datetime | None = None,
        data_fim: datetime | None = None,
    ) -> list[DocumentoRecebidoFocus]:
        """Equivalente a `listar_nfes_recebidas` para CTe (entradas)."""
        if settings.use_mock_focus_nfe:
            return self._mock_recebidas(cnpj, tipo="cte")

        resultados: list[DocumentoRecebidoFocus] = []
        nsu_atual = nsu
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"cnpj": cnpj}
            if nsu_atual:
                params["nsu"] = nsu_atual
            payload = self._request(token, "GET", CTES_RECEBIDOS_ENDPOINT, params=params)
            itens = self._extrair_itens(payload)
            if not itens:
                break
            for item in itens:
                doc = self._normalizar_recebida(item, tipo_default="cte")
                if not self._dentro_da_janela(doc.data_emissao, data_inicio, data_fim):
                    continue
                resultados.append(doc)
            ultimo_nsu = self._maior_nsu(itens)
            if not ultimo_nsu or ultimo_nsu == nsu_atual:
                break
            nsu_atual = ultimo_nsu
        return resultados

    # --- Helpers internos ---

    def _request(
        self,
        token: str,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        if not token:
            raise FocusTokenAusenteError("Token Focus NFe ausente.")
        headers = {"Accept": "application/json"}
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{endpoint}",
            auth=(token, ""),
            headers=headers,
            params=params,
            json=json,
            data=data,
            files=files,
            timeout=60,
        )
        # IMPORTANTE: substitui raise_for_status() padrão pra incluir o BODY
        # do erro na exceção. Focus retorna mensagens úteis em 4xx/5xx (qual
        # campo faltou, qual validação falhou, etc), mas raise_for_status()
        # padrão joga apenas "500 Server Error" sem contexto.
        if response.status_code >= 400:
            try:
                # JSONDecodeError herda de ValueError; pega ambos com um catch
                body = response.json() if response.content else {}
            except ValueError:
                body = response.text[:1000] if response.text else ""
            # Mensagem amigável: tenta extrair `mensagem`/`erros`/`mensagens`
            # do JSON Focus, senão usa texto cru.
            detalhe = ""
            if isinstance(body, dict):
                detalhe = (
                    body.get("mensagem")
                    or body.get("codigo")
                    or " | ".join(
                        m.get("mensagem", "") if isinstance(m, dict) else str(m)
                        for m in (body.get("erros") or body.get("mensagens") or [])
                    )
                    or str(body)[:500]
                )
            else:
                detalhe = str(body)[:500]
            raise requests.HTTPError(
                f"{response.status_code} {response.reason} - {detalhe}",
                response=response,
            )
        if not expect_json or response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _extrair_itens(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "nfes", "ctes", "documentos", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _maior_nsu(itens: list[dict[str, Any]]) -> str | None:
        valores: list[int] = []
        for item in itens:
            nsu = item.get("nsu") or item.get("ultimo_nsu")
            if nsu is None:
                continue
            try:
                valores.append(int(str(nsu)))
            except (TypeError, ValueError):
                continue
        return str(max(valores)) if valores else None

    @staticmethod
    def _normalizar_recebida(
        item: dict[str, Any],
        *,
        tipo_default: str = "nfe",
    ) -> DocumentoRecebidoFocus:
        chave = (
            item.get("chave_nfe")
            or item.get("chave")
            or item.get("chave_acesso")
            or ""
        )
        cnpj_emit = (
            item.get("cnpj_emitente")
            or item.get("emitente_cnpj")
            or (item.get("emitente") or {}).get("cnpj")
            or (item.get("emitente") or {}).get("cpf_cnpj")
            or ""
        )
        nome_emit = (
            item.get("nome_emitente")
            or item.get("emitente_nome")
            or (item.get("emitente") or {}).get("nome")
            or (item.get("emitente") or {}).get("nome_razao_social")
        )
        valor_raw = item.get("valor_total") or item.get("valor")
        valor = None
        if valor_raw is not None:
            try:
                valor = Decimal(str(valor_raw))
            except Exception:
                valor = None
        return DocumentoRecebidoFocus(
            chave=str(chave),
            nsu=str(item.get("nsu") or ""),
            cnpj_emitente=str(cnpj_emit),
            nome_emitente=nome_emit,
            valor_total=valor,
            data_emissao=parse_data_emissao(item.get("data_emissao") or item.get("dhEmi")),
            tipo=str(item.get("tipo") or item.get("tipo_documento") or tipo_default).lower(),
            raw=item,
        )

    @staticmethod
    def _dentro_da_janela(
        dt: datetime | None,
        inicio: datetime | None,
        fim: datetime | None,
    ) -> bool:
        if dt is None:
            # Sem data: incluir defensivamente para nao perder documentos.
            return True
        dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
        if inicio is not None:
            ini_naive = inicio.replace(tzinfo=None) if inicio.tzinfo else inicio
            if dt_naive < ini_naive:
                return False
        if fim is not None:
            fim_naive = fim.replace(tzinfo=None) if fim.tzinfo else fim
            if dt_naive > fim_naive:
                return False
        return True

    # --- Mocks (USE_MOCK_FOCUS_NFE=true) ---

    @staticmethod
    def _mock_empresa(cnpj: str) -> dict[str, Any]:
        return {
            "cnpj": cnpj,
            "nome": f"Empresa {cnpj}",
            "nome_fantasia": "Empresa Mock",
            "regime_tributario": "1",
            "habilita_nfe": True,
            "habilita_nfce": False,
            "habilita_cte": False,
            "habilita_nfse": False,
            "token_homologacao": f"mock-homolog-{cnpj}",
            "token_producao": f"mock-prod-{cnpj}",
            "certificado_valido_de": "2026-01-01",
            "certificado_valido_ate": "2027-01-01",
        }

    @staticmethod
    def _mock_emitida_status(tipo: str, ref: str) -> dict[str, Any]:
        return {
            "ref": ref,
            "status": "autorizado",
            "tipo": tipo,
            "caminho_xml_nota_fiscal": f"/mock/{tipo}/{ref}.xml",
            "caminho_danfe": f"/mock/{tipo}/{ref}.pdf",
        }

    @staticmethod
    def _mock_recebidas(cnpj: str, *, tipo: str = "nfe") -> list[DocumentoRecebidoFocus]:
        fornecedor = "11111111000111"
        agora = datetime.now(timezone.utc).replace(tzinfo=None)
        # Chave de acesso fake 100% numerica (44 digitos): UF(2) + AAMM(4) + CNPJ(14) +
        # mod(2) + serie(3) + nNF(9) + tpEmis(1) + cNF(8) + cDV(1).
        chave = (
            f"26{agora.strftime('%y%m')}{fornecedor}55001"
            f"{agora.strftime('%j%H%M%S').zfill(11)}19999"
        )[:44].ljust(44, "0")
        return [
            DocumentoRecebidoFocus(
                chave=chave,
                nsu="1",
                cnpj_emitente=fornecedor,
                nome_emitente="Fornecedor Mock LTDA",
                valor_total=Decimal("800.00"),
                data_emissao=agora,
                tipo=tipo,
                raw={
                    "chave_nfe": chave,
                    "nsu": "1",
                    "cnpj_emitente": fornecedor,
                    "nome_emitente": "Fornecedor Mock LTDA",
                    "valor_total": 800.00,
                    "data_emissao": agora.isoformat(),
                    "tipo": tipo,
                },
            )
        ]

    @staticmethod
    def _mock_recebida_detalhe(chave: str) -> dict[str, Any]:
        return {
            "chave_nfe": chave,
            "nsu": "1",
            "status": "autorizada",
            "cnpj_emitente": "11111111000111",
            "nome_emitente": "Fornecedor Mock LTDA",
            "valor_total": 800.00,
        }

    @staticmethod
    def _mock_xml_nfe(chave_ou_ref: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc>
  <NFe>
    <infNFe Id="NFe{chave_ou_ref}">
      <ide><nNF>1001</nNF><serie>1</serie><dhEmi>2026-04-24T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>11111111000111</CNPJ><xNome>Fornecedor Mock LTDA</xNome></emit>
      <dest><CNPJ>12345678000195</CNPJ><xNome>Empresa Mock</xNome></dest>
      <det nItem="1"><prod><CFOP>1102</CFOP></prod></det>
      <total><ICMSTot><vNF>800.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
</nfeProc>"""
