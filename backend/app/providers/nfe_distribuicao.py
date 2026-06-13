"""Distribuição de DF-e da NFe (NFeDistribuicaoDFe) — DIRETO, sem Focus.

Puxa do Ambiente Nacional da Receita os documentos do CNPJ da empresa:
- RECEBIDAS (resNFe): resumo das NFes emitidas CONTRA a empresa (compras) —
  vem sem custo e sem manifestar (chave, emitente, valor, data).
- EMITIDAS / completas (procNFe): XML completo quando disponível.
- Eventos (resEvento/procEventoNFe): cancelamentos etc.

Modelo NSU (Número Sequencial Único): o AN numera cada doc do CNPJ; pedimos
"a partir do ultNSU" e recebemos até ~50 + o novo maxNSU. Guardamos o NSU e
continuamos de onde paramos (incremental).

Autenticação: mTLS com o certificado A1 (e-CNPJ) da própria empresa — que o
PAC já guarda em storage/certs/<cnpj>.pfx. SEM custo por nota (≠ Focus).

NÃO faz manifestação aqui (evento assinado = fase 2). Esta camada só DISTRIBUI.

Ref: MOC NF-e, NFeDistribuicaoDFe v1.01. cStat: 137=nenhum doc, 138=docs
localizados, 656=consumo indevido (esperar 1h).
"""
from __future__ import annotations

import base64
import gzip
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


# Endpoint do Ambiente Nacional (produção). Homologação tem host próprio.
URL_AN_PRODUCAO = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
URL_AN_HOMOLOG = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
SOAP_ACTION = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"

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
class DocDistribuido:
    """Um documento devolvido pela distribuição."""
    nsu: str
    schema: str                  # resNFe_v1.01 | procNFe_v4.00 | resEvento_v1.01 ...
    tipo: str                    # RECEBIDA_RESUMO | NFE_COMPLETA | EVENTO | OUTRO
    chave: str | None = None
    cnpj_emitente: str | None = None
    nome_emitente: str | None = None
    valor: str | None = None
    data_emissao: str | None = None
    situacao: str | None = None  # cSitNFe (1=autorizada, 2=cancelada...)
    xml: str | None = None       # XML completo (só procNFe)


@dataclass
class ResultadoDistribuicao:
    cstat: str
    motivo: str
    ult_nsu: str
    max_nsu: str
    docs: list[DocDistribuido] = field(default_factory=list)

    @property
    def tem_mais(self) -> bool:
        """True se ainda há docs além do ultNSU (maxNSU > ultNSU)."""
        try:
            return int(self.max_nsu) > int(self.ult_nsu)
        except (ValueError, TypeError):
            return False


class NFeDistribuicaoProvider:
    def __init__(self) -> None:
        self.homolog = os.getenv("NFE_DIST_HOMOLOG", "false").lower() == "true"
        self.url = URL_AN_HOMOLOG if self.homolog else URL_AN_PRODUCAO
        self.tp_amb = "2" if self.homolog else "1"
        self.timeout = int(os.getenv("NFE_DIST_TIMEOUT_S", "60"))

    # ------------------------------------------------------------------
    def distribuir(
        self, *, cnpj: str, uf: str, pfx_path: str, pfx_senha: str, ult_nsu: str = "0",
    ) -> ResultadoDistribuicao:
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
            '<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
            '<nfeDadosMsg>'
            f'<distDFeInt xmlns="{NS_NFE}" versao="1.01">'
            f'<tpAmb>{self.tp_amb}</tpAmb>'
            f'<cUFAutor>{cuf}</cUFAutor>'
            f'<CNPJ>{cnpj}</CNPJ>'
            f'<distNSU><ultNSU>{ult_nsu}</ultNSU></distNSU>'
            '</distDFeInt>'
            '</nfeDadosMsg>'
            '</nfeDistDFeInteresse>'
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

    def _parse_resposta(self, resp_xml: str) -> ResultadoDistribuicao:
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

        docs: list[DocDistribuido] = []
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
                logger.warning("Falha ao descompactar docZip NSU=%s: %s", nsu, exc)
        return ResultadoDistribuicao(
            cstat=cstat, motivo=motivo, ult_nsu=ult_nsu, max_nsu=max_nsu, docs=docs,
        )

    @staticmethod
    def _classificar_doc(nsu: str, schema: str, xml: str) -> DocDistribuido:
        inner = ET.fromstring(xml)
        nome_raiz = _local(inner.tag)
        s = schema.lower()
        if nome_raiz == "resNFe" or s.startswith("resnfe"):
            return DocDistribuido(
                nsu=nsu, schema=schema, tipo="RECEBIDA_RESUMO",
                chave=_txt(inner, "chNFe"),
                cnpj_emitente=_txt(inner, "CNPJ"),
                nome_emitente=_txt(inner, "xNome"),
                valor=_txt(inner, "vNF"),
                data_emissao=_txt(inner, "dhEmi"),
                situacao=_txt(inner, "cSitNFe"),
            )
        if nome_raiz in ("nfeProc", "NFe") or s.startswith("procnfe"):
            return DocDistribuido(
                nsu=nsu, schema=schema, tipo="NFE_COMPLETA",
                chave=(_txt(inner, "chNFe") or _chave_de_infnfe(inner)),
                cnpj_emitente=_txt(inner, "CNPJ"),
                nome_emitente=_txt(inner, "xNome"),
                valor=_txt(inner, "vNF"),
                data_emissao=_txt(inner, "dhEmi"),
                xml=xml,
            )
        if nome_raiz in ("resEvento", "procEventoNFe") or "evento" in s:
            return DocDistribuido(
                nsu=nsu, schema=schema, tipo="EVENTO",
                chave=_txt(inner, "chNFe"),
            )
        return DocDistribuido(nsu=nsu, schema=schema, tipo="OUTRO")


def _chave_de_infnfe(root: ET.Element) -> str | None:
    inf = next((e for e in root.iter() if _local(e.tag) == "infNFe"), None)
    if inf is not None:
        raw = inf.attrib.get("Id", "")
        return raw.replace("NFe", "") if raw else None
    return None
