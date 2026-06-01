from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.schemas.auth_schema import LoginRequest, TokenResponse, UsuarioCreate
from app.services.auth_service import authenticate_user, create_access_token, get_current_user, hash_password


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register_user(payload: UsuarioCreate, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(Usuario).where(Usuario.email == payload.email))
    if existing:
        raise HTTPException(status_code=400, detail="Usuario ja cadastrado")
    user = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_password(payload.password),
        ativo=True,
        is_admin=False,
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
    return {"id": user.id, "nome": user.nome, "email": user.email, "is_admin": user.is_admin}
