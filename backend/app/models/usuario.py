from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Senha PROVISÓRIA: admin criou/resetou e o usuário tem que TROCAR no 1º acesso.
    # Enquanto True, o front bloqueia o uso até definir a senha dele.
    senha_provisoria: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # --- Portal do cliente (multi-tenant) ---
    # is_cliente=True → usuário é um CLIENTE (dono da empresa), NÃO equipe do
    # escritório. Vê SÓ a empresa dele (empresa_id) e SÓ pelo /portal — o
    # get_current_user (usado por todo endpoint do escritório) rejeita cliente.
    # Equipe do escritório: is_cliente=False, empresa_id=NULL (vê todas).
    is_cliente: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id"), nullable=True, index=True
    )
    # Motivo da inativação do CLIENTE (ex.: "inadimplente", "saiu do escritório").
    # Só descritivo pro escritório saber por que o acesso está desligado.
    motivo_inativacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
