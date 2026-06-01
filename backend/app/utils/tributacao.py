"""Classificacao tributaria de itens de NFe.

Responsabilidades:
- Detectar **tributacao monofasica/concentrada** de PIS/COFINS por CST e/ou NCM:
    Combustiveis (Lei 9.718/98), Medicamentos+Cosmeticos (Lei 10.147/00),
    Veiculos+Autopecas+Pneus (Lei 10.485/02), Bebidas frias (Lei 10.833 e 10.865).
- Detectar **isencao/aliquota zero** (CST 06, 07, 08, 09).
- Detectar **substituicao tributaria** (CSOSN/CST ICMS).

Empresas do Simples Nacional que **revendem** mercadorias monofasicas ou tributadas
por ST devem segregar essa receita no PGDAS-D para o sistema RECALCULAR o DAS
removendo os tributos ja cobrados na cadeia anterior:
- Monofasico: zera PIS e COFINS sobre a parcela
- ST (substituido): zera ICMS sobre a parcela
- Exportacao: zera PIS, COFINS, IPI, ICMS, ISS

Ref: Resolucao CGSN 140/2018 art. 25.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TipoTributacao = Literal[
    "NORMAL",          # tributacao cheia
    "MONOFASICO",      # PIS/COFINS ja recolhido na cadeia (revenda)
    "ST",              # ICMS por substituicao tributaria (substituido)
    "MONOFASICO_ST",   # ambos
    "ISENTA",          # CST 06/07/08/09 (sem incidencia)
    "EXPORTACAO",      # CFOP 7xxx
]


# CST PIS/COFINS = 04 → "Operacao Tributavel Monofasica - Revenda a Aliquota Zero"
# Comerciante revendendo produto monofasico nao paga PIS/COFINS.
CST_PIS_COFINS_MONOFASICO = {"04", "5"}

# CST PIS/COFINS = 06 → "Operacao Tributavel a Aliquota Zero"
# CST PIS/COFINS = 07 → "Operacao Isenta da Contribuicao"
# CST PIS/COFINS = 08 → "Operacao Sem Incidencia da Contribuicao"
# CST PIS/COFINS = 09 → "Operacao com Suspensao da Contribuicao"
CST_PIS_COFINS_ZERO = {"06", "07", "08", "09"}

# CSOSN com ICMS ja recolhido por ST (substituido)
CSOSN_ST = {"201", "202", "203", "500"}

# CST ICMS com ST
CST_ICMS_ST = {"10", "30", "60", "70"}


# ============================================================
#  NCMs MONOFASICOS (lista resumida — ampliavel)
# ============================================================
# Em produção, isso vira tabela no banco para o usuario customizar.
# Aqui, prefixos NCM mais comuns por categoria (4 ou 8 digitos).

# Combustiveis (Lei 9.718/98 art. 4-6)
NCM_COMBUSTIVEIS_PREFIXOS = {
    "2710",  # gasolina, oleo diesel, querosene, lubrificantes
    "2711",  # GLP, gas natural
    "2207",  # alcool etilico (combustivel)
    "2905",  # alcoois aciclicos (anidro/hidratado)
}

# Medicamentos, perfumaria, cosmeticos (Lei 10.147/00 art. 1-3)
NCM_MEDICAMENTOS_COSMETICOS_PREFIXOS = {
    "3001", "3002", "3003", "3004", "3005", "3006",  # produtos farmaceuticos
    "3303", "3304", "3305", "3306", "3307",          # perfumaria, cosmeticos
    "9603.21",                                        # escovas dentais
    "3401",                                           # sabonetes (alguns)
}

# Veiculos, autopecas, pneus (Lei 10.485/02 art. 1-5)
NCM_VEICULOS_AUTOPECAS_PNEUS_PREFIXOS = {
    "8701", "8702", "8703", "8704", "8705", "8706",  # veiculos
    "8707", "8708",                                   # carrocerias, autopecas
    "4011", "4012", "4013",                           # pneus, cameras
    "8714.10", "8714.20", "8714.91", "8714.99",       # partes motocicletas
    "4016.99.90",                                     # outras pecas borracha
}

# Bebidas frias (cervejas, refrigerantes, agua, isotonicos) — Lei 10.833 + 10.865
NCM_BEBIDAS_FRIAS_PREFIXOS = {
    "2201", "2202", "2203", "2204", "2205", "2206", "2208",
}

# Cigarros e fumo (Lei 9.532/97 art. 53; Lei 10.865 art. 5)
NCM_CIGARROS_PREFIXOS = {
    "2402", "2403",
}


_TODOS_NCMS_MONOFASICOS = (
    NCM_COMBUSTIVEIS_PREFIXOS
    | NCM_MEDICAMENTOS_COSMETICOS_PREFIXOS
    | NCM_VEICULOS_AUTOPECAS_PNEUS_PREFIXOS
    | NCM_BEBIDAS_FRIAS_PREFIXOS
    | NCM_CIGARROS_PREFIXOS
)


def categoria_monofasica(ncm: str | None) -> str | None:
    """Retorna a categoria do NCM se for monofasico, ou None."""
    if not ncm:
        return None
    n = ncm.replace(".", "").strip()
    # Normaliza para comparar com prefixos
    for prefixo in NCM_COMBUSTIVEIS_PREFIXOS:
        p = prefixo.replace(".", "")
        if n.startswith(p):
            return "COMBUSTIVEL"
    for prefixo in NCM_MEDICAMENTOS_COSMETICOS_PREFIXOS:
        p = prefixo.replace(".", "")
        if n.startswith(p):
            return "MEDICAMENTO_COSMETICO"
    for prefixo in NCM_VEICULOS_AUTOPECAS_PNEUS_PREFIXOS:
        p = prefixo.replace(".", "")
        if n.startswith(p):
            return "VEICULO_AUTOPECA_PNEU"
    for prefixo in NCM_BEBIDAS_FRIAS_PREFIXOS:
        p = prefixo.replace(".", "")
        if n.startswith(p):
            return "BEBIDA_FRIA"
    for prefixo in NCM_CIGARROS_PREFIXOS:
        p = prefixo.replace(".", "")
        if n.startswith(p):
            return "CIGARRO"
    return None


def is_monofasico(cst_pis: str | None, cst_cofins: str | None, ncm: str | None) -> bool:
    """True se o item se enquadra em tributacao monofasica de PIS/COFINS."""
    if cst_pis and cst_pis.strip() in CST_PIS_COFINS_MONOFASICO:
        return True
    if cst_cofins and cst_cofins.strip() in CST_PIS_COFINS_MONOFASICO:
        return True
    # Fallback por NCM (caso o XML nao tenha CST PIS preenchido corretamente)
    if categoria_monofasica(ncm):
        return True
    return False


def is_pis_cofins_zero(cst_pis: str | None, cst_cofins: str | None) -> bool:
    """True se PIS/COFINS estao zerados por isencao/suspensao (CST 06-09)."""
    if cst_pis and cst_pis.strip() in CST_PIS_COFINS_ZERO:
        return True
    if cst_cofins and cst_cofins.strip() in CST_PIS_COFINS_ZERO:
        return True
    return False


def is_icms_st(csosn: str | None, cst: str | None) -> bool:
    """True se ICMS ja foi recolhido por substituicao tributaria."""
    if csosn and csosn.strip() in CSOSN_ST:
        return True
    if cst and cst.strip() in CST_ICMS_ST:
        return True
    return False


@dataclass(frozen=True, slots=True)
class ClassificacaoItem:
    """Resultado da analise tributaria de um item de NFe."""
    monofasico: bool
    monofasico_categoria: str | None  # COMBUSTIVEL, MEDICAMENTO_COSMETICO, ...
    icms_st: bool
    pis_cofins_zero: bool

    @property
    def tipo(self) -> TipoTributacao:
        if self.monofasico and self.icms_st:
            return "MONOFASICO_ST"
        if self.monofasico:
            return "MONOFASICO"
        if self.icms_st:
            return "ST"
        if self.pis_cofins_zero:
            return "ISENTA"
        return "NORMAL"


def classificar_item(
    *,
    csosn_icms: str | None,
    cst_icms: str | None,
    cst_pis: str | None,
    cst_cofins: str | None,
    ncm: str | None,
) -> ClassificacaoItem:
    return ClassificacaoItem(
        monofasico=is_monofasico(cst_pis, cst_cofins, ncm),
        monofasico_categoria=categoria_monofasica(ncm),
        icms_st=is_icms_st(csosn_icms, cst_icms),
        pis_cofins_zero=is_pis_cofins_zero(cst_pis, cst_cofins),
    )
