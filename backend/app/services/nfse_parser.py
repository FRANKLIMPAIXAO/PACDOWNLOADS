"""Parsing mínimo do XML da NFS-e (padrão nacional ADN + fallback ABRASF 2.04).

Extrai só o necessário pra popular o DocumentoFiscal (chave, prestador, tomador,
valores, datas). Funções puras, sem dependência externa (xml.etree).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _find(node, nome: str):
    """Primeiro elemento (em profundidade) cujo nome local == nome."""
    if node is None:
        return None
    for e in node.iter():
        if _local(e.tag) == nome:
            return e
    return None


def _txt(node, nome: str) -> str | None:
    el = _find(node, nome)
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def _digitos(s: str | None) -> str | None:
    if not s:
        return None
    d = re.sub(r"\D", "", s)
    return d or None


def _dec(s: str | None) -> Decimal | None:
    if not s:
        return None
    try:
        return Decimal(str(s).replace(".", "").replace(",", ".")) if "," in str(s) else Decimal(str(s))
    except (InvalidOperation, ValueError):
        return None


def parse_nfse(xml: str) -> dict:
    """Extrai meta da NFS-e. Para evento, devolve {'tipo_raiz': 'evento', ...}."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return {"_erro": f"parse XML: {exc}"}

    eh_evento = _find(root, "infEvento") is not None or _find(root, "evento") is not None
    if eh_evento:
        return {
            "tipo_raiz": "evento",
            "chave_acesso": _txt(root, "chNFSe"),
            "dh_emissao": _txt(root, "dhEvento") or _txt(root, "dhProc"),
            "tipo_evento": _txt(root, "cMotivo"),
            "motivo_evento": _txt(root, "xMotivo") or _txt(root, "xDesc"),
        }

    # Chave (50 dígitos): tag chNFSe ou no Id do infNFSe
    chave = _txt(root, "chNFSe")
    if not chave:
        inf = _find(root, "infNFSe")
        if inf is not None:
            idv = inf.attrib.get("Id") or inf.attrib.get("id") or ""
            m = re.search(r"(\d{40,})$", idv)
            if m:
                chave = m.group(1)

    inf_dps = _find(root, "infDPS") or _find(root, "DPS") or root
    inf_nfse = _find(root, "infNFSe") or root

    numero = _txt(inf_nfse, "nNFSe") or _txt(root, "Numero")
    serie = _txt(inf_dps, "serie") or _txt(root, "Serie")
    dh_emissao = _txt(inf_dps, "dhEmi") or _txt(root, "DataEmissao") or _txt(root, "Competencia")

    # Prestador (emitente) — nacional usa <prest>/<emit>; ABRASF usa <Prestador>
    prest = _find(inf_dps, "prest") or _find(root, "prestador")
    emit = _find(inf_nfse, "emit") or _find(root, "emitente")
    prest_abrasf = _find(root, "PrestadorServico") or _find(root, "Prestador")
    cnpj_prestador = (
        _digitos(_txt(prest, "CNPJ")) or _digitos(_txt(emit, "CNPJ"))
        or _digitos(_txt(prest, "CPF")) or _digitos(_txt(emit, "CPF"))
        or _digitos(_txt(prest_abrasf, "Cnpj")) or _digitos(_txt(prest_abrasf, "Cpf"))
    )
    nome_prestador = (
        _txt(emit, "xNome") or _txt(prest, "xNome") or _txt(prest_abrasf, "RazaoSocial")
    )

    # Tomador (destinatário)
    toma = _find(inf_dps, "toma") or _find(root, "tomador") or _find(root, "dest")
    toma_abrasf = _find(root, "TomadorServico")
    cnpj_tomador = (
        _digitos(_txt(toma, "CNPJ")) or _digitos(_txt(toma_abrasf, "Cnpj"))
        or _digitos(_txt(toma, "CPF")) or _digitos(_txt(toma_abrasf, "Cpf"))
    )
    nome_tomador = _txt(toma, "xNome") or _txt(toma_abrasf, "RazaoSocial")

    valor_servico = (
        _dec(_txt(inf_dps, "vServ")) or _dec(_txt(root, "ValorServicos"))
    )
    valor_liquido = (
        _dec(_txt(inf_nfse, "vLiq")) or _dec(_txt(inf_dps, "vLiq"))
        or _dec(_txt(root, "ValorLiquidoNfse"))
    )

    return {
        "tipo_raiz": "nfse",
        "chave_acesso": chave,
        "numero": numero,
        "serie": serie,
        "dh_emissao": dh_emissao,
        "cnpj_prestador": cnpj_prestador,
        "nome_prestador": nome_prestador,
        "cnpj_tomador": cnpj_tomador,
        "nome_tomador": nome_tomador,
        "valor_servico": valor_servico,
        "valor_liquido": valor_liquido,
    }
