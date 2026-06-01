"""Classificacao de CFOPs para o motor de apuracao.

Cada CFOP eh classificado em:
- direcao: ENTRADA (1xxx, 2xxx, 3xxx) ou SAIDA (5xxx, 6xxx, 7xxx)
- natureza: VENDA | VENDA_ST | EXPORTACAO | DEVOLUCAO_VENDA | DEVOLUCAO_COMPRA |
            COMPRA | REMESSA_NAO_RECEITA | TRANSFERENCIA | OUTRO
- afeta_receita: int em {+1, -1, 0}
    +1 = soma na receita bruta (vendas, exportacoes)
    -1 = subtrai (devolucoes de venda — feitas como ENTRADA com CFOP 1xxx/2xxx)
     0 = nao entra na receita (compras, remessas, transferencias, devolucao de compra)

Fonte: tabela oficial CFOP (Convenio S/N de 1970, atualizada pelos
Convenios SINIEF). Mapeamento focado nos CFOPs mais usados por
varejo/industria/servico em geral. CFOPs nao mapeados caem em "OUTRO"
com `afeta_receita=0` por seguranca.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Natureza = Literal[
    "VENDA",
    "VENDA_ST",
    "EXPORTACAO",
    "DEVOLUCAO_VENDA",
    "DEVOLUCAO_COMPRA",
    "COMPRA",
    "REMESSA_NAO_RECEITA",
    "TRANSFERENCIA",
    "OUTRO",
]


@dataclass(frozen=True, slots=True)
class CfopInfo:
    cfop: str
    direcao: Literal["ENTRADA", "SAIDA"]
    natureza: Natureza
    afeta_receita: int  # +1, -1 ou 0
    descricao: str


# --- SAIDAS (5xxx interno, 6xxx interestadual, 7xxx exterior) ---

_SAIDAS: list[CfopInfo] = [
    # Vendas comuns (industria/comercio)
    CfopInfo("5101", "SAIDA", "VENDA",       +1, "Venda de producao propria"),
    CfopInfo("5102", "SAIDA", "VENDA",       +1, "Venda de mercadoria adquirida"),
    CfopInfo("5103", "SAIDA", "VENDA",       +1, "Venda de producao em consignacao"),
    CfopInfo("5104", "SAIDA", "VENDA",       +1, "Venda de mercadoria em consignacao"),
    CfopInfo("5109", "SAIDA", "VENDA",       +1, "Venda Zona Franca Manaus"),
    CfopInfo("5110", "SAIDA", "VENDA",       +1, "Venda Zona Franca - mercadoria adquirida"),
    CfopInfo("5111", "SAIDA", "VENDA",       +1, "Venda producao - estabelecimento equiparado"),
    CfopInfo("5112", "SAIDA", "VENDA",       +1, "Venda mercadoria - estabelecimento equiparado"),
    CfopInfo("5113", "SAIDA", "VENDA",       +1, "Venda producao - feira/exposicao"),
    CfopInfo("5114", "SAIDA", "VENDA",       +1, "Venda mercadoria - feira/exposicao"),
    CfopInfo("5115", "SAIDA", "VENDA",       +1, "Venda mercadoria - mostruario"),
    CfopInfo("5116", "SAIDA", "VENDA",       +1, "Venda producao - venda futura"),
    CfopInfo("5117", "SAIDA", "VENDA",       +1, "Venda mercadoria - venda futura"),
    CfopInfo("5118", "SAIDA", "VENDA",       +1, "Venda producao - entrega futura"),
    CfopInfo("5119", "SAIDA", "VENDA",       +1, "Venda mercadoria - entrega futura"),
    CfopInfo("5120", "SAIDA", "VENDA",       +1, "Venda mercadoria - venda direta"),
    # Interestadual
    CfopInfo("6101", "SAIDA", "VENDA",       +1, "Venda producao interestadual"),
    CfopInfo("6102", "SAIDA", "VENDA",       +1, "Venda mercadoria interestadual"),
    CfopInfo("6107", "SAIDA", "VENDA",       +1, "Venda nao contribuinte interestadual"),
    CfopInfo("6108", "SAIDA", "VENDA",       +1, "Venda nao contribuinte (mercadoria) interestadual"),
    CfopInfo("6109", "SAIDA", "VENDA",       +1, "Venda Zona Franca interestadual"),
    CfopInfo("6110", "SAIDA", "VENDA",       +1, "Venda Zona Franca mercadoria interestadual"),
    CfopInfo("6111", "SAIDA", "VENDA",       +1, "Venda producao - equiparado interestadual"),
    CfopInfo("6112", "SAIDA", "VENDA",       +1, "Venda mercadoria - equiparado interestadual"),
    CfopInfo("6116", "SAIDA", "VENDA",       +1, "Venda futura interestadual"),
    CfopInfo("6117", "SAIDA", "VENDA",       +1, "Venda futura mercadoria interestadual"),
    CfopInfo("6118", "SAIDA", "VENDA",       +1, "Entrega futura producao interestadual"),
    CfopInfo("6119", "SAIDA", "VENDA",       +1, "Entrega futura mercadoria interestadual"),
    CfopInfo("6120", "SAIDA", "VENDA",       +1, "Venda direta interestadual"),

    # Vendas com Substituicao Tributaria
    CfopInfo("5401", "SAIDA", "VENDA_ST",    +1, "Venda com ST - substituto produtor"),
    CfopInfo("5402", "SAIDA", "VENDA_ST",    +1, "Venda com ST - substituto adquirente"),
    CfopInfo("5403", "SAIDA", "VENDA_ST",    +1, "Venda com ST - substituto"),
    CfopInfo("5405", "SAIDA", "VENDA_ST",    +1, "Venda com ST - substituido"),
    CfopInfo("5408", "SAIDA", "VENDA_ST",    +1, "Venda com ST - producao Zona Franca"),
    CfopInfo("5409", "SAIDA", "VENDA_ST",    +1, "Venda com ST - mercadoria Zona Franca"),
    CfopInfo("5410", "SAIDA", "VENDA_ST",    +1, "Venda com ST - producao industrial"),
    CfopInfo("5411", "SAIDA", "VENDA_ST",    +1, "Venda com ST - mercadoria adquirida"),
    CfopInfo("5412", "SAIDA", "VENDA_ST",    +1, "Venda com ST - producao - imune"),
    CfopInfo("5413", "SAIDA", "VENDA_ST",    +1, "Venda com ST - mercadoria - imune"),
    CfopInfo("6401", "SAIDA", "VENDA_ST",    +1, "Venda com ST - substituto interestadual"),
    CfopInfo("6402", "SAIDA", "VENDA_ST",    +1, "Venda com ST - adquirente interestadual"),
    CfopInfo("6403", "SAIDA", "VENDA_ST",    +1, "Venda com ST interestadual"),
    CfopInfo("6404", "SAIDA", "VENDA_ST",    +1, "Venda com ST - inducao interestadual"),
    CfopInfo("6408", "SAIDA", "VENDA_ST",    +1, "Venda com ST Zona Franca interestadual"),
    CfopInfo("6409", "SAIDA", "VENDA_ST",    +1, "Venda com ST mercadoria ZFM interestadual"),
    CfopInfo("6410", "SAIDA", "VENDA_ST",    +1, "Venda com ST producao industrial interestadual"),
    CfopInfo("6411", "SAIDA", "VENDA_ST",    +1, "Venda com ST mercadoria interestadual"),

    # Exportacao
    CfopInfo("7101", "SAIDA", "EXPORTACAO",  +1, "Exportacao - producao"),
    CfopInfo("7102", "SAIDA", "EXPORTACAO",  +1, "Exportacao - mercadoria adquirida"),
    CfopInfo("7105", "SAIDA", "EXPORTACAO",  +1, "Exportacao - producao Zona Franca"),
    CfopInfo("7106", "SAIDA", "EXPORTACAO",  +1, "Exportacao - mercadoria Zona Franca"),

    # Devolucao de COMPRA (saida) — nao afeta receita bruta
    CfopInfo("5201", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao de compra - producao"),
    CfopInfo("5202", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao de compra - mercadoria"),
    CfopInfo("5210", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao de compra com ST"),
    CfopInfo("5410", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao de compra com ST industrial"),
    CfopInfo("5411", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao de compra com ST mercadoria"),
    CfopInfo("6201", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao compra producao interestadual"),
    CfopInfo("6202", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao compra mercadoria interestadual"),
    CfopInfo("6210", "SAIDA", "DEVOLUCAO_COMPRA", 0, "Devolucao compra com ST interestadual"),

    # Remessas / nao geram receita
    CfopInfo("5901", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa para industrializacao"),
    CfopInfo("5902", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Retorno de industrializacao"),
    CfopInfo("5903", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Retorno de mercadoria recebida para industrializacao"),
    CfopInfo("5904", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa para venda fora do estabelecimento"),
    CfopInfo("5905", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa para deposito fechado/armazem geral"),
    CfopInfo("5906", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Retorno de deposito fechado/armazem geral"),
    CfopInfo("5908", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa em comodato"),
    CfopInfo("5909", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Retorno de comodato"),
    CfopInfo("5910", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa em bonificacao/brinde"),
    CfopInfo("5912", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa para conserto/reparo"),
    CfopInfo("5915", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa para conserto/reparo"),
    CfopInfo("5916", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Retorno de conserto/reparo"),
    CfopInfo("5917", "SAIDA", "REMESSA_NAO_RECEITA", 0, "Remessa em conta de ordem - terceiro"),
    CfopInfo("5949", "SAIDA", "OUTRO",          0, "Outras saidas"),

    # Transferencias entre estabelecimentos do mesmo titular
    CfopInfo("5151", "SAIDA", "TRANSFERENCIA",  0, "Transferencia de producao"),
    CfopInfo("5152", "SAIDA", "TRANSFERENCIA",  0, "Transferencia de mercadoria"),
    CfopInfo("6151", "SAIDA", "TRANSFERENCIA",  0, "Transferencia de producao interestadual"),
    CfopInfo("6152", "SAIDA", "TRANSFERENCIA",  0, "Transferencia de mercadoria interestadual"),
]


# --- ENTRADAS (1xxx interno, 2xxx interestadual, 3xxx exterior) ---

_ENTRADAS: list[CfopInfo] = [
    # Compras (nao afetam receita)
    CfopInfo("1101", "ENTRADA", "COMPRA",   0, "Compra para industrializacao"),
    CfopInfo("1102", "ENTRADA", "COMPRA",   0, "Compra para revenda"),
    CfopInfo("1111", "ENTRADA", "COMPRA",   0, "Compra para industrializacao - estabelecimento equiparado"),
    CfopInfo("1113", "ENTRADA", "COMPRA",   0, "Compra mercadoria - feira/exposicao"),
    CfopInfo("1116", "ENTRADA", "COMPRA",   0, "Compra para industrializacao - venda futura"),
    CfopInfo("1117", "ENTRADA", "COMPRA",   0, "Compra para revenda - venda futura"),
    CfopInfo("1118", "ENTRADA", "COMPRA",   0, "Entrada futura producao"),
    CfopInfo("1119", "ENTRADA", "COMPRA",   0, "Entrada futura revenda"),
    CfopInfo("1120", "ENTRADA", "COMPRA",   0, "Compra venda direta"),
    CfopInfo("1124", "ENTRADA", "COMPRA",   0, "Industrializacao por encomenda"),
    CfopInfo("1125", "ENTRADA", "COMPRA",   0, "Industrializacao por encomenda equiparado"),
    CfopInfo("2101", "ENTRADA", "COMPRA",   0, "Compra industrializacao interestadual"),
    CfopInfo("2102", "ENTRADA", "COMPRA",   0, "Compra revenda interestadual"),
    CfopInfo("2111", "ENTRADA", "COMPRA",   0, "Compra industrializacao - equiparado interestadual"),
    CfopInfo("2113", "ENTRADA", "COMPRA",   0, "Compra mercadoria feira interestadual"),
    CfopInfo("2116", "ENTRADA", "COMPRA",   0, "Compra futura industrializacao interestadual"),
    CfopInfo("2117", "ENTRADA", "COMPRA",   0, "Compra futura revenda interestadual"),
    CfopInfo("2120", "ENTRADA", "COMPRA",   0, "Compra venda direta interestadual"),
    CfopInfo("2124", "ENTRADA", "COMPRA",   0, "Industrializacao por encomenda interestadual"),

    # Compra com ST
    CfopInfo("1401", "ENTRADA", "COMPRA",   0, "Compra industrializacao com ST"),
    CfopInfo("1403", "ENTRADA", "COMPRA",   0, "Compra revenda com ST"),
    CfopInfo("1407", "ENTRADA", "COMPRA",   0, "Compra mercadoria com ST nao contribuinte"),
    CfopInfo("1408", "ENTRADA", "COMPRA",   0, "Compra industrializacao ZFM com ST"),
    CfopInfo("1409", "ENTRADA", "COMPRA",   0, "Compra revenda ZFM com ST"),
    CfopInfo("2401", "ENTRADA", "COMPRA",   0, "Compra industrializacao com ST interestadual"),
    CfopInfo("2403", "ENTRADA", "COMPRA",   0, "Compra revenda com ST interestadual"),
    CfopInfo("2407", "ENTRADA", "COMPRA",   0, "Compra mercadoria com ST nao contrib. interestadual"),

    # *** DEVOLUCAO DE VENDA *** (entram como entrada e SUBTRAEM da receita)
    CfopInfo("1201", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao de venda de producao propria"),
    CfopInfo("1202", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao de venda de mercadoria adquirida"),
    CfopInfo("1203", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao de venda - producao em consignacao"),
    CfopInfo("1204", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao de venda - mercadoria em consignacao"),
    CfopInfo("1208", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda producao Zona Franca"),
    CfopInfo("1209", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda mercadoria Zona Franca"),
    CfopInfo("1410", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda com ST - producao industrial"),
    CfopInfo("1411", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda com ST - mercadoria"),
    CfopInfo("1503", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Retorno de mercadoria - producao em consignacao"),
    CfopInfo("1504", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Retorno - mercadoria em consignacao"),
    CfopInfo("1553", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda imobilizado"),
    CfopInfo("1660", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda - simples remessa"),
    CfopInfo("1661", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda mercadoria"),
    CfopInfo("1662", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda - producao com remessa"),
    CfopInfo("2201", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda producao interestadual"),
    CfopInfo("2202", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda mercadoria interestadual"),
    CfopInfo("2208", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda Zona Franca interestadual"),
    CfopInfo("2209", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda mercadoria ZFM interestadual"),
    CfopInfo("2410", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda com ST industrial interestadual"),
    CfopInfo("2411", "ENTRADA", "DEVOLUCAO_VENDA", -1, "Devolucao venda com ST mercadoria interestadual"),

    # Remessas de entrada (nao afetam receita)
    CfopInfo("1901", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Entrada para industrializacao por encomenda"),
    CfopInfo("1902", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Retorno de industrializacao por encomenda"),
    CfopInfo("1908", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Entrada de bem por comodato"),
    CfopInfo("1909", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Retorno de bem por comodato"),
    CfopInfo("1910", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Entrada de bonificacao/brinde"),
    CfopInfo("1915", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Entrada para conserto/reparo"),
    CfopInfo("1916", "ENTRADA", "REMESSA_NAO_RECEITA", 0, "Retorno de conserto/reparo"),
    CfopInfo("1949", "ENTRADA", "OUTRO",          0, "Outras entradas"),

    # Transferencias de entrada
    CfopInfo("1151", "ENTRADA", "TRANSFERENCIA",  0, "Transferencia recebida de producao"),
    CfopInfo("1152", "ENTRADA", "TRANSFERENCIA",  0, "Transferencia recebida de mercadoria"),
    CfopInfo("2151", "ENTRADA", "TRANSFERENCIA",  0, "Transferencia recebida de producao interestadual"),
    CfopInfo("2152", "ENTRADA", "TRANSFERENCIA",  0, "Transferencia recebida de mercadoria interestadual"),

    # Imobilizado / uso e consumo (nao afetam receita)
    CfopInfo("1551", "ENTRADA", "COMPRA",   0, "Compra de bem imobilizado"),
    CfopInfo("1552", "ENTRADA", "COMPRA",   0, "Transferencia bem imobilizado"),
    CfopInfo("1556", "ENTRADA", "COMPRA",   0, "Compra material uso/consumo"),
    CfopInfo("2551", "ENTRADA", "COMPRA",   0, "Compra bem imobilizado interestadual"),
    CfopInfo("2552", "ENTRADA", "COMPRA",   0, "Transferencia bem imobilizado interestadual"),
    CfopInfo("2556", "ENTRADA", "COMPRA",   0, "Compra material uso/consumo interestadual"),
]


# Indice por CFOP (string de 4 digitos)
_INDEX: dict[str, CfopInfo] = {info.cfop: info for info in (_SAIDAS + _ENTRADAS)}


def classificar_cfop(cfop: str | None) -> CfopInfo:
    """Retorna a classificacao do CFOP. CFOP nao mapeado vira "OUTRO" com afeta_receita=0."""
    if not cfop:
        return CfopInfo("0000", "SAIDA", "OUTRO", 0, "CFOP ausente")
    cfop = cfop.strip().replace(".", "")
    info = _INDEX.get(cfop)
    if info:
        return info
    # Fallback por prefixo
    if cfop.startswith(("1", "2", "3")):
        direcao = "ENTRADA"
    else:
        direcao = "SAIDA"
    return CfopInfo(cfop, direcao, "OUTRO", 0, f"CFOP {cfop} nao mapeado")


# CSOSN com Substituicao Tributaria (Simples Nacional)
CSOSN_COM_ST = {"201", "202", "203", "500"}

# CST com Substituicao Tributaria (Lucro Presumido/Real)
CST_COM_ST = {"10", "30", "60", "70"}


def tem_substituicao_tributaria(csosn: str | None, cst: str | None) -> bool:
    """Determina se o item tem ICMS por substituicao tributaria."""
    if csosn and csosn.strip() in CSOSN_COM_ST:
        return True
    if cst and cst.strip() in CST_COM_ST:
        return True
    return False
