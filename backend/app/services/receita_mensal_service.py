"""Serviço de faturamento mensal (RBT12) — manual + puxar da Receita.

O RBT12 (Receita Bruta dos 12 meses anteriores) define a alíquota efetiva do
Simples Nacional. Empresas migradas não têm histórico de NFes, então o
faturamento dos meses anteriores precisa ser informado:

1. Manual: contador digita os 12 meses (grade).
2. Puxar da Receita: via Integra Contador (CONSDECLARACAO13 + CONSDECREC15)
   — vem da fonte oficial, garante que o RBT12 bate.
"""
from __future__ import annotations

import base64
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.empresa import Empresa
from app.models.receita_mensal import ReceitaMensal
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)


def _achar_receita(obj: Any, palavras: tuple[str, ...], _prof: int = 0) -> float:
    """Busca recursiva por um campo numérico cujo nome contenha uma das
    `palavras` (lowercase). Retorna o maior valor encontrado (a receita bruta
    costuma ser o maior numero). 0 se não achar. Limita profundidade."""
    if _prof > 6:
        return 0.0
    melhor = 0.0
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if isinstance(v, (int, float)) and any(p in kl for p in palavras):
                melhor = max(melhor, float(v))
            elif isinstance(v, (dict, list)):
                melhor = max(melhor, _achar_receita(v, palavras, _prof + 1))
    elif isinstance(obj, list):
        for it in obj:
            melhor = max(melhor, _achar_receita(it, palavras, _prof + 1))
    return melhor


def _truncar(obj: Any, _prof: int = 0):
    """Versão resumida de um dict/list pra debug (corta strings longas/base64)."""
    if _prof > 4:
        return "..."
    if isinstance(obj, dict):
        return {k: _truncar(v, _prof + 1) for k, v in list(obj.items())[:30]}
    if isinstance(obj, list):
        return [_truncar(v, _prof + 1) for v in obj[:5]]
    if isinstance(obj, str) and len(obj) > 80:
        return obj[:80] + "...(truncado)"
    return obj


# --- Leitura do PDF da PGDAS-D (Serpro só devolve PDF, sem campo estruturado) ---

_BRL_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")


