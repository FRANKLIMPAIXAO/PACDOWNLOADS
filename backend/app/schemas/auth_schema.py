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


class UsuarioRead(BaseModel):
    id: int
    nome: str
    email: EmailStr
    ativo: bool
    is_admin: bool
    is_cliente: bool = False
    empresa_id: int | None = None

    model_config = {"from_attributes": True}


class UsuarioUpdate(BaseModel):
    """Atualização parcial por admin. Todos opcionais."""
    nome: str | None = None
    ativo: bool | None = None
    is_admin: bool | None = None
    password: str | None = None  # reset de senha
