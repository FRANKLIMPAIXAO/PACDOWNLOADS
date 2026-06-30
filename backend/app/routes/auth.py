from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.auth_schema import LoginRequest, TokenResponse, TrocarSenha, UsuarioCreate
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register_user(payload: UsuarioCreate, db: Session = Depends(get_db)) -> TokenResponse:
    """Cadastro PÚBLICO — habilitado APENAS quando ainda não existe nenhum
    usuário (bootstrap do primeiro admin). Depois disso, novos usuários só
    são criados por um admin via POST /usuarios.

    Isso fecha a brecha de qualquer pessoa com o link /register criar conta
    e acessar dados fiscais sensíveis de todas as empresas.
    """
    total_usuarios = db.scalar(select(func.count(Usuario.id))) or 0
    if total_usuarios > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Cadastro público desabilitado. Peça a um administrador para "
                "criar seu acesso em Configurações → Usuários."
            ),
        )
    existing = db.scalar(select(Usuario).where(Usuario.email == payload.email))
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ja cadastrado")
    user = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_password(payload.password),
        ativo=True,
        is_admin=True,  # primeiro usuário é admin (bootstrap)
    )
    db.add(user)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.email))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas")
    return TokenResponse(access_token=create_access_token(user.email))


@router.get("/me")
def me(user: Usuario = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "nome": user.nome,
        "email": user.email,
        "is_admin": user.is_admin,
        # True = senha provisória (admin resetou) → o front força trocar antes de usar.
        "senha_provisoria": user.senha_provisoria,
    }


@router.post("/trocar-senha")
def trocar_senha(
    payload: TrocarSenha,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Usuário troca a PRÓPRIA senha (1º acesso com provisória, ou voluntário).
    Confirma a senha atual, valida a nova e LIMPA a marca de provisória."""
    if not verify_password(payload.senha_atual, user.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    nova = payload.nova_senha.strip()
    if len(nova) < 6:
        raise HTTPException(status_code=400, detail="A nova senha precisa de ao menos 6 caracteres.")
    if verify_password(nova, user.senha_hash):
        raise HTTPException(status_code=400, detail="A nova senha não pode ser igual à atual.")
    user.senha_hash = hash_password(nova)
    user.senha_provisoria = False
    db.commit()
    return {"ok": True}
