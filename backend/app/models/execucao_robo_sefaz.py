"""Modelo de execução do robô SEFAZ-GO.

Cada disparo do agente (manual ou via cron mensal) cria uma linha aqui.
Quando termina, o status muda para `concluido` ou `erro` e as métricas
agregadas são preenchidas.

Status workflow:
    pendente → rodando → concluido | erro
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.empresa import Empresa


class ExecucaoRoboSefaz(Base):
    __tablename__ = "execucoes_robo_sefaz"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Quem disparou: "cron" (agendamento mensal) ou "manual" (botão na UI)
    disparo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # UF (preparado pra multi-UF futuro — hoje só "GO")
    uf: Mapped[str] = mapped_column(String(2), nullable=False, default="GO", index=True)

    # Status: pendente | rodando | concluido | erro
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendente", index=True,
    )

    # Janela de busca no portal
    periodo_inicio: Mapped[datetime] = mapped_column(Date, nullable=False)
    periodo_fim: Mapped[datetime] = mapped_column(Date, nullable=False)

    # Se o disparo for restrito a uma empresa específica (manual por empresa)
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    # Timestamps
    iniciado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finalizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Métricas agregadas (preenchidas ao terminar)
    total_empresas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    com_zip: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sem_notas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    erros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    persistidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Resumo bruto do agente (JSONL parseado) — uma entrada por empresa
    detalhes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Caso erro: motivo (timeout, stack trace truncado, etc.)
    motivo_erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Empresa relacionada (quando manual single-empresa)
    empresa: Mapped["Empresa | None"] = relationship(lazy="joined")

    @property
    def duracao_segundos(self) -> float | None:
        """Duração em segundos. Robusto a:
        - `finalizado_em` ou `iniciado_em` `None` → retorna `None`.
        - Mistura de datetimes naive vs aware (server_default no DB salva como
          aware; `datetime.now()` no Python salva como naive). Normaliza ambos
          pra naive antes de subtrair.
        - Valor negativo (timezone mismatch) → retorna 0 em vez de número
          negativo enganoso.
        """
        if not (self.finalizado_em and self.iniciado_em):
            return None
        ini = self.iniciado_em.replace(tzinfo=None) if self.iniciado_em.tzinfo else self.iniciado_em
        fim = self.finalizado_em.replace(tzinfo=None) if self.finalizado_em.tzinfo else self.finalizado_em
        delta = (fim - ini).total_seconds()
        return max(0.0, delta)
