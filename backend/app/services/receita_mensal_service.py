"""Serviço de faturamento mensal (RBT12) — manual + puxar da Receita.

O RBT12 (Receita Bruta dos 12 meses anteriores) define a alíquota efetiva do
Simples Nacional. Empresas migradas não têm histórico de NFes, então o
faturamento dos meses anteriores precisa ser informado:

1. Manual: contador digita os 12 meses (grade).
2. Puxar da Receita: via Integra Contador (CONSDECLARACAO13 + CONSDECREC15)
   — vem da fonte oficial, garante que o RBT12 bate.
"""
from __future__ import annotations

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
                    if debug_raw is None:
                        # Guarda chaves da 1ª resposta pra mapear os campos certos
                        debug_raw = {
                            "competencia": am,
                            "chaves_topo": list(dd.keys()) if isinstance(dd, dict) else str(type(dd)),
                            "amostra": _truncar(dd),
                        }
                    # Busca recursiva por campos de receita interna/externa
                    valor_interno = _achar_receita(dd, ("interno", "interna", "receitabruta", "valorreceita"))
                    valor_externo = _achar_receita(dd, ("externo", "externa", "exporta"))
                    achou = (valor_interno + valor_externo) > 0
                except IntegraContadorError as exc:
                    erros.append(f"{am}: {exc}")
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