def _brl_para_float(s: str) -> float:
    """'5.701,00' -> 5701.0"""
    try:
        return float(s.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def _pdf_para_texto(pdf_b64: str | None) -> str:
    """Decodifica o PDF base64 e extrai todo o texto. '' se falhar."""
    if not pdf_b64:
        return ""
    try:
        import pdfplumber  # import tardio: só carrega quando realmente usa

        raw = base64.b64decode(pdf_b64)
        partes: list[str] = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                partes.append(page.extract_text() or "")
        return "\n".join(partes)
    except Exception:
        return ""


def _valor_proximo(texto: str, palavras: tuple[str, ...], janela: int = 160) -> float:
    """Acha a 1ª ocorrência de qualquer `palavra` (lowercase) e devolve o 1º
    valor em formato BRL que aparece logo depois (dentro de `janela` chars).
    0.0 se não achar."""
    low = texto.lower()
    melhor_pos = -1
    for p in palavras:
        pos = low.find(p)
        if pos != -1 and (melhor_pos == -1 or pos < melhor_pos):
            melhor_pos = pos
            achou_p = p
    if melhor_pos == -1:
        return 0.0
    trecho = texto[melhor_pos: melhor_pos + len(achou_p) + janela]
    m = _BRL_RE.search(trecho)
    return _brl_para_float(m.group(1)) if m else 0.0


def _valores_apos(
    texto: str, palavras: tuple[str, ...], n: int = 3, janela: int = 240,
) -> list[float]:
    """Acha a 1ª ocorrência (mais à esquerda) de qualquer `palavra` e devolve os
    primeiros `n` valores BRL que aparecem logo depois, EM ORDEM."""
    low = texto.lower()
    melhor_pos = -1
    achou_p = ""
    for p in palavras:
        pos = low.find(p)
        if pos != -1 and (melhor_pos == -1 or pos < melhor_pos):
            melhor_pos = pos
            achou_p = p
    if melhor_pos == -1:
        return []
    ini = melhor_pos + len(achou_p)
    trecho = texto[ini: ini + janela]
    return [_brl_para_float(m.group(1)) for m in _BRL_RE.finditer(trecho)][:n]


def _extrair_receitas_pdf(texto: str) -> tuple[float, float]:
    """Extrai (receita_interna, receita_externa) do recibo/declaração PGDAS-D.

    O recibo traz a linha da RPA (receita do PERÍODO, regime de competência) com
    3 valores em ordem: Mercado Interno | Mercado Externo | Total. Lê os 3 da
    MESMA linha e deriva externo = total − interno.

    ⚠️ BUG corrigido (19/06): o parser antigo procurava o rótulo "Mercado Externo"
    (que no recibo é só o CABEÇALHO da coluna) e pegava o 1º número depois — que é
    o do INTERNO (a linha de dados começa no interno). Resultado: externo=interno →
    RBT12 DOBRADO (METHA BIKE: 2,35M em vez de 1,18M → Faixa 5 em vez de 4 → DAS a
    maior). Derivar externo do total elimina a recaptura."""
    if not texto:
        return 0.0, 0.0

    # Linha da receita do PERÍODO (RPA), NÃO a do RBT12 (acumulado 12 meses).
    nums = _valores_apos(texto, (
        "regime de competência", "regime de competencia",
        "receita bruta do período de apuração", "receita bruta do periodo de apuracao",
        "receita bruta do pa", "(rpa)",
    ), n=3, janela=240)

    if len(nums) >= 3:
        interno, total = nums[0], nums[2]
        externo = round(total - interno, 2)  # total = interno + externo (consistente)
        return interno, (externo if externo > 0 else 0.0)
    if len(nums) == 2:
        interno, segundo = nums[0], nums[1]
        # 2 números iguais = o 2º é recaptura do interno → externo 0.
        return interno, (0.0 if abs(segundo - interno) < 0.01 else segundo)
    if len(nums) == 1:
        return nums[0], 0.0

    # Fallback (layout fora do padrão): rótulos diretos, com trava anti-dobra.
    interno = _valor_proximo(texto, (
        "mercado interno", "receita bruta interna",
        "receita bruta de mercado interno", "rpa",
    ))
    externo = _valor_proximo(texto, (
        "receita bruta externa", "receita bruta de mercado externo",
        "exportação", "exportacao",
    ))
    if abs(externo - interno) < 0.01 and interno > 0:
        externo = 0.0  # externo recapturou o interno
    return interno, externo


def meses_anteriores(ano_mes: str, n: int = 12) -> list[str]:
    """Lista os N meses ANTERIORES a ano_mes (AAAAMM), do mais antigo ao mais novo."""
    ano = int(ano_mes[:4]); mes = int(ano_mes[4:])
    out: list[str] = []
    m, a = mes, ano
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12; a -= 1
        out.append(f"{a}{m:02d}")
    return list(reversed(out))  # mais antigo primeiro


class ReceitaMensalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    def get_empresa_or_404(self, empresa_id: int) -> Empresa:
        emp = self.db.get(Empresa, empresa_id)
        if not emp:
            raise HTTPException(status_code=404, detail="Empresa nao encontrada")
        return emp

    def listar(self, empresa_id: int) -> list[ReceitaMensal]:
        return self.db.scalars(
            select(ReceitaMensal)
            .where(ReceitaMensal.empresa_id == empresa_id)
            .order_by(ReceitaMensal.ano_mes)
        ).all()

    def listar_para_competencia(self, empresa_id: int, ano_mes: str) -> dict[str, Any]:
        """Devolve os 12 meses anteriores a `ano_mes` com valores (0 se vazio)."""
        self.get_empresa_or_404(empresa_id)
        meses = meses_anteriores(ano_mes, 12)
        existentes = {
            r.ano_mes: r for r in self.db.scalars(
                select(ReceitaMensal).where(
                    ReceitaMensal.empresa_id == empresa_id,
                    ReceitaMensal.ano_mes.in_(meses),
                )
            ).all()
        }
        linhas = []
        for am in meses:
            r = existentes.get(am)
            linhas.append({
                "ano_mes": am,
                "valor_interno": float(r.valor_interno) if r else 0.0,
                "valor_externo": float(r.valor_externo) if r else 0.0,
                "origem": r.origem if r else None,
            })
        rbt12 = sum(l["valor_interno"] + l["valor_externo"] for l in linhas)
        return {
            "empresa_id": empresa_id,
            "competencia": ano_mes,
            "meses": linhas,
            "rbt12": round(rbt12, 2),
            "meses_preenchidos": sum(1 for l in linhas if (l["valor_interno"] + l["valor_externo"]) > 0),
        }

    def salvar_em_lote(
        self, empresa_id: int, meses: list[dict[str, Any]], *, origem: str = "manual",
    ) -> dict[str, Any]:
        """UPSERT de vários meses de uma vez (grade manual)."""
        self.get_empresa_or_404(empresa_id)
        salvos = 0
        for item in meses:
            am = str(item.get("ano_mes") or "").strip()
            if len(am) != 6 or not am.isdigit():
                continue
            interno = Decimal(str(item.get("valor_interno") or 0))
            externo = Decimal(str(item.get("valor_externo") or 0))
            existente = self.db.scalar(
                select(ReceitaMensal).where(
                    ReceitaMensal.empresa_id == empresa_id,
                    ReceitaMensal.ano_mes == am,
                )
            )
            if existente:
                existente.valor_interno = interno
                existente.valor_externo = externo
                existente.origem = origem
            else:
                self.db.add(ReceitaMensal(
                    empresa_id=empresa_id, ano_mes=am,
                    valor_interno=interno, valor_externo=externo, origem=origem,
                ))
            salvos += 1
        self.db.commit()
        return {"salvos": salvos}

    def puxar_da_receita(self, empresa_id: int, ano_mes: str) -> dict[str, Any]:
        """Puxa o faturamento dos 12 meses anteriores via Integra Contador.

        Fluxo: pra cada ano envolvido, CONSDECLARACAO13 lista as declarações;
        pra cada declaração CONSDECREC15 traz o detalhe com a receita bruta.
        Salva em ReceitaMensal com origem='receita'. Best-effort: o que não
        conseguir extrair fica 0 pro contador completar manualmente.
        """
        empresa = self.get_empresa_or_404(empresa_id)
        meses = meses_anteriores(ano_mes, 12)
        anos = sorted({am[:4] for am in meses})

        # 1. Lista declarações por ano → mapa competencia -> numeroDeclaracao
        num_por_competencia: dict[str, str] = {}
        erros: list[str] = []
        for ano in anos:
            try:
                resp = self.provider.pgdas_listar_declaracoes(empresa.cnpj, ano=ano)
            except IntegraContadorError as exc:
                erros.append(f"Ano {ano}: {exc}")
                continue
            dados = parse_dados(resp)
            for periodo in (dados.get("periodos") or []):
                comp = str(periodo.get("periodoApuracao") or "")
                for op in (periodo.get("operacoes") or []):
                    idx = op.get("indiceDeclaracao") or {}
                    num = idx.get("numeroDeclaracao")
                    if num and comp:
                        num_por_competencia[comp] = num

        # 2. Pra cada mês anterior, consulta a declaração e tenta extrair receita
        resultado_meses: list[dict[str, Any]] = []
        debug_raw = None  # estrutura crua do 1º CONSDECREC (pra mapear campos)
        for am in meses:
            num = num_por_competencia.get(am)
            valor_interno = 0.0
            valor_externo = 0.0
            achou = False
            if num:
                try:
                    det = self.provider.pgdas_consultar_declaracao(
                        empresa.cnpj, numero_declaracao=num,
                    )
                    dd = parse_dados(det)
                    # O Serpro devolve a declaração como PDF (recibo + declaração).
                    # Extrai o texto dos dois e parseia a receita bruta.
                    texto_pdf = ""
                    if isinstance(dd, dict):
                        for chave_pdf in ("declaracao", "recibo"):
                            bloco = dd.get(chave_pdf)
                            if isinstance(bloco, dict) and bloco.get("pdf"):
                                texto_pdf += "\n" + _pdf_para_texto(bloco["pdf"])
                    if debug_raw is None:
                        # 1ª resposta: guarda o texto cru do PDF pra calibrar os
                        # rótulos exatos do layout Serpro.
                        debug_raw = {
                            "competencia": am,
                            "chaves_topo": list(dd.keys()) if isinstance(dd, dict) else str(type(dd)),
                            "tem_texto_pdf": bool(texto_pdf.strip()),
                            "texto_pdf_amostra": texto_pdf[:3500],
                        }
                    valor_interno, valor_externo = _extrair_receitas_pdf(texto_pdf)
                    achou = (valor_interno + valor_externo) > 0
                except IntegraContadorError as exc:
                    erros.append(f"{am}: {exc}")
                except Exception as exc:  # noqa: BLE001 — leitura de PDF best-effort
                    erros.append(f"{am}: falha ao ler PDF da declaração: {exc}")
            if achou:
                self._upsert(empresa_id, am, valor_interno, valor_externo, "receita")
            resultado_meses.append({
                "ano_mes": am,
                "valor_interno": valor_interno,
                "valor_externo": valor_externo,
                "encontrado": achou,
            })
        self.db.commit()

        encontrados = sum(1 for m in resultado_meses if m["encontrado"])
        return {
            "empresa_id": empresa_id,
            "competencia": ano_mes,
            "meses": resultado_meses,
            "encontrados": encontrados,
            "total_meses": len(meses),
            "declaracoes_encontradas": len(num_por_competencia),
            "competencias_com_declaracao": sorted(num_por_competencia.keys()),
            "erros": erros,
            # Estrutura crua do 1º CONSDECREC — pra mapear os campos de receita
            # corretos quando a extração automática falhar (debug).
            "debug_estrutura_serpro": debug_raw,
            "aviso": (
                "Campos de receita do CONSDECREC15 são best-effort (estrutura "
                "Serpro varia). Revise a grade e complete manualmente o que "
                "ficou em branco antes de calcular o DAS."
            ) if encontrados < len(meses) else None,
        }

    def corrigir_exportacao_dobrada(self, empresa_id: int | None = None) -> dict:
        """Conserta as linhas em que o 'Puxar da Receita' (parser antigo) gravou
        valor_externo = valor_interno, DOBRANDO o RBT12. Zera o valor_externo onde
        origem='receita' e externo == interno > 0.

        Seguro/idempotente: um exportador real não tem externo EXATAMENTE igual ao
        interno; e só mexe nas linhas puxadas da Receita (origem='receita'), nunca
        nas manuais. `empresa_id=None` → roda na carteira inteira."""
        stmt = select(ReceitaMensal).where(ReceitaMensal.origem == "receita")
        if empresa_id is not None:
            stmt = stmt.where(ReceitaMensal.empresa_id == empresa_id)
        corrigidas = 0
        empresas: set[int] = set()
        for r in self.db.scalars(stmt).all():
            vi = r.valor_interno or Decimal(0)
            ve = r.valor_externo or Decimal(0)
            if ve > 0 and abs(ve - vi) < Decimal("0.01"):
                r.valor_externo = Decimal(0)
                corrigidas += 1
                empresas.add(r.empresa_id)
        if corrigidas:
            self.db.commit()
        return {"linhas_corrigidas": corrigidas, "empresas_afetadas": len(empresas)}

    def _upsert(self, empresa_id: int, ano_mes: str, interno: float, externo: float, origem: str):
        existente = self.db.scalar(
            select(ReceitaMensal).where(
                ReceitaMensal.empresa_id == empresa_id,
                ReceitaMensal.ano_mes == ano_mes,
            )
        )
        if existente:
            existente.valor_interno = Decimal(str(interno))
            existente.valor_externo = Decimal(str(externo))
            existente.origem = origem
        else:
            self.db.add(ReceitaMensal(
                empresa_id=empresa_id, ano_mes=ano_mes,
                valor_interno=Decimal(str(interno)),
                valor_externo=Decimal(str(externo)), origem=origem,
            ))
