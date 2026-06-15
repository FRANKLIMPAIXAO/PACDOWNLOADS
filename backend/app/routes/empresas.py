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
from app.services.auth_service import get_current_admin, get_current_user
from app.services.certificado_service import (
    diagnosticar_certificado_empresa,
    remover_certificado,
    salvar_certificado_para_empresa,
)
from app.services.jettax_importer import importar_xlsx_jettax
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
def inativar_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),  # só admin pode inativar empresa
) -> Empresa:
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

    # Monta payload Focus (modelo EmpresaFocusPayload).
    # IMPORTANTE: habilita_nfe + habilita_nfce + discrimina_impostos +
    # enviar_email_destinatario sao obrigatorios pra Focus aceitar o cadastro.
    # Sem eles, /v2/empresas retorna 500 generico. Defaults conservadores:
    # - habilita_nfe=True (todo cliente PAC recebe NFes de fornecedores)
    # - habilita_nfce=False (NFCe sai sob demanda — empresa pede)
    # - habilita_cte=True (recebimento de CTe de frete, comum em ind/comercio)
    # - habilita_nfse=False (servico depende do municipio — ativa caso a caso)
    # - discrimina_impostos=True (Lei 12.741/2012 obriga)
    # - enviar_email_destinatario=True (padrao Focus pro destinatario receber XML)
    # - data_inicio_recebimento_nfe/cte = hoje (UMA VEZ definida, nao muda mais —
    #   por isso usamos a data do cadastro como ponto zero do DF-e).
    from datetime import date as _date
    hoje_iso = _date.today().isoformat()
    payload = EmpresaFocusPayload(
        cnpj=empresa.cnpj,
        nome=empresa.razao_social,
        nome_fantasia=empresa.nome_fantasia,
        inscricao_estadual=empresa.inscricao_estadual,
        inscricao_municipal=empresa.inscricao_municipal,
        fone=empresa.telefone,
        email=empresa.email_contato,
        regime_tributario=empresa.regime_tributario,
        habilita_nfe=True,
        habilita_nfce=False,
        habilita_cte=True,
        habilita_nfse=False,
        discrimina_impostos=True,
        enviar_email_destinatario=True,
        data_inicio_recebimento_nfe=hoje_iso,
        data_inicio_recebimento_cte=hoje_iso,
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


@router.post("/{empresa_id}/focus/ativar-recebimento")
def ativar_recebimento_dfe(
    empresa_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Ativa o recebimento DFe (NFe + CTe) de uma empresa JA cadastrada na Focus.

    Use pra empresas que foram cadastradas na Focus SEM `data_inicio_recebimento_nfe`
    (ex: CLAVEAUX foi criada via API direta com payload minimo). Sem essa data,
    a Focus NAO popula as NFes recebidas no DF-e — sincronizacao retorna 0
    documentos.

    A Focus exige data_inicio uma SO vez na vida da empresa — apos definida nao
    muda mais. Por isso este endpoint so tenta o PUT (se Focus rejeitar com
    'ja definida', orienta usuario a esperar a populacao automatica).

    Usa o token da PROPRIA empresa (nao o master) pra fazer o PUT.
    """
    from datetime import date as _date
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada")

    token = empresa.get_focus_token()
    if not token:
        raise HTTPException(
            status_code=400,
            detail=(
                "Empresa sem focus_token. Cadastra ela na Focus primeiro "
                "(botao Auto-cadastrar) ou importa o token manualmente."
            ),
        )

    hoje_iso = _date.today().isoformat()
    payload_focus = {
        "habilita_nfe": True,
        "habilita_cte": True,
        "data_inicio_recebimento_nfe": hoje_iso,
        "data_inicio_recebimento_cte": hoje_iso,
    }

    try:
        from app.providers.focus_nfe import FocusNFeProvider
        provider = FocusNFeProvider()
        data = provider.atualizar_empresa(token, empresa.cnpj, payload=payload_focus)
    except requests.HTTPError as exc:
        msg = str(exc)
        if "ja definida" in msg.lower() or "ja_definida" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"data_inicio_recebimento ja foi definida pra essa empresa "
                    f"na Focus e nao pode ser alterada. Focus disse: {msg[:300]}"
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Focus rejeitou a atualizacao: {msg[:500]}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado: {type(exc).__name__}: {exc}",
        ) from exc

    return {
        "ok": True,
        "empresa_id": empresa.id,
        "cnpj": empresa.cnpj,
        "data_inicio_recebimento_nfe": hoje_iso,
        "data_inicio_recebimento_cte": hoje_iso,
        "focus_response": data,
    }


@router.post("/importar-xlsx")
async def importar_empresas_xlsx(
    arquivo_xlsx: UploadFile = File(...),
    dry_run: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Importa carteira do Jettax 360 (XLSX) pro PAC.

    Multipart upload com:
    - `arquivo_xlsx`: XLSX exportado do Jettax (sheet `clientes` + tabelas dominio)
    - `?dry_run=true`: simula sem persistir (recomendado pra primeira execucao)

    UPSERT por CNPJ:
    - Empresa existente: atualiza campos (preserva os que vem None no XLSX)
    - Empresa nova: cria

    NAO importa cert .pfx — so a validade do cert. Cert real precisa ser
    subido por empresa em /empresas/{id}/certificado.

    Devolve resumo {linhas_lidas, criadas, atualizadas, erros, detalhes[...]}.
    """
    if not arquivo_xlsx.filename or not arquivo_xlsx.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo .xlsx (exportado do Jettax).",
        )
    conteudo = await arquivo_xlsx.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo XLSX vazio.")
    try:
        resultado = importar_xlsx_jettax(db, conteudo, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado: {type(exc).__name__}: {exc}",
        ) from exc
    return resultado.to_dict()


@router.get("/{empresa_id}/cert-cadeia")
def cert_cadeia(empresa_id: int, db: Session = Depends(get_db)) -> dict:
    """Diagnostica a cadeia de certificação do A1: sobe pela AIA (caIssuers) e
    reporta se dá pra baixar as intermediárias do container. Usado pra entender
    o alert 40 do robô SEFAZ (cadeia incompleta no handshake do portal)."""
    import urllib.request
    from pathlib import Path

    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7
    from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    if not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
        raise HTTPException(status_code=400, detail="Empresa sem certificado A1.")
    senha = (empresa.get_cert_a1_senha() or "").encode("utf-8")
    pfx = Path(empresa.cert_a1_path).read_bytes()
    _key, cert, additional = pkcs12.load_key_and_certificates(pfx, senha)
    if not cert:
        raise HTTPException(status_code=400, detail="PFX sem certificado.")

    def _aia(c):
        try:
            aia = c.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
            for d in aia:
                if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
                    return d.access_location.value
        except Exception:  # noqa: BLE001
            return None
        return None

    def _parse(data):
        for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
            try:
                return [loader(data)]
            except Exception:  # noqa: BLE001
                pass
        for loader in (pkcs7.load_der_pkcs7_certificates, pkcs7.load_pem_pkcs7_certificates):
            try:
                return list(loader(data))
            except Exception:  # noqa: BLE001
                pass
        return []

    passos = []
    atual = cert
    for _ in range(8):
        info = {
            "subject": atual.subject.rfc4514_string()[:120],
            "issuer": atual.issuer.rfc4514_string()[:120],
            "auto_assinado": atual.issuer == atual.subject,
        }
        if info["auto_assinado"]:
            passos.append(info)
            break
        url = _aia(atual)
        info["aia_url"] = url
        if not url:
            passos.append(info)
            break
        prox = None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pac-diag/1.0"})
            data = urllib.request.urlopen(req, timeout=10).read()
            certs = _parse(data)
            info["download"] = f"ok ({len(data)} bytes, {len(certs)} cert)"
            info["cas"] = [c.subject.rfc4514_string()[:100] for c in certs]
            prox = next((c for c in certs if c.subject == atual.issuer),
                        certs[0] if certs else None)
        except Exception as exc:  # noqa: BLE001
            info["download"] = f"FALHOU: {type(exc).__name__}: {exc}"
        passos.append(info)
        if prox is None:
            break
        atual = prox

    return {
        "empresa": empresa.razao_social,
        "cadeia_no_pfx": len(additional or []),
        "passos": passos,
    }


@router.post("/focus/diagnostico")
def diagnostico_focus(
    empresa_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Roda diagnostico em cascata na Focus pra isolar gargalo.

    3 etapas, cada uma com timeout curto pra nao estourar Traefik (~60s):
    1. HEAD api.focusnfe.com.br — testa DNS + TLS handshake (timeout 5s)
    2. GET /v2/empresas com master token — testa auth + endpoint de leitura (timeout 8s)
    3. PUT /v2/empresas/{cnpj} payload pequeno — testa endpoint de cadastro/update (timeout 10s)
       Se `empresa_id` informado e empresa tem focus_token, usa essa empresa.
       Senao, pula a etapa 3.

    Retorna JSON estruturado com tempo + status + erro de cada etapa.
    NUNCA levanta excecao — se uma etapa falha, marca `ok: false` e segue.
    """
    import time
    import requests as _rq
    from app.config import get_settings as _gs
    _s = _gs()

    resultado: dict = {"etapas": [], "ok_geral": True}

    # === Etapa 1: TLS handshake ===
    t0 = time.monotonic()
    try:
        r = _rq.head("https://api.focusnfe.com.br/", timeout=5, allow_redirects=False)
        dt = time.monotonic() - t0
        resultado["etapas"].append({
            "etapa": "1_tls_handshake",
            "ok": True,
            "tempo_segundos": round(dt, 3),
            "status_http": r.status_code,
            "info": "TLS + DNS OK",
        })
    except _rq.Timeout:
        dt = time.monotonic() - t0
        resultado["etapas"].append({
            "etapa": "1_tls_handshake", "ok": False,
            "tempo_segundos": round(dt, 3),
            "erro": "TIMEOUT 5s — Focus inacessivel ou TLS muito lento do container",
        })
        resultado["ok_geral"] = False
    except Exception as exc:  # noqa: BLE001
        dt = time.monotonic() - t0
        resultado["etapas"].append({
            "etapa": "1_tls_handshake", "ok": False,
            "tempo_segundos": round(dt, 3),
            "erro": f"{type(exc).__name__}: {exc}",
        })
        resultado["ok_geral"] = False

    # === Etapa 2: GET autenticado com master ===
    master = (_s.focus_master_token or "").strip()
    if not master:
        resultado["etapas"].append({
            "etapa": "2_get_listar_empresas", "ok": False,
            "erro": "FOCUS_MASTER_TOKEN ausente no .env do backend",
        })
        resultado["ok_geral"] = False
    else:
        t0 = time.monotonic()
        try:
            r = _rq.get(
                "https://api.focusnfe.com.br/v2/empresas",
                auth=(master, ""),
                headers={"Accept": "application/json"},
                timeout=8,
            )
            dt = time.monotonic() - t0
            body_preview = r.text[:300] if r.text else ""
            resultado["etapas"].append({
                "etapa": "2_get_listar_empresas",
                "ok": r.status_code < 400,
                "tempo_segundos": round(dt, 3),
                "status_http": r.status_code,
                "body_preview": body_preview,
            })
            if r.status_code >= 400:
                resultado["ok_geral"] = False
        except _rq.Timeout:
            dt = time.monotonic() - t0
            resultado["etapas"].append({
                "etapa": "2_get_listar_empresas", "ok": False,
                "tempo_segundos": round(dt, 3),
                "erro": "TIMEOUT 8s — GET demora demais",
            })
            resultado["ok_geral"] = False
        except Exception as exc:  # noqa: BLE001
            dt = time.monotonic() - t0
            resultado["etapas"].append({
                "etapa": "2_get_listar_empresas", "ok": False,
                "tempo_segundos": round(dt, 3),
                "erro": f"{type(exc).__name__}: {exc}",
            })
            resultado["ok_geral"] = False

    # === Etapa 3: PUT pequeno se temos empresa_id com token ===
    empresa_alvo = None
    if empresa_id:
        empresa_alvo = db.get(Empresa, empresa_id)
    if empresa_alvo and empresa_alvo.get_focus_token():
        token = empresa_alvo.get_focus_token()
        cnpj_limpo = (empresa_alvo.cnpj or "").replace(".", "").replace("/", "").replace("-", "")
        t0 = time.monotonic()
        try:
            r = _rq.put(
                f"https://api.focusnfe.com.br/v2/empresas/{cnpj_limpo}",
                auth=(token, ""),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"habilita_nfe": True},  # payload minimo idempotente
                timeout=10,
            )
            dt = time.monotonic() - t0
            body_preview = r.text[:500] if r.text else ""
            resultado["etapas"].append({
                "etapa": "3_put_empresa",
                "ok": r.status_code < 400,
                "tempo_segundos": round(dt, 3),
                "status_http": r.status_code,
                "cnpj_testado": cnpj_limpo,
                "body_preview": body_preview,
            })
            if r.status_code >= 400:
                resultado["ok_geral"] = False
        except _rq.Timeout:
            dt = time.monotonic() - t0
            resultado["etapas"].append({
                "etapa": "3_put_empresa", "ok": False,
                "tempo_segundos": round(dt, 3),
                "cnpj_testado": cnpj_limpo,
                "erro": "TIMEOUT 10s — PUT demora demais (provavel causa do 502 do auto-cadastrar)",
            })
            resultado["ok_geral"] = False
        except Exception as exc:  # noqa: BLE001
            dt = time.monotonic() - t0
            resultado["etapas"].append({
                "etapa": "3_put_empresa", "ok": False,
                "tempo_segundos": round(dt, 3),
                "cnpj_testado": cnpj_limpo,
                "erro": f"{type(exc).__name__}: {exc}",
            })
            resultado["ok_geral"] = False
    else:
        resultado["etapas"].append({
            "etapa": "3_put_empresa",
            "ok": None,  # pulado
            "info": (
                "Pulado — passe ?empresa_id=N de uma empresa que ja tem "
                "focus_token (ex: CLAVEAUX = 7)."
            ),
        })

    return resultado


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
