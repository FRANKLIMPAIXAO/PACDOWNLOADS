from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import get_current_user
from app.services.robo_xml import RoboXMLService


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
    return service.baixar_distribuicao_empresa_completa(
        _require_empresa_id(payload), payload.data_inicio, payload.data_fim
    )


@router.post("/multiempresas")
def executar_multiempresas(payload: RoboRequest, db: Session = Depends(get_db)) -> dict:
    service = RoboXMLService(db)
    return service.baixar_distribuicao_multiempresas(payload.data_inicio, payload.data_fim)


@router.post("/distribuicao")
def executar_distribuicao(payload: RoboRequest, db: Session = Depends(get_db)) -> dict:
    """Baixa NF-es RECEBIDAS contra o CNPJ da empresa via Focus NFe.

    Pre-requisito: empresa com `focus_token` salvo. Janela SEFAZ: 90 dias.
    """
    service = RoboXMLService(db)
    return asdict(service.baixar_distribuicao_empresa(
        _require_empresa_id(payload), payload.data_inicio, payload.data_fim
    ))


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
