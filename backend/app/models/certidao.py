from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TipoCertidao(str, Enum):
    """Tipos de certidao/comprovante de regularidade fiscal.

    FEDERAL: Relatorio SITFIS via Integra Contador (Serpro). Usado para
        controle interno mensal — sem captcha, custo ~R$ 0,03/emissao.
        Validade pratica: 60 dias.

    FEDERAL_OFICIAL: CND Conjunta RFB+PGFN, emitida no portal oficial da
        Receita Federal. Necessaria para LICITACOES, BANCOS e CONTRATOS
        PUBLICOS. Emissao via Playwright + 2captcha (ou eCNPJ A1).
        Validade: 180 dias.

    FGTS: CRF Caixa Economica (regularidade FGTS). Validade 30 dias.
    TRABALHISTA: CNDT Tribunal Superior do Trabalho. Validade 180 dias.
    ESTADUAL: CND Sefaz estadual (varia por UF). Cadastro manual no MVP.
    MUNICIPAL: CND da prefeitura. Cadastro manual no MVP.
    """
    FEDERAL = "FEDERAL"
    FEDERAL_OFICIAL = "FEDERAL_OFICIAL"
    FGTS = "FGTS"
    TRABALHISTA = "TRABALHISTA"
    ESTADUAL = "ESTADUAL"
    MUNICIPAL = "MUNICIPAL"


class Certidao(Base):
    """Certidao Negativa de Debito (CND/CRF/CNDT) cadastrada manualmente.

    O sistema controla validade e gera alertas; ao expirar/aproximar do
    vencimento, o usuario emite uma nova no portal correspondente e atualiza
    aqui (com upload de PDF opcional).
    """

    __tablename__ = "certidoes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), nullable=False)
    tipo: Mapped[TipoCertidao] = mapped_column(SqlEnum(TipoCertidao))
    numero: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_validade: Mapped[date] = mapped_column(Date, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    empresa = relationship("Empresa")

    def status(self, hoje: date | None = None) -> str:
        """Calcula status dinamicamente: VALIDA / A_VENCER (<=30d) / VENCIDA."""
        ref = hoje or date.today()
        if not self.data_validade:
            return "DESCONHECIDO"
        if self.data_validade < ref:
            return "VENCIDA"
        delta = (self.data_validade - ref).days
        if delta <= 30:
            return "A_VENCER"
        return "VALIDA"

    @property
    def dias_para_vencer(self) -> int | None:
        if not self.data_validade:
            return None
        return (self.data_validade - date.today()).days
