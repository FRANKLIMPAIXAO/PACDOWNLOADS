from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    password: str


class UsuarioAdminCreate(BaseModel):
    """Criação de usuário por um admin (pode definir is_admin)."""
    nome: str
    email: EmailStr
    password: str
    is_admin: bool = False


class ClienteCreate(BaseModel):
    """Criação de acesso de CLIENTE (portal) por um admin. Vincula a 1 empresa."""
    nome: str
    email: EmailStr
    password: str
    empresa_id: int


class ClienteConvite(BaseModel):
    """Convite de CLIENTE por e-mail: cria o acesso SEM senha (o cliente define
    a dele pelo link). Vincula a 1 empresa."""
    nome: str
    email: EmailStr
    empresa_id: int


class DefinirSenha(BaseModel):
    """Cliente define a senha a partir do token do convite/reset."""
    token: str
    senha: str


class UsuarioRead(BaseModel):
    id: int
    nome: str
    email: EmailStr
    ativo: bool
    is_admin: bool
    is_cliente: bool = False
    empresa_id: int | None = None
    senha_provisoria: bool = False

    model_config = {"from_attributes": True}


class TrocarSenha(BaseModel):
    """Usuário troca a PRÓPRIA senha (1º acesso ou voluntário)."""
    senha_atual: str
    nova_senha: str


class ConviteResposta(BaseModel):
    """Resultado de um convite. `email_enviado=False` → usar `link` pra enviar
    manualmente (ex.: RESEND_API_KEY ainda não configurada)."""
    usuario: UsuarioRead
    email_enviado: bool
    detalhe: str
    link: str | None = None


class UsuarioUpdate(BaseModel):
    """Atualização parcial por admin. Todos opcionais."""
    nome: str | None = None
    ativo: bool | None = None
    is_admin: bool | None = None
    password: str | None = None  # reset de senha
