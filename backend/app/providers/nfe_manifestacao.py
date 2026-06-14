"""Manifestação do Destinatário — evento "Ciência da Operação" (tpEvento 210210).

Necessário pra liberar o XML COMPLETO das recebidas que vieram só como RESUMO
na Distribuição DF-e. A "Ciência da Operação" é a manifestação mais leve (só
"estou ciente que essa nota existe contra mim", sem aceite/compromisso).

Fluxo: monta o evento → ASSINA com XML-DSig (cert A1 da empresa) → envia ao
webservice NFeRecepcaoEvento4 (Ambiente Nacional) via SOAP+mTLS → cStat 135/136
= registrado. Depois disso, a próxima Distribuição traz o procNFe (XML completo).

Assinatura: XML-DSig manual com lxml (C14N 1.0) + cryptography (RSA-SHA1), no
padrão NFe (assina o <infEvento> via Reference URI="#Id", transforms
enveloped-signature + C14N). Sem xmlsec (evita dep nativa no Docker).

Ref: MOC NF-e, Manifestação do Destinatário; evento 210210.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from lxml import etree

logger = logging.getLogger(__name__)

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_SIG = "http://www.w3.org/2000/09/xmldsig#"
# ATENÇÃO ao host: o serviço de EVENTO/manifestação do Ambiente Nacional fica em
# `www.nfe.fazenda.gov.br` (SEM o "1"), diferente da Distribuição DFe que fica em
# `www1`. Usar www1 aqui devolve "action não reconhecida" (é outro deployment).
# Confirmado no config do sped-nfe (AN RecepcaoEvento 4.00).
URL_AN_EVENTO_PROD = "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"
URL_AN_EVENTO_HOM = "https://hom.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"
SOAP_ACTION_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEvento"

# Brasília (sem horário de verão desde 2019)
_TZ_BR = timezone(timedelta(hours=-3))


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _c14n(elem) -> bytes:
    """C14N 1.0 inclusiva COMPATÍVEL com a da SEFAZ.

    Bug do lxml: ao canonicalizar uma sub-árvore cujo namespace default vem de
    um ancestral (caso do nosso <infEvento>/<SignedInfo>), ele emite `xmlns=""`
    espúrio nos elementos aninhados — bytes que NÃO batem com a C14N que a
    Receita recalcula → DigestValue/SignatureValue divergem → cStat 297.

    Serializar e reparsear o elemento isola os namespaces NELE mesmo, e aí a
    C14N sai correta (validado: bate byte a byte com xml.etree.canonicalize).
    """
    return etree.tostring(
        etree.fromstring(etree.tostring(elem)),
        method="c14n", exclusive=False, with_comments=False,
    )


def _extrair_fault(corpo: str) -> str | None:
    """Tira o motivo legível de um corpo de erro do .asmx.

    A SEFAZ devolve HTTP 500 com o motivo real dentro: SOAP 1.2 usa
    <env:Reason><env:Text>, SOAP 1.1 usa <faultstring>; às vezes ainda vem um
    cStat/xMotivo estruturado. Pega o que existir.
    """
    if not corpo:
        return None
    try:
        root = etree.fromstring(corpo.encode("utf-8"))
    except Exception:  # noqa: BLE001 — corpo pode não ser XML
        return None
    alvos = ("Text", "faultstring", "xMotivo", "Reason", "Detail")
    achados: list[str] = []
    cstat = None
    for e in root.iter():
        nome = _local(e.tag)
        if nome == "cStat" and e.text:
            cstat = e.text.strip()
        if nome in alvos and e.text and e.text.strip():
            achados.append(e.text.strip())
    msg = " | ".join(dict.fromkeys(achados)) if achados else None
    if cstat and msg:
        return f"cStat {cstat}: {msg}"
    return msg or (f"cStat {cstat}" if cstat else None)


class NFeManifestacaoProvider:
    def __init__(self) -> None:
        self.homolog = os.getenv("NFE_DIST_HOMOLOG", "false").lower() == "true"
        self.url = URL_AN_EVENTO_HOM if self.homolog else URL_AN_EVENTO_PROD
        self.tp_amb = "2" if self.homolog else "1"
        self.timeout = int(os.getenv("NFE_DIST_TIMEOUT_S", "60"))

    # ------------------------------------------------------------------
    def manifestar_ciencia(
        self, *, chave: str, cnpj: str, pfx_path: str, pfx_senha: str,
        n_seq: int = 1,
    ) -> dict:
        """Envia "Ciência da Operação" pra UMA nota. Devolve cStat/motivo."""
        cnpj_num = "".join(c for c in (cnpj or "") if c.isdigit())
        chave = "".join(c for c in (chave or "") if c.isdigit())
        if len(chave) != 44:
            raise ValueError(f"Chave NFe inválida (len={len(chave)})")

        key, cert = self._carregar_pfx(pfx_path, pfx_senha)
        env_evento = self._montar_evento_assinado(chave, cnpj_num, n_seq, key, cert)
        resp_xml = self._post_mtls(env_evento, key, cert)
        return self._parse_resposta(resp_xml)

    # ------------------------------------------------------------------
    @staticmethod
    def _carregar_pfx(pfx_path: str, senha: str):
        from cryptography.hazmat.primitives.serialization import pkcs12

        pfx = Path(pfx_path).read_bytes()
        key, cert, _ = pkcs12.load_key_and_certificates(pfx, (senha or "").encode("utf-8"))
        if key is None or cert is None:
            raise ValueError("PFX sem chave/certificado")
        return key, cert

    def _montar_evento_assinado(self, chave, cnpj, n_seq, key, cert) -> bytes:
        seq = f"{int(n_seq):02d}"
        ev_id = f"ID210210{chave}{seq}"
        dh = datetime.now(_TZ_BR).strftime("%Y-%m-%dT%H:%M:%S%z")
        dh = dh[:-2] + ":" + dh[-2:]  # +0000 -> +00:00

        E = "{%s}" % NS_NFE
        nsmap = {None: NS_NFE}
        env = etree.Element(E + "envEvento", versao="1.00", nsmap=nsmap)
        etree.SubElement(env, E + "idLote").text = "1"
        evento = etree.SubElement(env, E + "evento", versao="1.00")
        inf = etree.SubElement(evento, E + "infEvento")
        inf.set("Id", ev_id)
        etree.SubElement(inf, E + "cOrgao").text = "91"  # Ambiente Nacional
        etree.SubElement(inf, E + "tpAmb").text = self.tp_amb
        etree.SubElement(inf, E + "CNPJ").text = cnpj
        etree.SubElement(inf, E + "chNFe").text = chave
        etree.SubElement(inf, E + "dhEvento").text = dh
        etree.SubElement(inf, E + "tpEvento").text = "210210"
        etree.SubElement(inf, E + "nSeqEvento").text = str(int(n_seq))
        etree.SubElement(inf, E + "verEvento").text = "1.00"
        det = etree.SubElement(inf, E + "detEvento", versao="1.00")
        etree.SubElement(det, E + "descEvento").text = "Ciencia da Operacao"

        self._assinar(evento, inf, ev_id, key, cert)
        return etree.tostring(env, encoding="UTF-8")

    @staticmethod
    def _assinar(evento_el, inf_el, ref_id, key, cert) -> None:
        """Assina o <infEvento> no padrão NFe (XML-DSig enveloped, C14N, RSA-SHA1)."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        # 1. DigestValue = base64(SHA1(C14N(infEvento)))
        c14n_inf = _c14n(inf_el)
        digest = base64.b64encode(hashlib.sha1(c14n_inf).digest()).decode()

        S = "{%s}" % NS_SIG
        sig = etree.SubElement(evento_el, S + "Signature", nsmap={None: NS_SIG})
        signed_info = etree.SubElement(sig, S + "SignedInfo")
        etree.SubElement(signed_info, S + "CanonicalizationMethod").set(
            "Algorithm", "http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        etree.SubElement(signed_info, S + "SignatureMethod").set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#rsa-sha1")
        ref = etree.SubElement(signed_info, S + "Reference")
        ref.set("URI", "#" + ref_id)
        transforms = etree.SubElement(ref, S + "Transforms")
        etree.SubElement(transforms, S + "Transform").set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature")
        etree.SubElement(transforms, S + "Transform").set(
            "Algorithm", "http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        etree.SubElement(ref, S + "DigestMethod").set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#sha1")
        etree.SubElement(ref, S + "DigestValue").text = digest

        # 2. SignatureValue = base64(RSA-SHA1(C14N(SignedInfo)))
        c14n_si = _c14n(signed_info)
        assinatura = key.sign(c14n_si, padding.PKCS1v15(), hashes.SHA1())
        etree.SubElement(sig, S + "SignatureValue").text = base64.b64encode(assinatura).decode()

        # 3. KeyInfo / X509Certificate (DER base64)
        key_info = etree.SubElement(sig, S + "KeyInfo")
        x509 = etree.SubElement(key_info, S + "X509Data")
        cert_der = cert.public_bytes(serialization.Encoding.DER)
        etree.SubElement(x509, S + "X509Certificate").text = base64.b64encode(cert_der).decode()

    # ------------------------------------------------------------------
    def diagnosticar_variantes(self, *, chave: str, cnpj: str, pfx_path: str,
                               pfx_senha: str) -> list[dict]:
        """Dispara o MESMO evento assinado em várias formas de envelope/transporte
        e devolve o que cada uma respondeu. Serve pra descobrir, sem chute, qual
        combinação (SOAP 1.1/1.2, SOAPAction em header, wrapper, host) o
        NFeRecepcaoEvento4 do AN aceita — em vez de deploy a deploy.
        """
        from cryptography.hazmat.primitives import serialization

        cnpj_num = "".join(c for c in (cnpj or "") if c.isdigit())
        chave = "".join(c for c in (chave or "") if c.isdigit())
        if len(chave) != 44:
            raise ValueError(f"Chave NFe inválida (len={len(chave)})")
        key, cert = self._carregar_pfx(pfx_path, pfx_senha)
        env = self._montar_evento_assinado(chave, cnpj_num, 1, key, cert).decode("utf-8")

        wsdl_ns = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"
        url_www = "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"
        url_www1 = "https://www1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"

        wrap = f'<nfeRecepcaoEvento xmlns="{wsdl_ns}"><nfeDadosMsg>{env}</nfeDadosMsg></nfeRecepcaoEvento>'
        sem_wrap = f'<nfeDadosMsg xmlns="{wsdl_ns}">{env}</nfeDadosMsg>'

        def env12(inner: str) -> str:
            return ('<?xml version="1.0" encoding="UTF-8"?>'
                    '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
                    f'<soap12:Body>{inner}</soap12:Body></soap12:Envelope>')

        def env11(inner: str) -> str:
            return ('<?xml version="1.0" encoding="UTF-8"?>'
                    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                    f'<soap:Body>{inner}</soap:Body></soap:Envelope>')

        ct12 = f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION_EVENTO}"'
        casos = [
            ("1: soap1.2 action-no-CT (atual)", url_www, env12(wrap),
             {"Content-Type": ct12}),
            ("2: soap1.2 + SOAPAction header", url_www, env12(wrap),
             {"Content-Type": ct12, "SOAPAction": f'"{SOAP_ACTION_EVENTO}"'}),
            ("3: soap1.1 text/xml + SOAPAction", url_www, env11(wrap),
             {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{SOAP_ACTION_EVENTO}"'}),
            ("4: soap1.2 SEM wrapper (nfeDadosMsg direto)", url_www, env12(sem_wrap),
             {"Content-Type": ct12}),
            ("5: soap1.2 host www1", url_www1, env12(wrap),
             {"Content-Type": ct12}),
        ]

        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption())
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        cert_f = tempfile.NamedTemporaryFile(delete=False, suffix=".crt.pem")
        key_f = tempfile.NamedTemporaryFile(delete=False, suffix=".key.pem")
        out: list[dict] = []
        try:
            cert_f.write(cert_pem); cert_f.close()
            key_f.write(key_pem); key_f.close()
            for nome, url, envelope, headers in casos:
                try:
                    r = requests.post(url, data=envelope.encode("utf-8"), headers=headers,
                                      cert=(cert_f.name, key_f.name), timeout=self.timeout)
                    corpo = (r.text or "").strip()
                    out.append({
                        "variante": nome, "http": r.status_code,
                        "motivo": _extrair_fault(corpo) or corpo[:200] or "(vazio)",
                    })
                except Exception as exc:  # noqa: BLE001
                    out.append({"variante": nome, "http": "EXC", "motivo": str(exc)[:200]})
        finally:
            for f in (cert_f.name, key_f.name):
                try:
                    os.unlink(f)
                except OSError:
                    pass
        return out

    def _post_mtls(self, env_evento: bytes, key, cert) -> str:
        from cryptography.hazmat.primitives import serialization

        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        cert_f = tempfile.NamedTemporaryFile(delete=False, suffix=".crt.pem")
        key_f = tempfile.NamedTemporaryFile(delete=False, suffix=".key.pem")
        try:
            cert_f.write(cert_pem); cert_f.close()
            key_f.write(key_pem); key_f.close()
            # IMPORTANTE: o corpo leva <nfeDadosMsg> DIRETO (com o namespace do
            # WSDL), SEM o wrapper <nfeRecepcaoEvento>. Com o wrapper o AN
            # responde "action não reconhecida"; sem ele, processa (confirmado
            # pelo diagnóstico de variantes). É o oposto da Distribuição DFe.
            envelope = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
                '<soap12:Body>'
                '<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">'
                + env_evento.decode("utf-8") +
                '</nfeDadosMsg>'
                '</soap12:Body></soap12:Envelope>'
            )
            headers = {
                "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION_EVENTO}"',
            }
            resp = requests.post(
                self.url, data=envelope.encode("utf-8"), headers=headers,
                cert=(cert_f.name, key_f.name), timeout=self.timeout,
            )
            # NÃO usar raise_for_status cego: o .asmx da Receita devolve o motivo
            # real (SOAP Fault / Rejeição) DENTRO do corpo mesmo com HTTP 500.
            # Engolir isso = "500 Server Error" opaco. Capturamos o corpo.
            if resp.status_code >= 400:
                corpo = (resp.text or "").strip()
                motivo = _extrair_fault(corpo) or corpo[:600] or "(corpo vazio)"
                raise RuntimeError(f"HTTP {resp.status_code} NFeRecepcaoEvento4: {motivo}")
            return resp.text
        finally:
            for f in (cert_f.name, key_f.name):
                try:
                    os.unlink(f)
                except OSError:
                    pass

    @staticmethod
    def _parse_resposta(resp_xml: str) -> dict:
        root = etree.fromstring(resp_xml.encode("utf-8"))
        # cStat do lote e do evento (o do retEvento/infEvento é o que importa)
        def _find(tag: str) -> str | None:
            for e in root.iter():
                if _local(e.tag) == tag and e.text:
                    return e.text.strip()
            return None
        # pega o ÚLTIMO cStat (o do infEvento dentro do retEvento)
        cstats = [e.text for e in root.iter() if _local(e.tag) == "cStat" and e.text]
        motivos = [e.text for e in root.iter() if _local(e.tag) == "xMotivo" and e.text]
        cstat = cstats[-1] if cstats else "?"
        motivo = motivos[-1] if motivos else ""
        # 135/136 = registrado (vinculado/não vinculado); 573 = duplicidade (já manifestado)
        ok = cstat in ("135", "136", "573")
        return {
            "cstat": cstat,
            "motivo": motivo,
            "ok": ok,
            "protocolo": _find("nProt"),
        }
