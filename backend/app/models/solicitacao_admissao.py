from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SolicitacaoAdmissao(Base):
    """Solicitação de ADMISSÃO de funcionário feita pelo CLIENTE no portal (form
    eSocial S-2200). Vai pra equipe analisar (empurrada via webhook pro PAC
    TAREFAS). Os dados do formulário ficam num JSON flexível (`dados`) — o form
    pode crescer sem migration; só os campos de BUSCA viram coluna.

    Tabela NOVA — `create_all` cria no startup (sem migration).
    """
    __tablename__ = "solicitacoes_admissao"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=False)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # nova | em_analise | concluida | cancelada
    status: Mapped[str] = mapped_column(String(20), default="nova", nullable=False, index=True)
    funcionario_nome: Mapped[str | None] = mapped_column(String(160), nullable=True)
    funcionario_cpf: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    data_admissao: Mapped[date | None] = mapped_column(Date(), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # JSON com TODOS os campos do formulário (steps 1-5) e a lista de anexos.
    dados: Mapped[str | None] = mapped_column(Text, nullable=True)
    anexos: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON [{nome, path}]
    # Entrega ao PAC TAREFAS (webhook).
    enviado_pactarefas: Mapped[bool] = mapped_column(default=False, nullable=False)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    envio_erro: Mapped[str | None] = mapped_column(String(400), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
