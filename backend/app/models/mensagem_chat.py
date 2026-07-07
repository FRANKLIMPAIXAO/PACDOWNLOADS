from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MensagemChat(Base):
    """Mensagem de conversa (estilo WhatsApp) entre o ESCRITÓRIO e o CLIENTE de
    UMA empresa. A conversa é POR EMPRESA — `empresa_id` é a chave de isolamento
    multi-tenant: o portal só lê/escreve mensagens da própria empresa (empresa_id
    do TOKEN, nunca do request). Tabela NOVA — `create_all` cria no startup.

    `autor` = 'escritorio' ou 'cliente' (quem enviou). É definido pelo ENDPOINT
    (rota do escritório grava 'escritorio'; rota do portal grava 'cliente') —
    nunca vem do input, então o cliente não consegue se passar pelo escritório.

    Dois flags de leitura pra badges independentes: `lida_escritorio` (o escritório
    já viu esta msg) e `lida_cliente` (o cliente já viu). Quem ABRE a thread marca
    como lidas as mensagens do OUTRO lado.
    """
    __tablename__ = "mensagens_chat"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=False)
    # 'escritorio' | 'cliente' — quem mandou (definido pela rota, não pelo input).
    autor: Mapped[str] = mapped_column(String(12), nullable=False)
    # Quem exatamente enviou (usuário do escritório OU o cliente). Só p/ exibir o
    # nome; pode ser NULL se o usuário for removido depois.
    autor_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )
    autor_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    corpo: Mapped[str] = mapped_column(Text, nullable=False)
    lida_escritorio: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    lida_cliente: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
