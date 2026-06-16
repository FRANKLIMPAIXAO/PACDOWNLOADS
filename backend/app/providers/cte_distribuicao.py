"""Distribuição de DF-e do CT-e (CTeDistribuicaoDFe) — DIRETO, sem Focus.

Espelho do `nfe_distribuicao.py`, mas pro Conhecimento de Transporte (CT-e):
puxa do Ambiente Nacional os documentos de transporte do CNPJ da empresa:
- RECEBIDAS (resCTe): resumo do CT-e em que a empresa é TOMADORA do frete
  (quem paga) — vem sem custo (chave, emitente/transportadora, vTPrest, data).
- COMPLETAS (procCTe/cteProc): XML completo quando o AN distribui.
- Eventos (resEvento/procEventoCTe): cancelamentos etc.

Mesmo modelo NSU (Número Sequencial Único) e mTLS com o cert A1 (e-CNPJ) que a
Distribuição da NFe já usa. SEM custo por documento.

CT-e importa pro crédito de ICMS / PIS-COFINS de FRETE (ex.: indústria que
recebe muito transporte). O valor relevante é `vTPrest` (valor total da
prestação do serviço de transporte).

Endpoint/versão/namespace são CONFIGURÁVEIS por env (CTE_DIST_URL etc.) — caso
o ambiente exija ajuste, dá pra trocar sem novo deploy de código.

Ref: MOC CT-e, CTeDistribuicaoDFe. cStat: 137=nenhum doc, 138=docs localizados,
656=consumo indevido (esperar ~1h).
"""
from __future__ import annotations

import base64
import gzip
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


# Endpoint do Ambiente Nacional do CT-e (produção). Host é `cte.fazenda.gov.br`
# (NÃO `nfe`) — o CT-e tem ambiente próprio. Hom e prod usam o MESMO endereço
# (o tpAmb diferencia). Confirmado na NT 2015.002 / impl. sped-cte. Override por
# env se preciso (CTE_DIST_URL).
URL_AN_PRODUCAO = os.getenv(
    "CTE_DIST_URL",
    "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx",
)
URL_AN_HOMOLOG = os.getenv(
    "CTE_DIST_URL_HOMOLOG",
    "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx",
)

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_WSDL = "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe"
SOAP_ACTION = f"{NS_WSDL}/cteDistDFeInteresse"
# versao do distDFeInt do CT-e (1.00). Override por env caso o AN mude.
VERSAO = os.getenv("CTE_DIST_VERSAO", "1.00")

# Código IBGE da UF (cUFAutor). Foco em GO; mapa completo pra multi-UF.
UF_IBGE = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _txt(elem: ET.Element | None, nome: str) -> str | None:
    if elem is None:
        return None
    for e in elem.iter():
        if _local(e.tag) == nome and e.text:
            return e.text.strip()
    return None


@dataclass
class DocCteDistribuido:
    """Um documento de transporte devolvido pela distribuição."""
    nsu: str
    schema: str                  # resCTe_v1.00 | procCTe_v4.00 | resEvento ...
    tipo: str                    # RECEBIDA_RESUMO | CTE_COMPLETA | EVENTO | OUTRO
    chave: str | None = None
    cnpj_emitente: str | None = None     # transportadora
    nome_emitente: str | None = None
    valor: str | None = None             # vTPrest (valor total da prestação)
    data_emissao: str | None = None
    situacao: str | None = None          # cSitCTe (1=autorizado, 3=cancelado...)
    xml: str | None = None               # XML completo (só procCTe)


@dataclass
class ResultadoDistribuicaoCte:
    cstat: str
    motivo: str
    ult_nsu: str
    max_nsu: str
    docs: list[DocCteDistribuido] = field(default_factory=list)

    @property
    def tem_mais(self) -> bool:
        """True se ainda há docs além do ultNSU (maxNSU > ultNSU)."""
        try:
            return int(self.max_nsu) > int(self.ult_nsu)
        except (ValueError, TypeError):
            return False


