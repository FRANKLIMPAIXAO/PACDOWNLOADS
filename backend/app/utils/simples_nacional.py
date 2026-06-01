"""Tabela de aliquotas do Simples Nacional (LC 123/2006 + LC 155/2016).

Cada anexo tem 6 faixas. Calculo da aliquota efetiva:

    aliquota_efetiva = (rbt12 * aliquota_nominal - parcela_deduzir) / rbt12

Onde rbt12 = receita bruta acumulada nos 12 meses anteriores.

Para o primeiro mes em atividade, usa-se a media: rbt12 = receita_mes * 12.

Ref: https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/regimes-e-controles-especiais/simples-nacional
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


Anexo = Literal["I", "II", "III", "IV", "V"]


@dataclass(frozen=True, slots=True)
class FaixaSimples:
    faixa: int                  # 1..6
    teto: Decimal               # teto da faixa em RBT12
    aliquota_nominal: Decimal   # em %
    parcela_deduzir: Decimal    # em R$
    repartidos: dict[str, Decimal]  # IRPJ, CSLL, COFINS, PIS, CPP, ICMS, ISS — soma 100%


def _D(v: float | str) -> Decimal:
    return Decimal(str(v))


# --- ANEXO I: COMERCIO ---
ANEXO_I: list[FaixaSimples] = [
    FaixaSimples(1, _D(180_000),    _D(4.00),  _D(0),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(12.74), "PIS": _D(2.76), "CPP": _D(41.5), "ICMS": _D(34.0)}),
    FaixaSimples(2, _D(360_000),    _D(7.30),  _D(5_940),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(12.74), "PIS": _D(2.76), "CPP": _D(41.5), "ICMS": _D(34.0)}),
    FaixaSimples(3, _D(720_000),    _D(9.50),  _D(13_860),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(12.74), "PIS": _D(2.76), "CPP": _D(42.0), "ICMS": _D(33.5)}),
    FaixaSimples(4, _D(1_800_000),  _D(10.70), _D(22_500),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(12.74), "PIS": _D(2.76), "CPP": _D(42.0), "ICMS": _D(33.5)}),
    FaixaSimples(5, _D(3_600_000),  _D(14.30), _D(87_300),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(12.74), "PIS": _D(2.76), "CPP": _D(42.0), "ICMS": _D(33.5)}),
    FaixaSimples(6, _D(4_800_000),  _D(19.00), _D(378_000),
        {"IRPJ": _D(13.5), "CSLL": _D(10.0), "COFINS": _D(28.27), "PIS": _D(6.13), "CPP": _D(42.1), "ICMS": _D(0)}),
]

# --- ANEXO II: INDUSTRIA ---
ANEXO_II: list[FaixaSimples] = [
    FaixaSimples(1, _D(180_000),    _D(4.50),  _D(0),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(11.51), "PIS": _D(2.49), "CPP": _D(37.5), "ICMS": _D(32.0), "IPI": _D(7.5)}),
    FaixaSimples(2, _D(360_000),    _D(7.80),  _D(5_940),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(11.51), "PIS": _D(2.49), "CPP": _D(37.5), "ICMS": _D(32.0), "IPI": _D(7.5)}),
    FaixaSimples(3, _D(720_000),    _D(10.00), _D(13_860),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(11.51), "PIS": _D(2.49), "CPP": _D(37.5), "ICMS": _D(32.0), "IPI": _D(7.5)}),
    FaixaSimples(4, _D(1_800_000),  _D(11.20), _D(22_500),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(11.51), "PIS": _D(2.49), "CPP": _D(37.5), "ICMS": _D(32.0), "IPI": _D(7.5)}),
    FaixaSimples(5, _D(3_600_000),  _D(14.70), _D(85_500),
        {"IRPJ": _D(5.5), "CSLL": _D(3.5), "COFINS": _D(11.51), "PIS": _D(2.49), "CPP": _D(37.5), "ICMS": _D(32.0), "IPI": _D(7.5)}),
    FaixaSimples(6, _D(4_800_000),  _D(30.00), _D(720_000),
        {"IRPJ": _D(8.5), "CSLL": _D(7.5), "COFINS": _D(20.96), "PIS": _D(4.54), "CPP": _D(23.5), "ICMS": _D(0), "IPI": _D(35.0)}),
]

# --- ANEXO III: SERVICOS (escolas, agencias, salao etc.) ---
ANEXO_III: list[FaixaSimples] = [
    FaixaSimples(1, _D(180_000),    _D(6.00),  _D(0),
        {"IRPJ": _D(4.0), "CSLL": _D(3.5), "COFINS": _D(12.82), "PIS": _D(2.78), "CPP": _D(43.4), "ISS": _D(33.5)}),
    FaixaSimples(2, _D(360_000),    _D(11.20), _D(9_360),
        {"IRPJ": _D(4.0), "CSLL": _D(3.5), "COFINS": _D(14.05), "PIS": _D(3.05), "CPP": _D(43.4), "ISS": _D(32.0)}),
    FaixaSimples(3, _D(720_000),    _D(13.50), _D(17_640),
        {"IRPJ": _D(4.0), "CSLL": _D(3.5), "COFINS": _D(13.64), "PIS": _D(2.96), "CPP": _D(43.4), "ISS": _D(32.5)}),
    FaixaSimples(4, _D(1_800_000),  _D(16.00), _D(35_640),
        {"IRPJ": _D(4.0), "CSLL": _D(3.5), "COFINS": _D(13.64), "PIS": _D(2.96), "CPP": _D(43.4), "ISS": _D(32.5)}),
    FaixaSimples(5, _D(3_600_000),  _D(21.00), _D(125_640),
        {"IRPJ": _D(4.0), "CSLL": _D(3.5), "COFINS": _D(12.82), "PIS": _D(2.78), "CPP": _D(43.4), "ISS": _D(33.5)}),
    FaixaSimples(6, _D(4_800_000),  _D(33.00), _D(648_000),
        {"IRPJ": _D(35.0), "CSLL": _D(15.0), "COFINS": _D(16.03), "PIS": _D(3.47), "CPP": _D(30.5), "ISS": _D(0)}),
]

# --- ANEXO IV: SERVICOS (limpeza, vigilancia, construcao) — INSS por fora ---
ANEXO_IV: list[FaixaSimples] = [
    FaixaSimples(1, _D(180_000),    _D(4.50),  _D(0),
        {"IRPJ": _D(18.8), "CSLL": _D(15.2), "COFINS": _D(17.67), "PIS": _D(3.83), "ISS": _D(44.5)}),
    FaixaSimples(2, _D(360_000),    _D(9.00),  _D(8_100),
        {"IRPJ": _D(19.8), "CSLL": _D(15.2), "COFINS": _D(20.55), "PIS": _D(4.45), "ISS": _D(40.0)}),
    FaixaSimples(3, _D(720_000),    _D(10.20), _D(12_420),
        {"IRPJ": _D(20.8), "CSLL": _D(15.2), "COFINS": _D(19.73), "PIS": _D(4.27), "ISS": _D(40.0)}),
    FaixaSimples(4, _D(1_800_000),  _D(14.00), _D(39_780),
        {"IRPJ": _D(17.8), "CSLL": _D(19.2), "COFINS": _D(18.90), "PIS": _D(4.10), "ISS": _D(40.0)}),
    FaixaSimples(5, _D(3_600_000),  _D(22.00), _D(183_780),
        {"IRPJ": _D(18.8), "CSLL": _D(19.2), "COFINS": _D(18.08), "PIS": _D(3.92), "ISS": _D(40.0)}),
    FaixaSimples(6, _D(4_800_000),  _D(33.00), _D(828_000),
        {"IRPJ": _D(53.5), "CSLL": _D(21.5), "COFINS": _D(20.55), "PIS": _D(4.45), "ISS": _D(0)}),
]

# --- ANEXO V: SERVICOS (TI, advocacia, engenharia, midia) ---
# Pode migrar para ANEXO III via Fator R (folha 12m / receita 12m >= 0.28)
ANEXO_V: list[FaixaSimples] = [
    FaixaSimples(1, _D(180_000),    _D(15.50), _D(0),
        {"IRPJ": _D(25.0), "CSLL": _D(15.0), "COFINS": _D(14.10), "PIS": _D(3.05), "CPP": _D(28.85), "ISS": _D(14.0)}),
    FaixaSimples(2, _D(360_000),    _D(18.00), _D(4_500),
        {"IRPJ": _D(23.0), "CSLL": _D(15.0), "COFINS": _D(14.10), "PIS": _D(3.05), "CPP": _D(27.85), "ISS": _D(17.0)}),
    FaixaSimples(3, _D(720_000),    _D(19.50), _D(9_900),
        {"IRPJ": _D(24.0), "CSLL": _D(15.0), "COFINS": _D(14.92), "PIS": _D(3.23), "CPP": _D(23.85), "ISS": _D(19.0)}),
    FaixaSimples(4, _D(1_800_000),  _D(20.50), _D(17_100),
        {"IRPJ": _D(21.0), "CSLL": _D(15.0), "COFINS": _D(15.74), "PIS": _D(3.41), "CPP": _D(23.85), "ISS": _D(21.0)}),
    FaixaSimples(5, _D(3_600_000),  _D(23.00), _D(62_100),
        {"IRPJ": _D(23.0), "CSLL": _D(12.5), "COFINS": _D(14.10), "PIS": _D(3.05), "CPP": _D(23.85), "ISS": _D(23.5)}),
    FaixaSimples(6, _D(4_800_000),  _D(30.50), _D(540_000),
        {"IRPJ": _D(35.0), "CSLL": _D(15.5), "COFINS": _D(16.44), "PIS": _D(3.56), "CPP": _D(29.5), "ISS": _D(0)}),
]


_TABELA_POR_ANEXO: dict[str, list[FaixaSimples]] = {
    "I": ANEXO_I, "II": ANEXO_II, "III": ANEXO_III, "IV": ANEXO_IV, "V": ANEXO_V,
}


@dataclass(frozen=True, slots=True)
class CalculoSimples:
    anexo: str
    faixa: int
    rbt12: Decimal
    aliquota_nominal: Decimal      # %
    parcela_deduzir: Decimal       # R$
    aliquota_efetiva: Decimal      # %
    receita_mes: Decimal
    valor_devido: Decimal
    decomposicao: dict[str, Decimal]   # IRPJ/CSLL/PIS/COFINS/CPP/ICMS/ISS em R$
    teto_excedido: bool


def calcular_simples(
    anexo: str,
    rbt12: Decimal,
    receita_mes: Decimal,
) -> CalculoSimples:
    """Aplica a tabela do anexo informado e retorna decomposicao.

    Se rbt12 <= 0 (primeiro mes), usa receita_mes * 12 como estimativa.
    """
    tabela = _TABELA_POR_ANEXO.get(anexo)
    if not tabela:
        raise ValueError(f"Anexo invalido: {anexo}")
    if rbt12 <= 0:
        rbt12 = receita_mes * Decimal(12)

    teto_excedido = rbt12 > tabela[-1].teto
    faixa = tabela[-1]
    for f in tabela:
        if rbt12 <= f.teto:
            faixa = f
            break

    if rbt12 == 0:
        aliquota_efetiva = Decimal("0")
    else:
        aliquota_efetiva = (
            (rbt12 * faixa.aliquota_nominal / Decimal(100) - faixa.parcela_deduzir)
            / rbt12 * Decimal(100)
        ).quantize(Decimal("0.0001"))

    valor_devido = (receita_mes * aliquota_efetiva / Decimal(100)).quantize(Decimal("0.01"))

    # Decomposicao por tributo
    decomp: dict[str, Decimal] = {}
    for tributo, percentual in faixa.repartidos.items():
        decomp[tributo] = (valor_devido * percentual / Decimal(100)).quantize(Decimal("0.01"))

    return CalculoSimples(
        anexo=anexo,
        faixa=faixa.faixa,
        rbt12=rbt12.quantize(Decimal("0.01")),
        aliquota_nominal=faixa.aliquota_nominal,
        parcela_deduzir=faixa.parcela_deduzir,
        aliquota_efetiva=aliquota_efetiva,
        receita_mes=receita_mes.quantize(Decimal("0.01")),
        valor_devido=valor_devido,
        decomposicao=decomp,
        teto_excedido=teto_excedido,
    )


@dataclass(frozen=True, slots=True)
class CalculoSegregado:
    """Resultado de calculo Simples Nacional considerando segmentos.

    Cada segmento (NORMAL, MONOFASICO, ST, EXPORTACAO) eh tributado pela mesma
    aliquota efetiva da faixa, mas zerando os tributos ja recolhidos:
    - MONOFASICO: zera PIS e COFINS (ja recolhido pela industria/importador).
    - ST: zera ICMS (ja recolhido pelo substituto).
    - EXPORTACAO: zera PIS, COFINS, IPI, ICMS, ISS (resta IRPJ, CSLL, CPP).

    Ref: Resolucao CGSN 140/2018 art. 25.
    """
    anexo: str
    faixa: int
    rbt12: Decimal
    aliquota_nominal: Decimal
    aliquota_efetiva: Decimal
    teto_excedido: bool

    receita_total: Decimal
    receita_normal: Decimal
    receita_monofasica: Decimal
    receita_st: Decimal
    receita_exportacao: Decimal

    valor_devido: Decimal
    valor_normal: Decimal
    valor_monofasico: Decimal     # com PIS/COFINS zerados
    valor_st: Decimal             # com ICMS zerado
    valor_exportacao: Decimal     # so IRPJ + CSLL + CPP

    decomposicao: dict[str, Decimal]  # consolidado de IRPJ/CSLL/PIS/COFINS/CPP/ICMS/ISS


def calcular_simples_segregado(
    anexo: str,
    rbt12: Decimal,
    receita_normal: Decimal,
    receita_monofasica: Decimal = Decimal(0),
    receita_st: Decimal = Decimal(0),
    receita_exportacao: Decimal = Decimal(0),
) -> CalculoSegregado:
    """Calcula DAS aplicando regra de segregacao por tipo de receita.

    Cada parcela usa a mesma aliquota efetiva, mas zera os tributos ja recolhidos:
    - PIS+COFINS zerados na receita monofasica
    - ICMS zerado na receita ST (Anexo I/II) ou ISS (Anexo III/IV/V)
    - Em EXPORTACAO, zera PIS, COFINS, ICMS/ISS, IPI

    A aliquota efetiva eh aplicada sobre a receita_total para descobrir o "valor cheio"
    e depois zera-se a parcela proporcional aos tributos a remover.
    """
    receita_total = receita_normal + receita_monofasica + receita_st + receita_exportacao
    if receita_total <= 0:
        return CalculoSegregado(
            anexo=anexo, faixa=0, rbt12=Decimal("0"),
            aliquota_nominal=Decimal("0"), aliquota_efetiva=Decimal("0"),
            teto_excedido=False,
            receita_total=Decimal("0"), receita_normal=Decimal("0"),
            receita_monofasica=Decimal("0"), receita_st=Decimal("0"),
            receita_exportacao=Decimal("0"),
            valor_devido=Decimal("0"), valor_normal=Decimal("0"),
            valor_monofasico=Decimal("0"), valor_st=Decimal("0"),
            valor_exportacao=Decimal("0"),
            decomposicao={},
        )

    # Aplica tabela uma unica vez para descobrir aliquota
    base = calcular_simples(anexo, rbt12, receita_total)
    aliquota = base.aliquota_efetiva  # %
    repartido = _TABELA_POR_ANEXO[anexo][base.faixa - 1].repartidos

    def _parcela_valor(receita_parcela: Decimal) -> tuple[Decimal, dict[str, Decimal]]:
        """DAS desta parcela: receita * aliquota_efetiva, decomposto por tributo."""
        v_total = (receita_parcela * aliquota / Decimal(100)).quantize(Decimal("0.01"))
        decomp = {
            tributo: (v_total * pct / Decimal(100)).quantize(Decimal("0.01"))
            for tributo, pct in repartido.items()
        }
        return v_total, decomp

    # NORMAL: tudo
    v_normal, dec_normal = _parcela_valor(receita_normal)

    # MONOFASICO: zera PIS + COFINS
    v_mono_bruto, dec_mono = _parcela_valor(receita_monofasica)
    pis_mono = dec_mono.pop("PIS", Decimal("0"))
    cofins_mono = dec_mono.pop("COFINS", Decimal("0"))
    v_monofasico = v_mono_bruto - pis_mono - cofins_mono

    # ST: zera ICMS (comercio/industria) ou ISS (servicos)
    v_st_bruto, dec_st = _parcela_valor(receita_st)
    icms_st = dec_st.pop("ICMS", Decimal("0"))
    iss_st = dec_st.pop("ISS", Decimal("0"))  # alguns anexos tem ISS no lugar
    v_st = v_st_bruto - icms_st - iss_st

    # EXPORTACAO: zera PIS, COFINS, IPI, ICMS, ISS — resta IRPJ, CSLL, CPP
    v_exp_bruto, dec_exp = _parcela_valor(receita_exportacao)
    for tributo_zero in ("PIS", "COFINS", "IPI", "ICMS", "ISS"):
        dec_exp.pop(tributo_zero, None)
    v_exportacao = sum(dec_exp.values(), Decimal("0"))

    valor_devido = (v_normal + v_monofasico + v_st + v_exportacao).quantize(Decimal("0.01"))

    # Decomposicao consolidada
    consolidada: dict[str, Decimal] = {}
    for d in (dec_normal, dec_mono, dec_st, dec_exp):
        for k, v in d.items():
            consolidada[k] = consolidada.get(k, Decimal("0")) + v
    consolidada = {k: v.quantize(Decimal("0.01")) for k, v in consolidada.items() if v > 0}

    return CalculoSegregado(
        anexo=anexo,
        faixa=base.faixa,
        rbt12=base.rbt12,
        aliquota_nominal=base.aliquota_nominal,
        aliquota_efetiva=aliquota,
        teto_excedido=base.teto_excedido,
        receita_total=receita_total.quantize(Decimal("0.01")),
        receita_normal=receita_normal.quantize(Decimal("0.01")),
        receita_monofasica=receita_monofasica.quantize(Decimal("0.01")),
        receita_st=receita_st.quantize(Decimal("0.01")),
        receita_exportacao=receita_exportacao.quantize(Decimal("0.01")),
        valor_devido=valor_devido,
        valor_normal=v_normal,
        valor_monofasico=v_monofasico.quantize(Decimal("0.01")),
        valor_st=v_st.quantize(Decimal("0.01")),
        valor_exportacao=v_exportacao.quantize(Decimal("0.01")),
        decomposicao=consolidada,
    )


def fator_r(folha_12m: Decimal, receita_12m: Decimal) -> Decimal:
    """Calcula o Fator R para escolha entre Anexo III e V em servicos."""
    if receita_12m <= 0:
        return Decimal("0")
    return (folha_12m / receita_12m).quantize(Decimal("0.0001"))


def anexo_pelo_fator_r(folha_12m: Decimal, receita_12m: Decimal, anexo_padrao: str = "V") -> str:
    """Servicos do Anexo V migram para o III quando Fator R >= 28%."""
    fr = fator_r(folha_12m, receita_12m)
    if fr >= Decimal("0.28"):
        return "III"
    return anexo_padrao
