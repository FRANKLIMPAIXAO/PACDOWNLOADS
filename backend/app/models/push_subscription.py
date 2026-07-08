from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PushSubscription(Base):
    """Inscrição de Web Push de UM dispositivo de um cliente do portal. É o que o
    servidor usa pra mandar a notificação (tipo WhatsApp) mesmo com o app fechado.

    Guardado por `usuario_id` (o cliente logado) — no envio, a partir do CNPJ que
    o PacChat manda no webhook, achamos a empresa, os clientes com acesso a ela e
    as inscrições deles. `endpoint` é único (uma linha por dispositivo/navegador);
    reinscrever faz upsert. Tabela NOVA — `create_all` cria no startup.

    Os campos `p256dh`/`auth` são as chaves públicas do navegador (não são segredo
    do servidor) usadas pra CIFRAR o payload pra aquele dispositivo.
    """
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    # empresa ATIVA quando inscreveu (só informativo; o envio resolve por CNPJ).
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), nullable=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