class CteDistribuicaoProvider:
    def __init__(self) -> None:
        self.homolog = os.getenv("CTE_DIST_HOMOLOG", "false").lower() == "true"
        self.url = URL_AN_HOMOLOG if self.homolog else URL_AN_PRODUCAO
        self.tp_amb = "2" if self.homolog else "1"
        self.timeout = int(os.getenv("CTE_DIST_TIMEOUT_S", "60"))

    # ------------------------------------------------------------------
    def distribuir(
        self, *, cnpj: str, uf: str, pfx_path: str, pfx_senha: str, ult_nsu: str = "0",
    ) -> ResultadoDistribuicaoCte:
        """Chama distNSU (a partir do ultNSU). Devolve até ~50 docs + novo NSU."""
        cnpj_num = "".join(c for c in (cnpj or "") if c.isdigit())
        cuf = UF_IBGE.get((uf or "GO").upper(), "52")
        ult = str(ult_nsu or "0").zfill(15)

        envelope = self._montar_envelope_distnsu(cnpj_num, cuf, ult)
        resp_xml = self._post_mtls(envelope, pfx_path, pfx_senha)
        return self._parse_resposta(resp_xml)

    # ------------------------------------------------------------------
    def _montar_envelope_distnsu(self, cnpj: str, cuf: str, ult_nsu: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            '<soap12:Body>'
            f'<cteDistDFeInteresse xmlns="{NS_WSDL}">'
            '<cteDadosMsg>'
            f'<distDFeInt xmlns="{NS_CTE}" versao="{VERSAO}">'
            f'<tpAmb>{self.tp_amb}</tpAmb>'
            f'<cUFAutor>{cuf}</cUFAutor>'
            f'<CNPJ>{cnpj}</CNPJ>'
            f'<distNSU><ultNSU>{ult_nsu}</ultNSU></distNSU>'
            '</distDFeInt>'
            '</cteDadosMsg>'
            '</cteDistDFeInteresse>'
            '</soap12:Body>'
            '</soap12:Envelope>'
        )

    def _post_mtls(self, envelope: str, pfx_path: str, pfx_senha: str) -> str:
        """POST SOAP com mTLS usando o cert A1 (extrai PEM temporário do PFX)."""
        cert_pem, key_pem = self._pfx_para_pem(pfx_path, pfx_senha)
        cert_f = tempfile.NamedTemporaryFile(delete=False, suffix=".crt.pem")
        key_f = tempfile.NamedTemporaryFile(delete=False, suffix=".key.pem")
        try:
            cert_f.write(cert_pem); cert_f.flush(); cert_f.close()
            key_f.write(key_pem); key_f.flush(); key_f.close()
            headers = {
                "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"',
            }
            resp = requests.post(
                self.url, data=envelope.encode("utf-8"), headers=headers,
                cert=(cert_f.name, key_f.name), timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.text
        finally:
            for f in (cert_f.name, key_f.name):
                try:
                    os.unlink(f)
                except OSError:
                    pass

    @staticmethod
    def _pfx_para_pem(pfx_path: str, senha: str) -> tuple[bytes, bytes]:
        """Extrai (cert_pem, key_pem) do .pfx pra usar como mTLS no requests."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12

        pfx_bytes = Path(pfx_path).read_bytes()
        key, cert, _chain = pkcs12.load_key_and_certificates(
            pfx_bytes, (senha or "").encode("utf-8"),
        )
        if key is None or cert is None:
            raise ValueError("PFX sem chave/certificado")
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        return cert_pem, key_pem

    def _parse_resposta(self, resp_xml: str) -> ResultadoDistribuicaoCte:
        root = ET.fromstring(resp_xml)
        ret = next((e for e in root.iter() if _local(e.tag) == "retDistDFeInt"), None)
        if ret is None:
            # SOAP fault ou resposta inesperada
            fault = next((e for e in root.iter() if _local(e.tag) in ("Text", "faultstring")), None)
            raise RuntimeError(
                f"Resposta sem retDistDFeInt: {(fault.text if fault is not None else resp_xml[:300])}"
            )
        cstat = _txt(ret, "cStat") or "?"
        motivo = _txt(ret, "xMotivo") or ""
        ult_nsu = _txt(ret, "ultNSU") or "0"
        max_nsu = _txt(ret, "maxNSU") or "0"

        docs: list[DocCteDistribuido] = []
        for doczip in ret.iter():
            if _local(doczip.tag) != "docZip":
                continue
            nsu = doczip.attrib.get("NSU", "")
            schema = doczip.attrib.get("schema", "")
            try:
                conteudo = gzip.decompress(base64.b64decode(doczip.text or "")).decode("utf-8")
                doc = self._classificar_doc(nsu, schema, conteudo)
                docs.append(doc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao descompactar docZip CT-e NSU=%s: %s", nsu, exc)
        return ResultadoDistribuicaoCte(
            cstat=cstat, motivo=motivo, ult_nsu=ult_nsu, max_nsu=max_nsu, docs=docs,
        )

    @staticmethod
    def _classificar_doc(nsu: str, schema: str, xml: str) -> DocCteDistribuido:
        inner = ET.fromstring(xml)
        nome_raiz = _local(inner.tag)
        s = schema.lower()
        if nome_raiz == "resCTe" or s.startswith("rescte"):
            return DocCteDistribuido(
                nsu=nsu, schema=schema, tipo="RECEBIDA_RESUMO",
                chave=_txt(inner, "chCTe"),
                cnpj_emitente=_txt(inner, "CNPJ"),
                nome_emitente=_txt(inner, "xNome"),
                valor=_txt(inner, "vTPrest"),
                data_emissao=_txt(inner, "dhEmi"),
                situacao=_txt(inner, "cSitCTe"),
            )
        if nome_raiz in ("cteProc", "CTe", "procCTe") or s.startswith("proccte"):
            return DocCteDistribuido(
                nsu=nsu, schema=schema, tipo="CTE_COMPLETA",
                chave=(_txt(inner, "chCTe") or _chave_de_infcte(inner)),
                cnpj_emitente=_txt(inner, "CNPJ"),
                nome_emitente=_txt(inner, "xNome"),
                valor=_txt(inner, "vTPrest"),
                data_emissao=_txt(inner, "dhEmi"),
                xml=xml,
            )
        if nome_raiz in ("resEvento", "procEventoCTe") or "evento" in s:
            return DocCteDistribuido(
                nsu=nsu, schema=schema, tipo="EVENTO",
                chave=_txt(inner, "chCTe"),
            )
        return DocCteDistribuido(nsu=nsu, schema=schema, tipo="OUTRO")


def _chave_de_infcte(root: ET.Element) -> str | None:
    inf = next((e for e in root.iter() if _local(e.tag) == "infCte"), None)
    if inf is not None:
        raw = inf.attrib.get("Id", "")
        return raw.replace("CTe", "") if raw else None
    return None
