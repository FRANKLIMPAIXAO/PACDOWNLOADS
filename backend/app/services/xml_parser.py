from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from xml.etree import ElementTree as ET


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _find_text(root: ET.Element, names: Iterable[str]) -> str | None:
    wanted = set(names)
    for elem in root.iter():
        if _local_name(elem.tag) in wanted and elem.text:
            return elem.text.strip()
    return None


def _findall_text(root: ET.Element, name: str) -> list[str]:
    values: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) == name and elem.text:
            values.append(elem.text.strip())
    return values


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except Exception:
        return None


class XMLParserService:
    def parse(self, tipo_documento: str, xml_content: str) -> dict:
        root = ET.fromstring(xml_content)
        tipo = tipo_documento.upper()
        if tipo == "NFE":
            return self.parse_nfe(root)
        if tipo == "CTE":
            return self.parse_cte(root)
        if tipo == "NFSE":
            return self.parse_nfse(root)
        raise ValueError(f"Tipo de documento nao suportado: {tipo_documento}")

    def parse_nfe(self, root: ET.Element) -> dict:
        chave = _find_text(root, {"chNFe"})
        if not chave:
            inf = next((elem for elem in root.iter() if _local_name(elem.tag) == "infNFe"), None)
            if inf is not None:
                raw = inf.attrib.get("Id", "")
                chave = raw.replace("NFe", "") if raw else None
        return {
            "chave_acesso": chave or "",
            "numero": _find_text(root, {"nNF"}),
            "serie": _find_text(root, {"serie"}),
            "data_emissao": _to_datetime(_find_text(root, {"dhEmi", "dEmi"})),
            "cnpj_emitente": _find_text(root, {"CNPJ"}),
            "nome_emitente": _find_text(root, {"xNome"}),
            "cnpj_destinatario": self._nth_value(root, "CNPJ", 1),
            "nome_destinatario": self._nth_value(root, "xNome", 1),
            "valor_total": _to_decimal(_find_text(root, {"vNF"})),
            "cfops": _findall_text(root, "CFOP"),
            # tpNF: "1"=saída (venda/remessa), "0"=entrada (nota de entrada
            # própria — compra de produtor rural, retorno de industrialização).
            # Distingue faturamento real de nota que a empresa EMITE mas é compra.
            "tipo_nf": _find_text(root, {"tpNF"}),
        }

    def parse_cte(self, root: ET.Element) -> dict:
        chave = _find_text(root, {"chCTe"})
        if not chave:
            inf = next((elem for elem in root.iter() if _local_name(elem.tag) == "infCte"), None)
            if inf is not None:
                raw = inf.attrib.get("Id", "")
                chave = raw.replace("CTe", "") if raw else None
        return {
            "chave_acesso": chave or "",
            "numero": _find_text(root, {"nCT"}),
            "serie": _find_text(root, {"serie"}),
            "data_emissao": _to_datetime(_find_text(root, {"dhEmi"})),
            "cnpj_emitente": _find_text(root, {"CNPJ"}),
            "nome_emitente": _find_text(root, {"xNome"}),
            "cnpj_destinatario": self._nth_value(root, "CNPJ", 1),
            "nome_destinatario": self._nth_value(root, "xNome", 1),
            "valor_total": _to_decimal(_find_text(root, {"vTPrest", "vRec"})),
        }

    def parse_nfse(self, root: ET.Element) -> dict:
        return {
            "chave_acesso": _find_text(root, {"CodigoVerificacao", "Numero"}) or "",
            "numero": _find_text(root, {"Numero"}),
            "serie": _find_text(root, {"Serie"}),
            "data_emissao": _to_datetime(_find_text(root, {"DataEmissao"})),
            "cnpj_emitente": _find_text(root, {"Cnpj"}),
            "nome_emitente": _find_text(root, {"RazaoSocial"}),
            "cnpj_destinatario": self._nth_value(root, "Cnpj", 1),
            "nome_destinatario": self._nth_value(root, "RazaoSocial", 1),
            "valor_total": _to_decimal(_find_text(root, {"ValorServicos"})),
            "valor_iss": _to_decimal(_find_text(root, {"ValorIss"})),
            "municipio": _find_text(root, {"CodigoMunicipio"}),
            "codigo_servico": _find_text(root, {"ItemListaServico"}),
        }

    def _nth_value(self, root: ET.Element, tag_name: str, index: int) -> str | None:
        values = [elem.text.strip() for elem in root.iter() if _local_name(elem.tag) == tag_name and elem.text]
        return values[index] if len(values) > index else None
