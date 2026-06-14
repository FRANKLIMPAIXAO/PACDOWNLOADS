from __future__ import annotations

from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.crypto import decrypt_secret, encrypt_secret


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(255), index=True)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    regime_tributario: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_cadastro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ultimo_nsu_distribuicao: Mapped[str | None] = mapped_column(String(15), nullable=True)
    # Token API por empresa retornado pela Focus NFe (POST /v2/empresas).
    # ARMAZENADO CRIPTOGRAFADO via Fernet (cofre simetrico em app.utils.crypto).
    # Use os helpers `set_focus_token`/`get_focus_token` em vez de acessar
    # `focus_token` diretamente. Nunca expor o valor decifrado em respostas.
    focus_token: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # --- Configuracao fiscal (Simples Nacional) ---
    # Anexo: I (comercio), II (industria), III (servicos comuns),
    #        IV (servicos com cessao de mao de obra), V (servicos profissionais)
    anexo_simples: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # Atividade: COMERCIO | INDUSTRIA | SERVICO
    atividade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Aliquota ISS do municipio (somente Anexo III/IV/V)
    iss_aliquota: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Folha 12m (para calculo do Fator R no Anexo V)
    folha_12m: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # --- Dados cadastrais expandidos (migration 0012) ---
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20), nullable=True)
    inscricao_municipal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    natureza_juridica_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    natureza_juridica_descricao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tributacao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_abertura: Mapped[date | None] = mapped_column(Date(), nullable=True)
    data_inicio_sistema: Mapped[date | None] = mapped_column(Date(), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_contato: Mapped[str | None] = mapped_column(String(120), nullable=True)
    situacao_cadastral: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- Endereco ---
    cep: Mapped[str | None] = mapped_column(String(10), nullable=True)
    logradouro_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # --- Credenciais ---
    # Certificado A1: arquivo .pfx em `storage/certs/<cnpj>.pfx`, senha cifrada.
    cert_a1_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cert_a1_senha_cifrada: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cert_a1_validade_ate: Mapped[date | None] = mapped_column(Date(), nullable=True)
    cert_a1_subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Último NSU sacado da Distribuição DF-e da NFe (Ambiente Nacional). Permite
    # puxar incrementalmente as recebidas+emitidas direto com o cert (sem Focus).
    nfe_dist_ult_nsu: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Último NSU sacado do ADN da NFS-e (cursor incremental, mesmo cert A1).
    nfse_adn_ult_nsu: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Logins externos (senhas TODAS cifradas via cofre Fernet)
    prefeitura_login: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prefeitura_senha_cifrada: Mapped[str | None] = mapped_column(String(300), nullable=True)
    emissor_nacional_login: Mapped[str | None] = mapped_column(String(80), nullable=True)
    emissor_nacional_senha_cifrada: Mapped[str | None] = mapped_column(String(300), nullable=True)
    simples_codigo_acesso_cifrado: Mapped[str | None] = mapped_column(String(300), nullable=True)
    simples_cpf_responsavel: Mapped[str | None] = mapped_column(String(11), nullable=True)

    documentos: Mapped[list[DocumentoFiscal]] = relationship(back_populates="empresa")
    logs: Mapped[list[ConsultaLog]] = relationship(back_populates="empresa")

    def __repr__(self) -> str:  # type: ignore[override]
        return f"<Empresa id={self.id} cnpj={self.cnpj}>"

    # --- Cofre de credenciais ---

    def set_focus_token(self, plain_token: str | None) -> None:
        """Criptografa e armazena o token Focus."""
        self.focus_token = encrypt_secret(plain_token) if plain_token else None

    def get_focus_token(self) -> str | None:
        """Retorna o token Focus em texto plano (decriptado)."""
        return decrypt_secret(self.focus_token)

    @property
    def has_focus_token(self) -> bool:
        return bool(self.focus_token)

    # --- Helpers cofre p/ outras credenciais ---

    def set_cert_a1_senha(self, plain: str | None) -> None:
        self.cert_a1_senha_cifrada = encrypt_secret(plain) if plain else None

    def get_cert_a1_senha(self) -> str | None:
        return decrypt_secret(self.cert_a1_senha_cifrada)

    def set_prefeitura_senha(self, plain: str | None) -> None:
        self.prefeitura_senha_cifrada = encrypt_secret(plain) if plain else None

    def get_prefeitura_senha(self) -> str | None:
        return decrypt_secret(self.prefeitura_senha_cifrada)

    def set_emissor_nacional_senha(self, plain: str | None) -> None:
        self.emissor_nacional_senha_cifrada = encrypt_secret(plain) if plain else None

    def get_emissor_nacional_senha(self) -> str | None:
        return decrypt_secret(self.emissor_nacional_senha_cifrada)

    def set_simples_codigo_acesso(self, plain: str | None) -> None:
        self.simples_codigo_acesso_cifrado = encrypt_secret(plain) if plain else None

    def get_simples_codigo_acesso(self) -> str | None:
        return decrypt_secret(self.simples_codigo_acesso_cifrado)

    @property
    def has_certificado_a1(self) -> bool:
        return bool(self.cert_a1_path)

    # --- Flags em portugues (usadas pelo schema EmpresaRead) ---

    @property
    def tem_focus_token(self) -> bool:
        return bool(self.focus_token)

    @property
    def tem_certificado_a1(self) -> bool:
        return bool(self.cert_a1_path)

    @property
    def tem_credenciais_prefeitura(self) -> bool:
        return bool(self.prefeitura_login and self.prefeitura_senha_cifrada)

    @property
    def tem_credenciais_emissor_nacional(self) -> bool:
        return bool(self.emissor_nacional_login and self.emissor_nacional_senha_cifrada)

    @property
    def tem_codigo_acesso_simples(self) -> bool:
        return bool(self.simples_codigo_acesso_cifrado)
