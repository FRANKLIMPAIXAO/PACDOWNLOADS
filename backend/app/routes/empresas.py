import json

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.empresa import Empresa
from app.schemas.empresa_schema import (
    CertificadoUploadInfo,
    EmpresaCreate,
    EmpresaRead,
    EmpresaUpdate,
)
from app.schemas.integracao_schema import (
    EmpresaFocusPayload,
    EmpresaFocusTokenPayload,
    StatusIntegracaoEmpresaRead,
)
from app.services.auth_service import get_current_user
from app.services.certificado_service import (
    diagnosticar_certificado_empresa,
    remover_certificado,
    salvar_certificado_para_empresa,
)
from app.services.empresa_integracao import EmpresaIntegracaoService


router = APIRouter(prefix="/empresas", tags=["empresas"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=EmpresaRead, status_code=status.HTTP_201_CREATED)
def criar_empresa(payload: EmpresaCreate, db: Session = Depends(get_db)) -> Empresa:
    existing = db.scalar(select(Empresa).where(Empresa.cnpj == payload.cnpj))
    if existing:
        raise HTTPException(status_code=400, detail="Empresa ja cadastrada")
    empresa = Empresa(**payload.model_dump())
    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.get("", response_model=list[EmpresaRead])
def listar_empresas(db: Session = Depends(get_db)) -> list[Empresa]:
    return db.scalars(select(Empresa).order_by(Empresa.razao_social)).all()


@router.get("/{empresa_id}", response_model=EmpresaRead)
def obter_empresa(empresa_id: int, db: Session = Depends(get_db)) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    return empresa


@router.put("/{empresa_id}", response_model=EmpresaRead)
def atualizar_empresa(empresa_id: int, payload: EmpresaUpdate, db: Session = Depends(get_db)) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(empresa, key, value)
    db.commit()
    db.refresh(empresa)
    return empresa


@router.delete("/{empresa_id}", response_model=EmpresaRead)
def inativar_empresa(empresa_id: int, db: Session = Depends(get_db)) -> Empresa:
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    empresa.ativo = False
    db.commit()
    db.refresh(empresa)
    return empresa


# --- Integracao Focus NFe ---


@router.put("/{empresa_id}/focus")
async def cadastrar_ou_atualizar_focus(
    empresa_id: int,
    payload_json: str = Form(..., description="JSON com EmpresaFocusPayload"),
    senha_certificado: str = Form(...),
    arquivo_certificado: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Cadastra (POST /v2/empresas) ou atualiza (PUT /v2/empresas/{cnpj}) na Focus NFe.

    Multipart com `payload_json` (string JSON dos dados da empresa),
    `senha_certificado` e `arquivo_certificado` (.pfx ou .p12).
    """
    if not arquivo_certificado.filename or not arquivo_certificado.filename.lower().endswith((".pfx", ".p12")):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pfx ou .p12")
    try:
        payload_dict = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"payload_json invalido: {exc}") from exc
    payload = EmpresaFocusPayload.model_validate(payload_dict)
    content = await arquivo_certificado.read()
    # MESMO try/except do auto_cadastrar_focus pra evitar que erro Focus 500 vire
    # 502 Bad Gateway no Traefik (a HTTPException dentro do timeout do proxy é
    # responsedida antes do corte).
    try:
        return EmpresaIntegracaoService(db).sync_empresa(
            empresa_id,
            payload,
            certificado_bytes=content,
            certificado_filename=arquivo_certificado.filename,
            certificado_password=senha_certificado,
        )
    except requests.HTTPError as exc:
        msg = str(exc)
        # CNPJ ja cadastrado (Focus às vezes devolve 422, às vezes 500 genérico)
        if "ja cadastrad" in msg.lower() or "cnpj ja" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail=(
                    "Esta empresa já está cadastrada na sua conta Focus NFe. "
                    "Use a opção 'Importar token Focus' (pega o token do painel "
                    "Focus e cola aqui) em vez de tentar cadastrar de novo."
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Focus NFe rejeitou o cadastro: {msg[:500]}",
        ) from exc
    except requests.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Focus NFe demorou demais para responder (> 45s). Tenta de novo "
                "em alguns minutos — pode ter sido cadastrada mesmo assim, "
                "verifica recarregando a página."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado no cadastro Focus: {type(exc).__name__}: {exc}",
        ) from exc


@router.put("/{empresa_id}/focus/certificado")
async def renovar_certificado_focus(
    empresa_id: int,
    senha_certificado: str = Form(...),
    arquivo_certificado: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Atalho para renovar somente o certificado da empresa na Focus."""
    service = EmpresaIntegracaoService(db)
    empresa = service.get_empresa_or_404(empresa_id)
    token = empresa.get_focus_token()
    if not token:
        raise HTTPException(status_code=400, detail="Empresa sem focus_token; cadastre via PUT /focus.")
    if not arquivo_certificado.filename or not arquivo_certificado.filename.lower().endswith((".pfx", ".p12")):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pfx ou .p12")
    content = await arquivo_certificado.read()
    return service.provider.atualizar_empresa(
        token,
        empresa.cnpj,
        certificado_bytes=content,
        certificado_filename=arquivo_certificado.filename,
        certificado_password=senha_certificado,
    )


@router.put("/{empresa_id}/focus/token", response_model=EmpresaRead)
def importar_focus_token(
    empresa_id: int,
    payload: EmpresaFocusTokenPayload,
    db: Session = Depends(get_db),
) -> Empresa:
    """Importa um token Focus gerado manualmente no painel da Focus NFe."""
    return EmpresaIntegracaoService(db).importar_token(empresa_id, payload.token)


@router.post("/{empresa_id}/focus/auto-cadastrar")
def auto_cadastrar_focus(
    empresa_id: int,
    dry_run: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Cadastra a empresa no Focus NFe REUTILIZANDO o cert A1 já salvo no PAC.

    Pré-requisitos:
    - FOCUS_MASTER_TOKEN configurado no .env do backend
    - Empresa tem cert A1 cadastrado (cert_a1_path + senha cifrada)
    - Empresa NÃO tem focus_token ainda (idempotente: se já tem, retorna ele)

    Query params:
    - `?dry_run=true` — manda `?dry_run=1` pra Focus (valida o payload sem
      criar de verdade). NÃO consome cota, NÃO salva token local. Útil pra
      testar correção de bug sem gastar criação real.

    Fluxo:
    1. Lê o .pfx do disco (storage local ou volume)
    2. Decifra a senha do cert
    3. Monta payload pra Focus com dados da empresa (CNPJ, nome, endereço…)
    4. Chama EmpresaIntegracaoService.sync_empresa (POST /v2/empresas)
    5. Salva o token retornado em empresa.focus_token (cifrado) — exceto dry_run

    Devolve dict com {ja_tinha_token, token_salvo, focus_response, dry_run}.
    """
    from pathlib import Path as _Path
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    # Idempotente: se já tem token, retorna sem refazer (poupa chamada Focus).
    # Em dry_run, força a chamada mesmo com token (pra revalidar payload).
    if empresa.focus_token and not dry_run:
        return {
            "ja_tinha_token": True,
            "token_salvo": True,
            "dry_run": False,
            "mensagem": "Empresa ja tem focus_token cadastrado.",
        }

    # Validações pré-cadastro
    if not empresa.cert_a1_path:
        raise HTTPException(
            status_code=400,
            detail=(
                "Empresa sem cert A1 cadastrado. Sobe o .pfx em /empresas/{id} "
                "antes de auto-cadastrar no Focus."
            ),
        )
    pfx_path = _Path(empresa.cert_a1_path)
    if not pfx_path.exists():
        raise HTTPException(
            status_code=410,
            detail=(
                f"Cert path no banco aponta pra arquivo inexistente "
                f"({pfx_path.name}). Re-faz upload do cert."
            ),
        )

    senha_cert = empresa.get_cert_a1_senha()
    if not senha_cert:
        raise HTTPException(
            status_code=500,
            detail="Senha do cert nao decifravel (Fernet/SECRET_KEY desalinhado?)",
        )

    # Validações cadastrais mínimas (Focus exige)
    faltando = []
    if not empresa.razao_social: faltando.append("razao_social")
    if not empresa.cnpj: faltando.append("cnpj")
    if not empresa.logradouro: faltando.append("logradouro")
    if not empresa.numero: faltando.append("numero")
    if not empresa.municipio: faltando.append("municipio")
    if not empresa.uf: faltando.append("uf")
    if not empresa.cep: faltando.append("cep")
    if faltando:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Campos cadastrais faltando pra Focus: {', '.join(faltando)}. "
                "Edita a empresa e preenche antes de auto-cadastrar."
            ),
        )

    # Monta payload Focus (modelo EmpresaFocusPayload)
    payload = EmpresaFocusPayload(
        cnpj=empresa.cnpj,
        nome=empresa.razao_social,
        nome_fantasia=empresa.nome_fantasia,
        inscricao_estadual=empresa.inscricao_estadual,
        inscricao_municipal=empresa.inscricao_municipal,
        fone=empresa.telefone,
        email=empresa.email_contato,
        regime_tributario=empresa.regime_tributario,
        endereco={
            "logradouro": empresa.logradouro,
            "numero": empresa.numero or "S/N",
            "complemento": empresa.complemento,
            "bairro": empresa.bairro,
            "cidade": empresa.municipio,
            "uf": empresa.uf,
            "cep": (empresa.cep or "").replace("-", "").replace(".", ""),
        },
    )

    # Reusa o sync_empresa que já faz POST/PUT no Focus + salva token
    try:
        data = EmpresaIntegracaoService(db).sync_empresa(
            empresa_id,
            payload,
            certificado_bytes=pfx_path.read_bytes(),
            certificado_filename=pfx_path.name,
            certificado_password=senha_cert,
            dry_run=dry_run,
        )
    except requests.HTTPError as exc:
        # Vem com body Focus já incluído via custom _request — propaga detail
        msg = str(exc)
        # Detecta CNPJ já cadastrado (Focus retorna 422 com mensagem específica)
        if "ja cadastrad" in msg.lower() or "cnpj ja" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Empresa {empresa.cnpj} já está cadastrada na sua conta Focus NFe. "
                    "Use a opção 'Importar token gerado no painel Focus' em vez de "
                    "auto-cadastrar (o token dela já existe lá)."
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Focus NFe rejeitou o cadastro: {msg[:500]}",
        ) from exc
    except requests.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Focus NFe demorou demais para responder (> 45s). Recarregue a "
                "página em 30s para verificar — pode ter sido cadastrada mesmo "
                "assim. Se 'Sem token' persistir, tente de novo ou importe "
                "manualmente o token do painel Focus."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado no auto-cadastro: {type(exc).__name__}: {exc}",
        ) from exc

    # Re-fetch pra confirmar token salvo
    db.refresh(empresa)
    return {
        "ja_tinha_token": False,
        "token_salvo": bool(empresa.focus_token) and not dry_run,
        "dry_run": dry_run,
        "focus_response": data,
    }


@router.post("/focus/auto-cadastrar-todas")
def auto_cadastrar_focus_todas(db: Session = Depends(get_db)) -> dict:
    """Itera empresas ativas com cert A1 sem focus_token e auto-cadastra todas.

    Idempotente: empresas que já tem token são puladas.
    Devolve resumo: {tentadas, sucesso, ja_tinham, falhas, detalhes}.
    """
    from pathlib import Path as _Path
    empresas = db.scalars(
        select(Empresa).where(Empresa.ativo == True).order_by(Empresa.id)  # noqa: E712
    ).all()

    elegiveis = [
        e for e in empresas
        if e.cert_a1_path and _Path(e.cert_a1_path).exists() and not e.focus_token
    ]

    resultado = {
        "elegiveis": len(elegiveis),
        "sucesso": 0,
        "falhas": 0,
        "ja_tinham": sum(1 for e in empresas if e.focus_token),
        "sem_cert": sum(1 for e in empresas if e.ativo and not e.cert_a1_path),
        "detalhes": [],
    }

    for empresa in elegiveis:
        try:
            r = auto_cadastrar_focus(empresa.id, db=db)
            if r.get("token_salvo"):
                resultado["sucesso"] += 1
                resultado["detalhes"].append({
                    "empresa_id": empresa.id,
                    "cnpj": empresa.cnpj,
                    "razao_social": empresa.razao_social[:50],
                    "status": "ok",
                })
        except HTTPException as exc:
            resultado["falhas"] += 1
            resultado["detalhes"].append({
                "empresa_id": empresa.id,
                "cnpj": empresa.cnpj,
                "razao_social": empresa.razao_social[:50],
                "status": "erro",
                "erro": str(exc.detail)[:300],
            })
        except Exception as exc:  # noqa: BLE001
            resultado["falhas"] += 1
            resultado["detalhes"].append({
                "empresa_id": empresa.id,
                "cnpj": empresa.cnpj,
                "razao_social": empresa.razao_social[:50],
                "status": "erro",
                "erro": f"{type(exc).__name__}: {exc}"[:300],
            })

    return resultado


@router.get("/{empresa_id}/focus/status", response_model=StatusIntegracaoEmpresaRead)
def status_integracao_focus(empresa_id: int, db: Session = Depends(get_db)) -> StatusIntegracaoEmpresaRead:
    return EmpresaIntegracaoService(db).status_integracao(empresa_id)


# --- Certificado A1 por empresa (storage local) ---


@router.post("/{empresa_id}/certificado", response_model=CertificadoUploadInfo)
async def upload_certificado(
    empresa_id: int,
    arquivo_certificado: UploadFile = File(...),
    senha_certificado: str = Form(...),
    permitir_cnpj_diferente: bool = Form(False),
    db: Session = Depends(get_db),
) -> CertificadoUploadInfo:
    """Upload do certificado A1 (.pfx) da empresa pra storage local do sistema.

    Valida com cryptography (carrega cert + senha), extrai Subject + CNPJ,
    confere bate com `empresa.cnpj`, salva em `storage/certs/<cnpj>.pfx` e
    cifra a senha no banco via Fernet.

    Independente do cadastro na Focus. Pra cadastrar/atualizar na Focus
    use depois `PUT /empresas/{id}/focus` (ja existente).
    """
    if not arquivo_certificado.filename or not arquivo_certificado.filename.lower().endswith(
        (".pfx", ".p12")
    ):
        raise HTTPException(status_code=400, detail="Envie um arquivo .pfx ou .p12")
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    pfx_bytes = await arquivo_certificado.read()
    if not pfx_bytes:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    info = salvar_certificado_para_empresa(
        db, empresa, pfx_bytes, senha_certificado,
        permitir_cnpj_diferente=permitir_cnpj_diferente,
    )
    return CertificadoUploadInfo(
        cnpj_certificado=info.cnpj_certificado,
        subject=info.subject,
        validade_ate=info.validade_ate,
        valido_de=info.valido_de,
        bate_cnpj_empresa=info.bate_cnpj_empresa,
        salvo_em=info.salvo_em,
    )


@router.delete("/{empresa_id}/certificado")
def deletar_certificado(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Remove o .pfx do disco e limpa metadados (mantem flag focus_token)."""
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not empresa.cert_a1_path:
        raise HTTPException(status_code=404, detail="Empresa sem certificado salvo")
    remover_certificado(db, empresa)
    return {"removido": True}


@router.get("/{empresa_id}/cert/diagnostico")
def diagnosticar_cert(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Diagnostica o cert A1 salvo sem chamar nenhuma API externa.

    Use pra debugar Focus 500 / Integra 500 / qualquer falha que envolva
    cert + senha. Roda 6 checks em sequencia e devolve um dict estruturado
    com TODOS os campos preenchidos ate onde deu pra ir.

    Nao lanca erro pra estado "ruim" — devolve `ok=false` + `erro=str`. Os
    unicos 404/500 sao quando a empresa nem existe.

    Resposta tipica de cert OK:
    ```
    {
      "ok": true, "mac_ok": true, "subject": "CN=...:CNPJ,...",
      "validade_ate": "2026-12-31", "vencido": false, "dias_pra_vencer": 180,
      "cnpj_certificado": "12345...", "bate_com_empresa": true, "erro": null
    }
    ```

    Resposta tipica de senha errada (causa #1 de Focus 500):
    ```
    {"ok": false, "mac_ok": false, "erro": "PFX nao abriu... MAC verify failed"}
    ```
    """
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    d = diagnosticar_certificado_empresa(empresa)
    return {
        "ok": d.ok,
        "mac_ok": d.mac_ok,
        "path_existe": d.path_existe,
        "senha_decifravel": d.senha_decifravel,
        "subject": d.subject,
        "valido_de": d.valido_de.isoformat() if d.valido_de else None,
        "validade_ate": d.validade_ate.isoformat() if d.validade_ate else None,
        "vencido": d.vencido,
        "dias_pra_vencer": d.dias_pra_vencer,
        "cnpj_certificado": d.cnpj_certificado,
        "cnpj_empresa": d.cnpj_empresa,
        "bate_com_empresa": d.bate_com_empresa,
        "erro": d.erro,
    }


@router.get("/{empresa_id}/certificado/baixar")
def baixar_certificado_para_agente(empresa_id: int, db: Session = Depends(get_db)):
    """Devolve o .pfx + senha em CLARO da empresa.

    USO INTERNO RESTRITO: somente pelo agente PAC SEFAZ rodando em ambiente
    controlado (mesmo VPS ou via VPN). NUNCA expor publicamente sem TLS +
    auth forte.

    Retorna multipart-friendly: senha no header X-Cert-Password e bytes
    do .pfx no body como application/x-pkcs12.
    """
    from fastapi.responses import Response
    from pathlib import Path

    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")
    if not empresa.cert_a1_path:
        raise HTTPException(status_code=404, detail="Empresa sem certificado A1 cadastrado")

    p = Path(empresa.cert_a1_path)
    if not p.exists():
        raise HTTPException(
            status_code=410, detail="Cert path no banco aponta pra arquivo inexistente",
        )

    senha = empresa.get_cert_a1_senha()
    if not senha:
        raise HTTPException(
            status_code=500,
            detail="Senha do certificado nao decifravel (cofre Fernet desconfigurado)",
        )

    return Response(
        content=p.read_bytes(),
        media_type="application/x-pkcs12",
        headers={
            "Content-Disposition": f'attachment; filename="{empresa.cnpj}.pfx"',
            "X-Cert-Password": senha,
            "X-Cert-CNPJ": empresa.cnpj,
            "X-Cert-Validade-Ate": empresa.cert_a1_validade_ate.isoformat() if empresa.cert_a1_validade_ate else "",
        },
    )


# --- Busca de CNPJ via BrasilAPI (autopreenchimento do form) ---


@router.get("/_busca-cnpj/{cnpj}")
def buscar_cnpj_publico(cnpj: str) -> dict:
    """Consulta dados publicos do CNPJ via BrasilAPI (gratuita, sem token).

    Devolve um dict normalizado pronto pra autopreencher o form de cadastro
    de empresa: razao_social, nome_fantasia, cnae, endereco, telefone, etc.
    Usado APENAS pra autopreenchimento UX — nao persiste nada.
    """
    digits = "".join(c for c in cnpj if c.isdigit())
    if len(digits) != 14:
        raise HTTPException(status_code=400, detail="CNPJ deve ter 14 digitos")
    try:
        r = requests.get(
            f"https://brasilapi.com.br/api/cnpj/v1/{digits}",
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"BrasilAPI fora: {exc}") from exc
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="CNPJ nao encontrado na BrasilAPI")
    if r.status_code >= 400:
        raise HTTPException(
            status_code=502, detail=f"BrasilAPI retornou {r.status_code}: {r.text[:200]}"
        )
    raw = r.json()
    # Normaliza pro nosso schema EmpresaCreate
    return {
        "cnpj": digits,
        "razao_social": raw.get("razao_social"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "natureza_juridica_codigo": raw.get("codigo_natureza_juridica"),
        "natureza_juridica_descricao": raw.get("natureza_juridica"),
        "data_abertura": raw.get("data_inicio_atividade"),
        "telefone": raw.get("ddd_telefone_1"),
        "email_contato": raw.get("email"),
        "situacao_cadastral": (
            raw.get("descricao_situacao_cadastral") or ""
        ).upper().split(" ")[0] or None,
        # Endereco
        "cep": (raw.get("cep") or "").replace("-", "").replace(".", ""),
        "logradouro_tipo": raw.get("descricao_tipo_de_logradouro"),
        "logradouro": raw.get("logradouro"),
        "numero": raw.get("numero"),
        "complemento": raw.get("complemento"),
        "bairro": raw.get("bairro"),
        "municipio": raw.get("municipio"),
        "uf": raw.get("uf"),
        # Tributario
        "regime_tributario": "Simples Nacional" if raw.get("opcao_pelo_simples") else None,
        # Metadata extra (front pode mostrar)
        "_raw": {
            "cnae_principal": {
                "codigo": raw.get("cnae_fiscal"),
                "descricao": raw.get("cnae_fiscal_descricao"),
            },
            "porte": raw.get("porte"),
            "capital_social": raw.get("capital_social"),
            "qsa": raw.get("qsa") or [],
        },
    }
