"""Motor de apuracao do Simples Nacional — analise ITEM A ITEM.

Le os DocumentoFiscal de uma empresa+competencia, abre cada XML do disco,
extrai cada `<det>` com CFOP/CST/CSOSN/CST PIS/CST COFINS/NCM/valor,
classifica conforme tabela CFOP + tabela tributaria, e devolve:

- receita bruta liquida (saidas tributadas - devolucoes de venda)
- segregacao por tipo de tributacao:
    * NORMAL (tributacao cheia)
    * MONOFASICA (PIS/COFINS ja recolhidos pela industria/importador)
    * ST (ICMS ja recolhido pelo substituto)
    * EXPORTACAO (zera PIS/COFINS/ICMS/ISS/IPI)
- aliquota efetiva e valor devido, com decomposicao por tributo
- detalhamento item a item (auditoria + transparencia)

Para devolucoes de venda (CFOP 1.2xx, 2.2xx) entram como entrada e SUBTRAEM
proporcionalmente do segmento original (assumido NORMAL por padrao se nao
houver mais detalhe).

Servicos (NFSe) entram pelo `valor_total` como receita NORMAL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.apuracao import Apuracao, StatusApuracao
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.utils.cfop import classificar_cfop
from app.utils.simples_nacional import (
    CalculoSegregado,
    anexo_pelo_fator_r,
    calcular_simples_segregado,
    fator_r,
)
from app.utils.tributacao import classificar_item


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _D(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


@dataclass
class ItemAnalisado:
    """Analise de um item de NFe — granularidade do motor."""
    cfop: str
    direcao: str             # ENTRADA | SAIDA
    natureza: str            # VENDA | DEVOLUCAO_VENDA | EXPORTACAO | OUTRO
    afeta_receita: int       # +1 | -1 | 0
    valor_produto: Decimal   # vProd
    ncm: str | None
    csosn: str | None
    cst_icms: str | None
    cst_pis: str | None
    cst_cofins: str | None
    tipo_tributacao: str     # NORMAL | MONOFASICO | ST | MONOFASICO_ST | ISENTA | EXPORTACAO
    monofasico_categoria: str | None  # COMBUSTIVEL | MEDICAMENTO_COSMETICO | ...
    contribuicao: Decimal    # valor_produto * afeta_receita


@dataclass
class DocumentoAnalise:
    documento_id: int
    chave: str
    cnpj_emitente: str | None
    nome_emitente: str | None
    valor_nota: Decimal
    direcao: str
    natureza_predominante: str
    afeta_receita: int
    contribuicao_receita: Decimal
    com_st: bool
    monofasico: bool
    cfops: list[str] = field(default_factory=list)
    itens: list[ItemAnalisado] = field(default_factory=list)
    motivo_zero: str | None = None


@dataclass
class ResumoApuracao:
    empresa_id: int
    empresa_cnpj: str
    empresa_nome: str
    ano_mes: str

    total_docs: int
    saidas: int
    entradas: int
    docs_ignorados: int

    # Receitas brutas por segmento (saidas tributadas)
    total_normal: Decimal
    total_monofasico: Decimal
    total_st: Decimal
    total_exportacao: Decimal
    total_servicos: Decimal

    # Devolucoes (entradas) — subtraem proporcionalmente do segmento normal por padrao
    total_devolucoes_venda: Decimal

    # Receita bruta total liquida = saidas tributadas - devolucoes
    receita_bruta: Decimal

    # Detalhamento monofasico por categoria (combustivel, medicamento, ...)
    monofasico_por_categoria: dict[str, Decimal]

    # RBT12 e calculo
    rbt12: Decimal
    primeira_apuracao: bool
    anexo: str
    fator_r_valor: Decimal | None
    calculo: CalculoSegregado | None

    # Auditoria
    documentos: list[DocumentoAnalise]
    avisos: list[str]

    def to_payload(self) -> dict[str, Any]:
        d = asdict(self)
        d["calculo"] = asdict(self.calculo) if self.calculo else None
        return _decimals_to_str(d)


def _decimals_to_str(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _decimals_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimals_to_str(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    return obj


# ============================================================
#  MOTOR
# ============================================================


class ApuracaoCalculator:

    def __init__(self, db: Session) -> None:
        self.db = db

    def calcular(self, empresa_id: int, ano_mes: str) -> ResumoApuracao:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise ValueError(f"Empresa {empresa_id} nao encontrada")
        if len(ano_mes) != 6 or not ano_mes.isdigit():
            raise ValueError("ano_mes deve ser YYYYMM")

        ano = int(ano_mes[:4])
        mes = int(ano_mes[4:])
        documentos = self._documentos_da_competencia(empresa.id, ano, mes)

        analises: list[DocumentoAnalise] = []
        avisos: list[str] = []

        for doc in documentos:
            try:
                analise = self._analisar_documento(doc)
                analises.append(analise)
            except Exception as exc:
                avisos.append(f"Doc #{doc.id} ({doc.chave_acesso[:10]}...) ignorado: {exc}")

        # Agregar por SEGMENTO (somando ITEM A ITEM)
        total_normal = Decimal("0")
        total_monofasico = Decimal("0")
        total_st = Decimal("0")
        total_exportacao = Decimal("0")
        total_servicos = Decimal("0")
        total_devolucoes = Decimal("0")
        monofasico_por_categoria: dict[str, Decimal] = {}

        for a in analises:
            if a.natureza_predominante == "SERVICO":
                total_servicos += a.valor_nota
                continue
            if a.natureza_predominante == "DEVOLUCAO_VENDA":
                total_devolucoes += a.valor_nota
                continue
            for item in a.itens:
                if item.afeta_receita != 1:
                    continue
                if item.natureza == "EXPORTACAO":
                    total_exportacao += item.valor_produto
                    continue
                tipo = item.tipo_tributacao
                if tipo in ("MONOFASICO", "MONOFASICO_ST"):
                    total_monofasico += item.valor_produto
                    if item.monofasico_categoria:
                        monofasico_por_categoria[item.monofasico_categoria] = (
                            monofasico_por_categoria.get(item.monofasico_categoria, Decimal("0"))
                            + item.valor_produto
                        )
                if tipo in ("ST", "MONOFASICO_ST"):
                    total_st += item.valor_produto
                if tipo == "NORMAL" or tipo == "ISENTA":
                    total_normal += item.valor_produto

        # Devolucoes subtraem proporcionalmente do segmento NORMAL (assumido)
        # — simplificacao MVP. Versao futura poderia identificar o tipo da nota original.
        total_normal_liquido = total_normal - total_devolucoes
        if total_normal_liquido < 0:
            # Se a devolucao excede o NORMAL, sobra reduz o monofasico (pior caso)
            sobra = -total_normal_liquido
            total_normal_liquido = Decimal("0")
            total_monofasico = max(Decimal("0"), total_monofasico - sobra)

        receita_bruta = (
            total_normal_liquido + total_monofasico + total_st + total_exportacao + total_servicos
        )

        # RBT12
        rbt12, primeira_apuracao = self._rbt12(empresa.id, ano_mes)

        # Anexo (Fator R para servicos do Anexo V)
        anexo = (empresa.anexo_simples or self._anexo_padrao_por_atividade(empresa)).upper()
        fator_r_valor: Decimal | None = None
        if anexo == "V" and empresa.folha_12m:
            fator_r_valor = fator_r(_D(empresa.folha_12m), rbt12 or receita_bruta * 12)
            anexo = anexo_pelo_fator_r(_D(empresa.folha_12m), rbt12 or receita_bruta * 12, "V")

        # Calculo segregado
        calculo: CalculoSegregado | None = None
        if receita_bruta > 0:
            try:
                # Servicos entram em NORMAL para Anexo III/IV/V; em I/II eh comercio/industria
                receita_normal_calc = total_normal_liquido + (
                    total_servicos if anexo in {"III", "IV", "V"} else Decimal("0")
                )
                if anexo in {"I", "II"} and total_servicos > 0:
                    avisos.append(
                        f"R$ {total_servicos} de servicos ignorados — anexo {anexo} eh "
                        f"comercio/industria. Verifique segregacao por atividade."
                    )
                calculo = calcular_simples_segregado(
                    anexo=anexo,
                    rbt12=rbt12,
                    receita_normal=receita_normal_calc,
                    receita_monofasica=total_monofasico,
                    receita_st=total_st,
                    receita_exportacao=total_exportacao,
                )
                if calculo.teto_excedido:
                    avisos.append(
                        f"RBT12 R$ {rbt12} excedeu o teto do Simples Nacional (R$ 4.8mi). "
                        "Exclusao deve ser providenciada."
                    )
            except ValueError as exc:
                avisos.append(str(exc))

        if any(a.natureza_predominante == "OUTRO" for a in analises):
            qtd = sum(1 for a in analises if a.natureza_predominante == "OUTRO")
            avisos.append(
                f"{qtd} documento(s) com CFOP nao mapeado. Revise antes de transmitir."
            )

        if total_monofasico > 0 and not monofasico_por_categoria:
            avisos.append(
                "Monofasico identificado por CST mas sem categoria NCM. "
                "Verifique cadastro do produto."
            )

        return ResumoApuracao(
            empresa_id=empresa.id,
            empresa_cnpj=empresa.cnpj,
            empresa_nome=empresa.razao_social,
            ano_mes=ano_mes,
            total_docs=len(analises),
            saidas=sum(1 for a in analises if a.direcao == "SAIDA"),
            entradas=sum(1 for a in analises if a.direcao == "ENTRADA"),
            docs_ignorados=sum(1 for a in analises if a.afeta_receita == 0),
            total_normal=total_normal_liquido.quantize(Decimal("0.01")),
            total_monofasico=total_monofasico.quantize(Decimal("0.01")),
            total_st=total_st.quantize(Decimal("0.01")),
            total_exportacao=total_exportacao.quantize(Decimal("0.01")),
            total_servicos=total_servicos.quantize(Decimal("0.01")),
            total_devolucoes_venda=total_devolucoes.quantize(Decimal("0.01")),
            receita_bruta=receita_bruta.quantize(Decimal("0.01")),
            monofasico_por_categoria={
                k: v.quantize(Decimal("0.01")) for k, v in monofasico_por_categoria.items()
            },
            rbt12=rbt12.quantize(Decimal("0.01")),
            primeira_apuracao=primeira_apuracao,
            anexo=anexo,
            fator_r_valor=fator_r_valor,
            calculo=calculo,
            documentos=analises,
            avisos=avisos,
        )

    def calcular_e_salvar(self, empresa_id: int, ano_mes: str) -> Apuracao:
        resumo = self.calcular(empresa_id, ano_mes)
        existente = self.db.scalar(
            select(Apuracao).where(
                Apuracao.empresa_id == empresa_id, Apuracao.ano_mes == ano_mes,
            )
        )
        if existente:
            apur = existente
        else:
            apur = Apuracao(
                empresa_id=empresa_id, ano_mes=ano_mes, status=StatusApuracao.DRAFT,
            )
            self.db.add(apur)

        apur.receita_bruta = resumo.receita_bruta
        if resumo.calculo:
            apur.valor_devido = resumo.calculo.valor_devido
        apur.receitas_segregadas = [
            {"natureza": "NORMAL", "valor": str(resumo.total_normal)},
            {"natureza": "MONOFASICO", "valor": str(resumo.total_monofasico)},
            {"natureza": "ST", "valor": str(resumo.total_st)},
            {"natureza": "EXPORTACAO", "valor": str(resumo.total_exportacao)},
            {"natureza": "SERVICO", "valor": str(resumo.total_servicos)},
        ]
        apur.raw_declaracao = {"motor_calculo": resumo.to_payload()}
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Helpers ---

    def _anexo_padrao_por_atividade(self, empresa: Empresa) -> str:
        atividade = (empresa.atividade or "").upper()
        if atividade == "INDUSTRIA":
            return "II"
        if atividade == "SERVICO":
            return "III"
        return "I"

    def _documentos_da_competencia(
        self, empresa_id: int, ano: int, mes: int,
    ) -> list[DocumentoFiscal]:
        ini = datetime(ano, mes, 1)
        fim = datetime(ano + 1, 1, 1) if mes == 12 else datetime(ano, mes + 1, 1)
        stmt = (
            select(DocumentoFiscal)
            .where(
                DocumentoFiscal.empresa_id == empresa_id,
                DocumentoFiscal.data_emissao >= ini,
                DocumentoFiscal.data_emissao < fim,
            )
            .order_by(DocumentoFiscal.data_emissao)
        )
        return list(self.db.scalars(stmt).all())

    def _rbt12(self, empresa_id: int, ano_mes: str) -> tuple[Decimal, bool]:
        ano = int(ano_mes[:4]); mes = int(ano_mes[4:])
        meses_anteriores: list[str] = []
        m = mes; a = ano
        for _ in range(12):
            m -= 1
            if m == 0: m = 12; a -= 1
            meses_anteriores.append(f"{a}{m:02d}")
        apuracoes = self.db.scalars(
            select(Apuracao).where(
                Apuracao.empresa_id == empresa_id,
                Apuracao.ano_mes.in_(meses_anteriores),
            )
        ).all()
        total = sum((a.receita_bruta or Decimal(0) for a in apuracoes), Decimal("0"))
        return total, len(apuracoes) == 0

    def _analisar_documento(self, doc: DocumentoFiscal) -> DocumentoAnalise:
        if doc.tipo_documento == TipoDocumento.NFSE:
            # NFSe: 1 item conceitual = servico tributado
            item = ItemAnalisado(
                cfop="-", direcao="SAIDA", natureza="SERVICO",
                afeta_receita=1,
                valor_produto=doc.valor_total or Decimal("0"),
                ncm=None, csosn=None, cst_icms=None, cst_pis=None, cst_cofins=None,
                tipo_tributacao="NORMAL", monofasico_categoria=None,
                contribuicao=doc.valor_total or Decimal("0"),
            )
            return DocumentoAnalise(
                documento_id=doc.id, chave=doc.chave_acesso,
                cnpj_emitente=doc.cnpj_emitente, nome_emitente=doc.nome_emitente,
                valor_nota=doc.valor_total or Decimal("0"),
                direcao="SAIDA", natureza_predominante="SERVICO",
                afeta_receita=1, contribuicao_receita=doc.valor_total or Decimal("0"),
                com_st=False, monofasico=False,
                cfops=[], itens=[item],
            )

        # NFe / CTe — abrir XML e extrair item a item
        itens = self._extrair_itens(doc.xml_path)

        # Direcao + natureza_predominante a partir dos CFOPs do documento
        cfops_doc = [it.cfop for it in itens if it.cfop and it.cfop != "-"]
        com_st = any(it.tipo_tributacao in ("ST", "MONOFASICO_ST") for it in itens)
        monofasico_doc = any(it.tipo_tributacao in ("MONOFASICO", "MONOFASICO_ST") for it in itens)

        if not itens:
            # XML vazio/ilegivel
            origem_default = "ENTRADA" if doc.origem == "recebida" else "SAIDA"
            return DocumentoAnalise(
                documento_id=doc.id, chave=doc.chave_acesso,
                cnpj_emitente=doc.cnpj_emitente, nome_emitente=doc.nome_emitente,
                valor_nota=doc.valor_total or Decimal("0"),
                direcao=origem_default,
                natureza_predominante="OUTRO",
                afeta_receita=0, contribuicao_receita=Decimal("0"),
                com_st=False, monofasico=False, cfops=[], itens=[],
                motivo_zero="XML sem itens parseaveis",
            )

        # Direcao = direcao do primeiro item relevante
        direcoes = {it.direcao for it in itens}
        direcao = "SAIDA" if "SAIDA" in direcoes else "ENTRADA"

        # Natureza predominante = a com maior soma
        soma_por_natureza: dict[str, Decimal] = {}
        for it in itens:
            soma_por_natureza[it.natureza] = (
                soma_por_natureza.get(it.natureza, Decimal("0")) + it.valor_produto
            )
        natureza_predominante = max(soma_por_natureza, key=lambda k: soma_por_natureza[k])

        afeta_doc = sum(it.afeta_receita for it in itens) // max(1, len(itens))
        if afeta_doc > 0: afeta_doc = 1
        elif afeta_doc < 0: afeta_doc = -1
        else: afeta_doc = 0

        contribuicao = sum(
            (it.contribuicao for it in itens), Decimal("0")
        )

        return DocumentoAnalise(
            documento_id=doc.id, chave=doc.chave_acesso,
            cnpj_emitente=doc.cnpj_emitente, nome_emitente=doc.nome_emitente,
            valor_nota=doc.valor_total or Decimal("0"),
            direcao=direcao,
            natureza_predominante=natureza_predominante,
            afeta_receita=afeta_doc,
            contribuicao_receita=contribuicao,
            com_st=com_st, monofasico=monofasico_doc,
            cfops=cfops_doc, itens=itens,
            motivo_zero=None if afeta_doc != 0 else (
                "Operacao nao gera receita (compra/remessa/transferencia)"
            ),
        )

    def _extrair_itens(self, xml_path: str | None) -> list[ItemAnalisado]:
        if not xml_path:
            return []
        path = Path(xml_path)
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8")
            root = ET.fromstring(content)
        except Exception:
            return []

        itens: list[ItemAnalisado] = []
        for det in root.iter():
            if _local(det.tag) != "det":
                continue
            cfop: str = ""
            ncm: str | None = None
            valor_prod: Decimal = Decimal("0")
            csosn: str | None = None
            cst_icms: str | None = None
            cst_pis: str | None = None
            cst_cofins: str | None = None
            in_pis = False
            in_cofins = False

            for elem in det.iter():
                name = _local(elem.tag)
                # Stack tracking simples: detectamos se estamos dentro de PIS ou COFINS
                if name in ("PIS", "PISAliq", "PISQtde", "PISNT", "PISOutr",
                            "PISAliquota", "PISST"):
                    in_pis = True; in_cofins = False
                elif name in ("COFINS", "COFINSAliq", "COFINSQtde", "COFINSNT",
                              "COFINSOutr", "COFINSAliquota", "COFINSST"):
                    in_pis = False; in_cofins = True
                elif name in ("ICMS", "ICMSSN101", "ICMSSN102", "ICMSSN201",
                              "ICMSSN202", "ICMSSN500", "ICMS00", "ICMS10",
                              "ICMS20", "ICMS30", "ICMS40", "ICMS51", "ICMS60",
                              "ICMS70", "ICMS90", "ICMSST"):
                    in_pis = False; in_cofins = False

                txt = (elem.text or "").strip() if elem.text else ""
                if name == "CFOP" and txt:
                    cfop = txt
                elif name == "NCM" and txt and not ncm:
                    ncm = txt
                elif name == "vProd" and txt:
                    valor_prod = _D(txt)
                elif name == "CSOSN" and txt:
                    csosn = txt
                elif name == "CST" and txt:
                    if in_pis:
                        cst_pis = txt
                    elif in_cofins:
                        cst_cofins = txt
                    elif not cst_icms:
                        cst_icms = txt

            if not cfop:
                continue

            cfop_info = classificar_cfop(cfop)
            classe = classificar_item(
                csosn_icms=csosn, cst_icms=cst_icms,
                cst_pis=cst_pis, cst_cofins=cst_cofins,
                ncm=ncm,
            )

            tipo_tributacao = classe.tipo
            # Sobrepor tipo se for exportacao pelo CFOP
            if cfop_info.natureza == "EXPORTACAO":
                tipo_tributacao = "EXPORTACAO"

            itens.append(ItemAnalisado(
                cfop=cfop,
                direcao=cfop_info.direcao,
                natureza=cfop_info.natureza,
                afeta_receita=cfop_info.afeta_receita,
                valor_produto=valor_prod,
                ncm=ncm,
                csosn=csosn,
                cst_icms=cst_icms,
                cst_pis=cst_pis,
                cst_cofins=cst_cofins,
                tipo_tributacao=tipo_tributacao,
                monofasico_categoria=classe.monofasico_categoria,
                contribuicao=valor_prod * Decimal(cfop_info.afeta_receita),
            ))
        return itens
