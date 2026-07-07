"""Gestão de usuários e acessos.

Níveis:
- admin (is_admin=True): acesso total, incluindo gerenciar a EQUIPE do
  escritório (criar/promover/desativar usuários) e excluir empresas.
- operador (is_admin=False): usa o sistema (subir cert, rodar robô, ver
  dados) E gerencia o ACESSO DO CLIENTE ao portal (convidar/criar/reenviar,
  vincular empresas, ver o relatório de acessos). NÃO gerencia a equipe nem
  exclui empresa.

PERMISSÃO POR ROTA: o router exige no mínimo `get_current_user` (usuário do
escritório — nunca um cliente). As rotas que mexem na EQUIPE/segurança somam
`Depends(get_current_admin)` explicitamente. Convidar/criar CLIENTE é operação
do dia a dia (operacional), então fica liberada pro operador — e é segura:
esses endpoints fixam `is_admin=False, is_cliente=True`, escopado a UMA empresa,
sem caminho de escalonamento de privilégio.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.empresa import Empresa
from app.models.usuario import Usuario
from app.schemas.auth_schema import (
    ClienteConvite,
    ClienteCreate,
    ConviteResposta,
    UsuarioAdminCreate,
    UsuarioRead,
    UsuarioUpdate,
)
from app.services.auth_service import (
    create_invite_token,
    get_current_admin,
    get_current_user,
    hash_password,
)
from app.services.email_service import enviar_email, html_convite_cliente


router = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"],
    # Mínimo: usuário do escritório (rejeita cliente). Rotas de EQUIPE/segurança
    # somam Depends(get_current_admin) abaixo; gestão de cliente fica no operador.
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[UsuarioRead])
def listar_usuarios(
    _admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[Usuario]:
    # ADMIN-only: lista a EQUIPE do escritório (inclui flags is_admin).
    return db.scalars(select(Usuario).order_by(Usuario.id)).all()


@router.get("/seguranca-diagnostico")
def seguranca_diagnostico(
    _admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Diagnóstico de segurança da CONFIG (admin-only). NÃO devolve nenhum valor
    de segredo — só flags booleanas pra detectar config fraca em produção.
    `true` em qualquer "_fraco"/"_default"/"_wildcard" = corrigir no servidor."""
    from app.services.auth_service import verify_password

    s = get_settings()
    sk = s.secret_key or ""
    # RISCO REAL: algum admin ATIVO ainda loga com 'admin123'? (testa o hash do
    # banco, não o env — assim trocar a senha pela tela já reflete aqui.)
    admins = db.scalars(
        select(Usuario).where(Usuario.is_admin.is_(True), Usuario.ativo.is_(True))
    ).all()
    admin_loga_com_123 = any(verify_password("admin123", a.senha_hash) for a in admins)
    return {
        "ambiente": s.app_env,
        "is_production": s.is_production,
        # CRÍTICO: assina JWT e cifra as senhas dos certs. Tem que ser forte e único.
        "secret_key_default_ou_fraco": sk in ("", "change-me") or len(sk) < 32,
        # true = EXISTE admin cuja senha REAL é 'admin123' (perigo de verdade).
        "senha_admin_default": admin_loga_com_123,
        # env ainda no default (cosmético: não recria admin123 num bootstrap futuro).
        "env_senha_admin_default": s.first_superuser_password == "admin123",
        "cors_wildcard": "*" in s.cors_origins,
        "mock_ligado_em_producao": s.is_production and any([
            s.use_mock_focus_nfe, s.use_mock_integra, s.use_mock_sefaz, s.use_mock_infosimples,
        ]),
        "resend_configurado": bool(s.resend_api_key),
    }


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    payload: UsuarioAdminCreate,
    _admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Usuario:
    # ADMIN-only: cria usuário da EQUIPE (pode setar is_admin) — escalonamento.
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
        senha_provisoria=True,  # admin define a provisória; o usuário troca no 1º acesso
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


def _enviar_convite(user: Usuario, empresa: Empresa) -> ConviteResposta:
    """Gera o token de definir-senha, monta o link do portal e dispara o e-mail.
    Sempre devolve o `link` (o admin pode mandar por WhatsApp tb). Se o e-mail
    falhar (ex.: RESEND_API_KEY vazia), não quebra — o link cobre."""
    token = create_invite_token(user.email)
    base = get_settings().portal_url.rstrip("/")
    link = f"{base}/definir-senha?token={token}"
    ok, detalhe = enviar_email(
        user.email,
        f"Acesso ao Portal do Cliente — {empresa.razao_social}",
        html_convite_cliente(user.nome, empresa.razao_social, link),
    )
    return ConviteResposta(
        usuario=UsuarioRead.model_validate(user),
        email_enviado=ok,
        detalhe="Convite enviado por e-mail." if ok else f"E-mail não enviado ({detalhe}). Envie o link manualmente.",
        link=link,
    )


