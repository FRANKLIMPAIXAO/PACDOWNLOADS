"""Gestão de usuários — somente administradores.

Endpoints pra o admin do escritório criar/listar/desativar operadores
(funcionários). Todas as rotas exigem `get_current_admin`.

Níveis:
- admin (is_admin=True): acesso total, incluindo gestão de usuários e
  exclusão de empresas.
- operador (is_admin=False): pode usar o sistema (subir cert, rodar robô,
  ver dados) mas NÃO pode gerenciar usuários nem excluir empresas.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.schemas.auth_schema import ClienteCreate, UsuarioAdminCreate, UsuarioRead, UsuarioUpdate
from app.services.auth_service import get_current_admin, hash_password


router = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[UsuarioRead])
def listar_usuarios(db: Session = Depends(get_db)) -> list[Usuario]:
    return db.scalars(select(Usuario).order_by(Usuario.id)).all()


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def criar_usuario(payload: UsuarioAdminCreate, db: Session = Depends(get_db)) -> Usuario:
    existing = db.scalar(select(Usuario).where(Usuario.email == payload.email))
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um usuário com esse e-mail.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Senha precisa de ao menos 6 caracteres.")
    user = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_password(payload.password),
        ativo=True,
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/cliente", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def criar_acesso_cliente(payload: ClienteCreate, db: Session = Depends(get_db)) -> Usuario:
    """Cria um acesso de CLIENTE (portal) vinculado a UMA empresa.

    O cliente loga em /portal e vê SÓ os documentos dessa empresa. Nunca é
    admin, nunca acessa o escritório (get_current_user rejeita cliente)."""
    if db.scalar(select(Usuario).where(Usuario.email == payload.email)):
        raise HTTPException(status_code=400, detail="Já existe um usuário com esse e-mail.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Senha precisa de ao menos 6 caracteres.")
    empresa = db.get(Empresa, payload.empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    user = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_password(payload.password),
        ativo=True,
        is_admin=False,
        is_cliente=True,
        empresa_id=empresa.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{usuario_id}", response_model=UsuarioRead)
def atualizar_usuario(
    usuario_id: int,
    payload: UsuarioUpdate,
    admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Usuario:
    """Ativa/desativa, muda papel (admin/operador), renomeia ou reseta senha.

    Proteções:
    - Admin não pode desativar/rebaixar a SI MESMO (evita travar a conta).
    - Não pode desativar o último admin ativo.
    """
    user = db.get(Usuario, usuario_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Auto-proteção: admin mexendo na própria conta
    if user.id == admin.id:
        if payload.ativo is False:
            raise HTTPException(status_code=400, detail="Você não pode desativar a si mesmo.")
        if payload.is_admin is False:
            raise HTTPException(status_code=400, detail="Você não pode remover seu próprio acesso admin.")

    # Não deixar o sistema ficar sem nenhum admin ativo
    if (payload.is_admin is False or payload.ativo is False) and user.is_admin:
        admins_ativos = db.scalars(
            select(Usuario).where(Usuario.is_admin.is_(True), Usuario.ativo.is_(True))
        ).all()
        if len(admins_ativos) <= 1 and user.id == admins_ativos[0].id:
            raise HTTPException(
                status_code=400,
                detail="Não dá pra desativar/rebaixar o último administrador ativo.",
            )

    if payload.nome is not None:
        user.nome = payload.nome
    if payload.ativo is not None:
        user.ativo = payload.ativo
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.password is not None:
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="Senha precisa de ao menos 6 caracteres.")
        user.senha_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return user
