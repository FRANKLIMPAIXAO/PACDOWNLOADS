from dataclasses import asdict
from datetime import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.robo_xml import RoboXMLService


def _wrap_focus_call(fn, *args, **kwargs):
    """Executa uma chamada que internamente bate na Focus, convertendo
    qualquer falha em HTTPException com mensagem JSON estruturada.

    Sem isso, exception nao-tratada vira 500 cru SEM CORS headers, o Traefik
    intercepta e devolve 502 HTML, e o frontend ve "Failed to fetch" sem
    nenhum detalhe — bug recorrente em prod (commit 132b9e7 corrigiu pro
    auto-cadastrar Focus, agora replicado aqui pros endpoints do robo).
    """
    try:
        return fn(*args, **kwargs)
    except requests.HTTPError as exc:
        # _request do FocusNFeProvider ja inclui body Focus na msg da exception
        raise HTTPException(
            status_code=502,
            detail=f"Focus NFe rejeitou a sincronizacao: {str(exc)[:500]}",
        ) from exc
    except requests.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Focus NFe demorou demais para responder. Tenta de novo com "
                "periodo menor (ex: ultimos 7 dias). Pode ter sincronizado "
                "parcialmente — recarrega /documentos."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Erro inesperado no robo: {type(exc).__name__}: {exc}",
        ) from exc


router = APIRouter(prefix="/robo", tags=["robo"], dependencies=[Depends(get_current_user)])


class RoboRequest(BaseModel):
    empresa_id: int | None = None
    data_inicio: datetime
    data_fim: datetime


def _require_empresa_id(payload: RoboRequest) -> int:
    if payload.empresa_id is None:
        raise HTTPException(status_code=422, detail="empresa_id e obrigatorio para esta operacao")
    return payload.empresa_id


@router.post("/empresa")
def executar_por_empresa(payload: RoboRequest, db: Session = Depends(get_db)) -> dict:
    """Executa o robo de distribuicao para uma empresa.

    Hoje so processa NF-es RECEBIDAS via Focus NFe. NFe/CTe/NFSe emitidas em
    outros sistemas nao sao baixaveis pela Focus.
    """
    service = RoboXMLService(db)
    return _wrap_focus_call(
        service.baixar_distribuicao_empresa_completa,
        _require_empresa_id(payload), payload.data_inicio, payload.data_fim,
    )


@router.post("/multiempresas")
def executar_multiempresas(payload: RoboRequest, db: Session = Depends(get_db)) -> dict:
    service = RoboXMLService(db)
    return _wrap_focus_call(
        service.baixar_distribuicao_multiempresas,
        payload.data_inicio, payload.data_fim,
    )


@router.post("/distribuicao")
def executar_distribuicao(payload: RoboRequest, db: Session = Depends(get_db)) -> dict:
    """Baixa NF-es RECEBIDAS contra o CNPJ da empresa via Focus NFe.

    Pre-requisito: empresa com `focus_token` salvo. Janela SEFAZ: 90 dias.
    """
    service = RoboXMLService(db)
    resultado = _wrap_focus_call(
        service.baixar_distribuicao_empresa,
        _require_empresa_id(payload), payload.data_inicio, payload.data_fim,
    )
    return asdict(resultado)


@router.post("/manifestar")
def executar_manifestacao(
    empresa_id: int,
    aguardar_sync_segundos: int = 30,
    db: Session = Depends(get_db),
) -> dict:
    """Manifesta (Ciencia da Operacao) todas as NFes recebidas da empresa.

    Apos manifestar, aguarda sync da Focus com SEFAZ e baixa:
    - XML completo (procNFe) — substitui o resNFe (resumo) salvo antes
    - DANFE PDF — salvo ao lado do XML como `<chave>.pdf`

    Pre-requisito: empresa com `focus_token` salvo e NFes ja listadas pelo robo.
    """
    service = RoboXMLService(db)
    resultado = service.manifestar_e_baixar_pdfs(
        empresa_id, aguardar_sync_segundos=aguardar_sync_segundos,
    )
    return resultado.to_dict()


class ManifestarUmaRequest(BaseModel):
    documento_id: int
    tipo: str = "ciencia"  # ciencia | confirmacao | desconhecimento | nao_realizada


@router.post("/verificar-canceladas")
def executar_verificacao_canceladas(
    empresa_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Varre XMLs locais e marca como cancelada quando detectar evento
    `procEventoNFe descEvento=Cancelamento` no conteudo XML.

    Util pra empresas com XMLs ja baixados (antes da feature de deteccao).
    Pass `empresa_id` pra filtrar, ou omita pra varrer todas.
    """
    return RoboXMLService(db).verificar_canceladas(empresa_id)


@router.post("/manifestar-uma")
def manifestar_um_documento(
    payload: ManifestarUmaRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Manifesta UM documento especifico pela id local.

    Tipos validos Focus: ciencia, confirmacao, desconhecimento, nao_realizada.

    Tenta tambem baixar XML completo + DANFE PDF imediatamente. Se a Focus
    ainda nao sincronizou com a SEFAZ, retorna `pdf_baixado=False`,
    `xml_atualizado=False` — usuario chama novamente daqui alguns minutos.
    """
    service = RoboXMLService(db)
    try:
        return service.manifestar_documento(payload.documento_id, tipo=payload.tipo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
