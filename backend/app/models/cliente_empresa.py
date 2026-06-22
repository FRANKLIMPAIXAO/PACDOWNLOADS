from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClienteEmpresa(Base):
    """Vínculo N:N entre usuário CLIENTE e empresas (um e-mail pode acessar várias
    empresas — ex.: dono de 3 empresas). A `Usuario.empresa_id` continua sendo a
    empresa PADRÃO/primária; esta tabela lista as ADICIONAIS que o mesmo login pode
    acessar. O conjunto permitido = empresa_id ∪ (linhas aqui). Tabela NOVA —
    `create_all` cria no startup (sem migration).
    """
    __tablename__ = "cliente_empresas"
    __table_args__ = (
        UniqueConstraint("usuario_id", "empresa_id", name="uq_cliente_empresa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True, nullable=False)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True, nullable=False)
