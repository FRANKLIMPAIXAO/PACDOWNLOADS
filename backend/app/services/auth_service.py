from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.usuario import Usuario


settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_invite_token(email: str, horas: int = 168) -> str:
    """Token de CONVITE (definir senha) — JWT assinado, scope=set_senha, expira em
    7 dias por padrão. Sem coluna no banco (stateless): o set-senha valida a
    assinatura. Não loga ninguém — só autoriza criar a senha daquele e-mail."""
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=horas)
    payload = {"sub": email, "scope": "set_senha", "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def email_do_token_senha(token: str) -> str:
    """Valida o token de definir-senha (scope=set_senha) e devolve o e-mail.
    Levanta 400 se inválido/expirado/escopo errado."""
    erro = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Link inválido ou expirado. Peça um novo convite ao escritório.",
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as exc:
        raise erro from exc
    if payload.get("scope") != "set_senha" or not payload.get("sub"):
        raise erro
    return payload["sub"]


def authenticate_user(db: Session, email: str, password: str) -> Usuario | None:
    user = db.scalar(select(Usuario).where(Usuario.email == email, Usuario.ativo.is_(True)))
    if not user or not verify_password(password, user.senha_hash):
        return None
    return user


def _user_from_token(token: str, db: Session) -> Usuario:
    """Decodifica o JWT e carrega o Usuario ativo. NÃO aplica regra de papel —
    quem chama (get_current_user / get_current_cliente) decide o que aceitar."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nao autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        subject = payload.get("sub")
        if not subject:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.scalar(select(Usuario).where(Usuario.email == subject, Usuario.ativo.is_(True)))
    if not user:
        raise credentials_exception
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    """Usuário do ESCRITÓRIO (equipe). É a dependência de TODO endpoint interno.

    BLOQUEIA cliente: um token de cliente (portal) bate aqui e leva 403 — assim
    o isolamento multi-tenant é garantido num ponto só, sem precisar lembrar de
    escopar cada rota do escritório. Cliente acessa SÓ pelo /portal."""
    user = _user_from_token(token, db)
    if user.is_cliente:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta área é do escritório. Acesse pelo portal do cliente (/portal).",
        )
    return user


def get_current_cliente(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    """Usuário CLIENTE do portal. Exige is_cliente + empresa_id vinculada.

    Todo endpoint do /portal escopa pela `empresa_id` DESTE usuário (derivada do
    token, nunca do input) — o cliente não consegue pedir a empresa de outro."""
    user = _user_from_token(token, db)
    if not user.is_cliente or not user.empresa_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao portal do cliente.",
        )
    return user


def get_current_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Exige que o usuario logado seja admin. Usar em rotas administrativas
    (gestao de usuarios, exclusao de empresa, etc)."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return user