@router.post("/cliente/convidar", response_model=ConviteResposta, status_code=status.HTTP_201_CREATED)
def convidar_cliente(payload: ClienteConvite, db: Session = Depends(get_db)) -> ConviteResposta:
    """Cria um acesso de CLIENTE SEM senha e ENVIA o convite por e-mail. O cliente
    define a própria senha pelo link (token JWT, 7 dias). Self-service estilo Jettax/Nibo."""
    if db.scalar(select(Usuario).where(Usuario.email == payload.email)):
        raise HTTPException(status_code=400, detail="Já existe um usuário com esse e-mail.")
    empresa = db.get(Empresa, payload.empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    user = Usuario(
        nome=payload.nome,
        email=payload.email,
        # senha aleatória inutilizável — o cliente só entra após definir a dele pelo link
        senha_hash=hash_password(secrets.token_urlsafe(24)),
        ativo=True,
        is_admin=False,
        is_cliente=True,
        empresa_id=empresa.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _enviar_convite(user, empresa)


@router.post("/{usuario_id}/reenviar-convite", response_model=ConviteResposta)
def reenviar_convite(usuario_id: int, db: Session = Depends(get_db)) -> ConviteResposta:
    """Reenvia o convite (novo link de definir senha) pra um cliente já cadastrado."""
    user = db.get(Usuario, usuario_id)
    if not user or not user.is_cliente or not user.empresa_id:
        raise HTTPException(status_code=404, detail="Acesso de cliente não encontrado.")
    empresa = db.get(Empresa, user.empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa do cliente não encontrada.")
    return _enviar_convite(user, empresa)


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
        # Reset pelo admin = senha PROVISÓRIA → força o usuário a trocar no próximo acesso.
        user.senha_provisoria = True

    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Multi-empresa do cliente: um e-mail pode acessar VÁRIAS empresas.
# ---------------------------------------------------------------------------
from pydantic import BaseModel, Field  # noqa: E402

from app.models.cliente_empresa import ClienteEmpresa  # noqa: E402
from app.models.portal_acesso_log import PortalAcessoLog  # noqa: E402


class ClienteEmpresasSet(BaseModel):
    empresa_ids: list[int] = Field(default_factory=list, description="Empresas ADICIONAIS (além da primária)")


@router.get("/cliente/{usuario_id}/empresas")
def listar_empresas_cliente(usuario_id: int, db: Session = Depends(get_db)) -> dict:
    """Empresas que ESTE cliente pode acessar: a primária + as adicionais."""
    user = db.get(Usuario, usuario_id)
    if not user or not user.is_cliente:
        raise HTTPException(status_code=404, detail="Acesso de cliente não encontrado.")
    adicionais = [ce.empresa_id for ce in db.scalars(
        select(ClienteEmpresa).where(ClienteEmpresa.usuario_id == user.id)
    ).all()]
    ids = list({user.empresa_id, *adicionais})
    emap = {e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_(ids))).all()}
    return {
        "primaria_id": user.empresa_id,
        "empresas": [
            {"id": i, "razao_social": emap[i].razao_social if i in emap else None,
             "cnpj": emap[i].cnpj if i in emap else None,
             "primaria": i == user.empresa_id}
            for i in ids if i is not None
        ],
    }


@router.put("/cliente/{usuario_id}/empresas")
def definir_empresas_cliente(
    usuario_id: int, payload: ClienteEmpresasSet, db: Session = Depends(get_db),
) -> dict:
    """Define as empresas ADICIONAIS que este cliente pode acessar (além da
    primária). Substitui o conjunto. A primária NUNCA sai (continua em
    `empresa_id`). Valida que cada empresa existe."""
    user = db.get(Usuario, usuario_id)
    if not user or not user.is_cliente:
        raise HTTPException(status_code=404, detail="Acesso de cliente não encontrado.")
    novos = {i for i in payload.empresa_ids if i and i != user.empresa_id}
    if novos:
        achadas = {e.id for e in db.scalars(select(Empresa).where(Empresa.id.in_(novos))).all()}
        faltando = novos - achadas
        if faltando:
            raise HTTPException(status_code=404, detail=f"Empresa(s) inexistente(s): {sorted(faltando)}")
    for ce in db.scalars(select(ClienteEmpresa).where(ClienteEmpresa.usuario_id == user.id)).all():
        db.delete(ce)
    for eid in novos:
        db.add(ClienteEmpresa(usuario_id=user.id, empresa_id=eid))
    db.commit()
    return {"primaria_id": user.empresa_id, "adicionais": sorted(novos), "total": len(novos) + 1}


class ClienteAtivoSet(BaseModel):
    ativo: bool
    motivo: str | None = Field(default=None, max_length=255)


@router.patch("/cliente/{usuario_id}/ativo", response_model=UsuarioRead)
def definir_ativo_cliente(
    usuario_id: int,
    payload: ClienteAtivoSet,
    db: Session = Depends(get_db),
) -> Usuario:
    """Ativa/INATIVA o acesso de um CLIENTE ao portal (operacional — liberado pro
    operador, não só admin). Uso: cortar acesso de cliente inadimplente ou que saiu
    do escritório, e religar depois.

    SEGURANÇA: só mexe em usuário `is_cliente=True`. Um usuário da EQUIPE
    (is_cliente=False) nunca é tocado por aqui — isso continua sendo admin-only via
    PATCH /usuarios/{id}. Assim o operador não desliga colega nem escala privilégio.

    Efeito imediato: `authenticate_user` e `_user_from_token` filtram `ativo=True`,
    então inativar BLOQUEIA o login novo E derruba os tokens já emitidos na hora."""
    user = db.get(Usuario, usuario_id)
    if not user or not user.is_cliente:
        raise HTTPException(status_code=404, detail="Acesso de cliente não encontrado.")
    user.ativo = payload.ativo
    # Guarda o motivo ao inativar; limpa ao reativar.
    user.motivo_inativacao = (payload.motivo or "").strip() or None if not payload.ativo else None
    db.commit()
    db.refresh(user)
    return user


@router.get("/clientes-acesso")
def clientes_acesso(db: Session = Depends(get_db)) -> dict:
    """Relatório de CONTROLE: lista os acessos de cliente com último login e total
    de acessos (frequência) + as empresas que cada um acessa."""
    from sqlalchemy import func

    clientes = list(db.scalars(
        select(Usuario).where(Usuario.is_cliente.is_(True)).order_by(Usuario.nome)
    ).all())
    if not clientes:
        return {"clientes": []}
    ids = [c.id for c in clientes]
    ultimos = dict(db.execute(
        select(PortalAcessoLog.usuario_id, func.max(PortalAcessoLog.criado_em))
        .where(PortalAcessoLog.usuario_id.in_(ids))
        .group_by(PortalAcessoLog.usuario_id)
    ).all())
    totais = dict(db.execute(
        select(PortalAcessoLog.usuario_id, func.count(PortalAcessoLog.id))
        .where(PortalAcessoLog.usuario_id.in_(ids), PortalAcessoLog.evento == "login")
        .group_by(PortalAcessoLog.usuario_id)
    ).all())
    adic: dict[int, list[int]] = {}
    for ce in db.scalars(select(ClienteEmpresa).where(ClienteEmpresa.usuario_id.in_(ids))).all():
        adic.setdefault(ce.usuario_id, []).append(ce.empresa_id)
    todas_emp_ids = {c.empresa_id for c in clientes if c.empresa_id} | {e for v in adic.values() for e in v}
    emap = {e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_(todas_emp_ids))).all()} if todas_emp_ids else {}

    def _nome(i: int | None) -> str | None:
        return emap[i].razao_social if i in emap else None

    out = []
    for c in clientes:
        emp_ids = list({c.empresa_id, *adic.get(c.id, [])})
        ult = ultimos.get(c.id)
        out.append({
            "id": c.id,
            "nome": c.nome,
            "email": c.email,
            "ativo": c.ativo,
            "motivo_inativacao": c.motivo_inativacao,
            "empresas": [{"id": i, "razao_social": _nome(i)} for i in emp_ids if i is not None],
            "ultimo_acesso": ult.isoformat() if ult else None,
            "total_acessos": int(totais.get(c.id, 0)),
        })
    out.sort(key=lambda x: (x["ultimo_acesso"] or ""))
    return {"clientes": out}
