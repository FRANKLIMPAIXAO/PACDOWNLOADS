"""empresas: adiciona cadastro completo (IE, IM, endereco, contato, cert)

Revision ID: 20260518_0012
Revises: 20260506_0011
Create Date: 2026-05-18 12:00:00

Cadastro de empresa expandido para acomodar o modelo do mercado contabil
(equivalente JeTax 360). Adiciona:

Dados cadastrais:
- inscricao_estadual, inscricao_municipal
- natureza_juridica (codigo + descricao)
- tributacao (ex: 'ICMS Normal', 'Simples Nacional', 'Imune')
- data_abertura (RFB)
- data_inicio_sistema (quando entrou no PAC)
- telefone, whatsapp, email_contato
- situacao_cadastral (ATIVA, BAIXADA, SUSPENSA, INAPTA, NULA)

Endereco:
- cep, logradouro_tipo (Rua/Av/Tv/...), logradouro (nome),
  numero, complemento, bairro

Credenciais (.pfx armazenado em storage/certs/<cnpj>.pfx;
senha criptografada via cofre Fernet):
- cert_a1_path, cert_a1_senha_cifrada, cert_a1_validade_ate, cert_a1_subject
- prefeitura_login, prefeitura_senha_cifrada
- emissor_nacional_login, emissor_nacional_senha_cifrada
- simples_codigo_acesso_cifrado, simples_cpf_responsavel

Mantem cnpj/razao_social/municipio/uf/regime_tributario/anexo_simples/...
"""
from alembic import op
import sqlalchemy as sa


revision = "20260518_0012"
down_revision = "20260506_0011"
branch_labels = None
depends_on = None


COLUNAS = [
    # --- Cadastrais ---
    ("inscricao_estadual", sa.String(length=20)),
    ("inscricao_municipal", sa.String(length=20)),
    ("natureza_juridica_codigo", sa.String(length=10)),
    ("natureza_juridica_descricao", sa.String(length=120)),
    ("tributacao", sa.String(length=40)),
    ("data_abertura", sa.Date()),
    ("data_inicio_sistema", sa.Date()),
    ("telefone", sa.String(length=20)),
    ("whatsapp", sa.String(length=20)),
    ("email_contato", sa.String(length=120)),
    ("situacao_cadastral", sa.String(length=20)),
    # --- Endereco ---
    ("cep", sa.String(length=10)),
    ("logradouro_tipo", sa.String(length=20)),     # Rua, Av, Travessa, ...
    ("logradouro", sa.String(length=200)),         # nome da via
    ("numero", sa.String(length=20)),
    ("complemento", sa.String(length=100)),
    ("bairro", sa.String(length=80)),
    # --- Credenciais (cofre Fernet pras senhas) ---
    ("cert_a1_path", sa.String(length=300)),
    ("cert_a1_senha_cifrada", sa.String(length=300)),
    ("cert_a1_validade_ate", sa.Date()),
    ("cert_a1_subject", sa.String(length=300)),
    ("prefeitura_login", sa.String(length=80)),
    ("prefeitura_senha_cifrada", sa.String(length=300)),
    ("emissor_nacional_login", sa.String(length=80)),
    ("emissor_nacional_senha_cifrada", sa.String(length=300)),
    ("simples_codigo_acesso_cifrado", sa.String(length=300)),
    ("simples_cpf_responsavel", sa.String(length=11)),
]


def upgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        for nome, tipo in COLUNAS:
            batch.add_column(sa.Column(nome, tipo, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("empresas") as batch:
        for nome, _ in COLUNAS:
            batch.drop_column(nome)
