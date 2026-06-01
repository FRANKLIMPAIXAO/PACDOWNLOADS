"""Serviço de gestão de Parcelamentos PGFN (Dívida Ativa da União).

PGFN NÃO tem API direta:
- Serpro Integra Contador não cobre parcelamentos PGFN (só PARCSN do Simples)
- Infosimples não tem produto pra isso
- RFB tá prometendo PARC-PAEX mas ainda não saiu

Por enquanto: **CADASTRO MANUAL**. Usuário cadastra/edita/deleta os parcelamentos
PGFN da empresa via UI. Sistema só armazena, calcula percentuais, alerta no
dashboard e gera relatórios.

Fontes futuras (não implementadas):
- Parser do PDF SITFIS (Integra Contador) — SITFIS lista débitos PGFN
- Scraper REGULARIZE (Playwright + 2captcha) — caro de manter
- PARC-PAEX da RFB — aguardar disponibilidade
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.empresa import Empresa
from app.models.parcelamento_pgfn import ParcelamentoPgfn

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ParcelamentoPgfnPayload:
    """Dados pra criar/atualizar parcelamento PGFN via cadastro manual."""
    numero: str
    modalidade: str = "Parcelamento Ordinário"
    data_pedido: date | None = None
    situacao: str = "Ativo"
    valor_total: Decimal | None = None
    valor_total_pago: Decimal | None = None
    quantidade_parcelas: int | None = None
    parcelas_pagas: int | None = None


class ParcelamentoPgfnService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # CRUD manual — PGFN não tem provider automatizado hoje
    # ------------------------------------------------------------------

    def criar(self, empresa_id: int, payload: ParcelamentoPgfnPayload) -> ParcelamentoPgfn:
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        existente = self.db.scalar(
            select(ParcelamentoPgfn).where(
                ParcelamentoPgfn.empresa_id == empresa_id,
                ParcelamentoPgfn.numero == payload.numero,
            ),
        )
        if existente:
            raise ValueError(
                f"Empresa {empresa_id} já tem parcelamento com número {payload.numero!r}. "
                f"Use PUT pra atualizar (id={existente.id})."
            )

        novo = ParcelamentoPgfn(
            empresa_id=empresa_id,
            numero=payload.numero,
            modalidade=payload.modalidade or "Parcelamento Ordinário",
            data_pedido=payload.data_pedido,
            situacao=(payload.situacao or "Ativo")[:64],
            valor_total=payload.valor_total,
            valor_total_pago=payload.valor_total_pago,
            quantidade_parcelas=payload.quantidade_parcelas,
            parcelas_pagas=payload.parcelas_pagas,
        )
        self.db.add(novo)
        self.db.commit()
        self.db.refresh(novo)
        return novo

    def atualizar(
        self, parcelamento_id: int, payload: ParcelamentoPgfnPayload,
    ) -> ParcelamentoPgfn:
        p = self.db.get(ParcelamentoPgfn, parcelamento_id)
        if p is None:
            raise ValueError(f"Parcelamento {parcelamento_id} não encontrado")

        # Atualiza só os campos enviados (não-None)
        p.numero = payload.numero or p.numero
        p.modalidade = payload.modalidade or p.modalidade
        if payload.data_pedido is not None:
            p.data_pedido = payload.data_pedido
        if payload.situacao:
            p.situacao = payload.situacao[:64]
        if payload.valor_total is not None:
            p.valor_total = payload.valor_total
        if payload.valor_total_pago is not None:
            p.valor_total_pago = payload.valor_total_pago
        if payload.quantidade_parcelas is not None:
            p.quantidade_parcelas = payload.quantidade_parcelas
        if payload.parcelas_pagas is not None:
            p.parcelas_pagas = payload.parcelas_pagas
        p.sincronizado_em = datetime.now()

        self.db.commit()
        self.db.refresh(p)
        return p

    def deletar(self, parcelamento_id: int) -> None:
        p = self.db.get(ParcelamentoPgfn, parcelamento_id)
        if p is None:
            raise ValueError(f"Parcelamento {parcelamento_id} não encontrado")
        self.db.delete(p)
        self.db.commit()

    def marcar_baixado(self, parcelamento_id: int) -> ParcelamentoPgfn:
        """Marca como 'nao_listado_mais' (foi pago/baixado na PGFN), mantém histórico."""
        p = self.db.get(ParcelamentoPgfn, parcelamento_id)
        if p is None:
            raise ValueError(f"Parcelamento {parcelamento_id} não encontrado")
        p.situacao = "nao_listado_mais"
        p.sincronizado_em = datetime.now()
        self.db.commit()
        self.db.refresh(p)
        return p

    # ------------------------------------------------------------------
    # Consultas locais
    # ------------------------------------------------------------------

    def listar_empresa(self, empresa_id: int) -> list[ParcelamentoPgfn]:
        stmt = (
            select(ParcelamentoPgfn)
            .where(ParcelamentoPgfn.empresa_id == empresa_id)
            .order_by(desc(ParcelamentoPgfn.data_pedido))
        )
        return list(self.db.scalars(stmt).all())

    def listar_todos_ativos(self) -> list[ParcelamentoPgfn]:
        """Todos os parcelamentos PGFN ativos (não baixados/pagos) — dashboard."""
        stmt = (
            select(ParcelamentoPgfn)
            .where(ParcelamentoPgfn.situacao != "nao_listado_mais")
            .order_by(desc(ParcelamentoPgfn.data_pedido))
        )
        return list(self.db.scalars(stmt).all())

