"""Orquestracao dos servicos do Integra Contador (Serpro).

Cada metodo `sync_*` faz uma chamada na API, persiste o resultado em tabela
local (idempotencia via unique constraints) e retorna um resumo do que rodou.
Os endpoints `consultar_*` lem direto do banco (rapidos, sem chamada externa).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import base64
import time
from pathlib import Path

from app.config import get_settings
from app.models.empresa import Empresa
from app.models.mensagem_ecac import MensagemEcac
from app.models.procuracao import Procuracao
from app.models.situacao_fiscal import SituacaoFiscal
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)
from app.providers._common import parse_data_emissao, parse_data_hora_serpro


def _extrair_lista_mensagens(dados: dict) -> list[dict]:
    """A resposta Serpro de MSGCONTRIBUINTE61 vem como:

        {"codigo": "00", "conteudo": [{"listaMensagens": [...], "qtdMensagens": "44", ...}]}

    Esta funcao suporta os dois formatos (com e sem `conteudo` aninhado).
    """
    conteudo = dados.get("conteudo")
    if isinstance(conteudo, list) and conteudo and isinstance(conteudo[0], dict):
        return conteudo[0].get("listaMensagens") or []
    return dados.get("listaMensagens") or []


def _extrair_detalhe_mensagem(dados: dict) -> dict:
    """Detalhe (MSGDETALHAMENTO62) tambem vem aninhado em `conteudo[0]`."""
    conteudo = dados.get("conteudo")
    if isinstance(conteudo, list) and conteudo and isinstance(conteudo[0], dict):
        return conteudo[0]
    return dados


_settings = get_settings()


@dataclass(slots=True)
class SyncCaixaPostalResultado:
    sincronizadas: int = 0
    novas: int = 0
    atualizadas: int = 0
    erros: int = 0


class IntegraContadorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    def get_empresa_or_404(self, empresa_id: int) -> Empresa:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa nao encontrada",
            )
        return empresa

    # --- Caixa Postal ---

    def sync_caixa_postal(self, empresa_id: int) -> SyncCaixaPostalResultado:
        """MSGCONTRIBUINTE61 -> persiste mensagens em `mensagens_ecac`.

        Idempotente: re-sync atualiza mensagens existentes via (empresa_id, isn_msg).
        """
        empresa = self.get_empresa_or_404(empresa_id)
        resultado = SyncCaixaPostalResultado()
        try:
            payload = self.provider.caixa_postal_listar(empresa.cnpj)
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")

        dados = parse_dados(payload)
        mensagens = _extrair_lista_mensagens(dados)
        resultado.sincronizadas = len(mensagens)

        for msg in mensagens:
            # Serpro retorna o identificador como `isn` no payload real;
            # mantemos compatibilidade com `isnMsg`/`isn_msg` por seguranca.
            isn = str(
                msg.get("isn")
                or msg.get("isnMsg")
                or msg.get("isn_msg")
                or ""
            ).strip()
            if not isn:
                resultado.erros += 1
                continue
            try:
                self._upsert_mensagem(empresa.id, isn, msg, resultado)
            except Exception:
                self.db.rollback()
                resultado.erros += 1
        return resultado

    def listar_mensagens(self, empresa_id: int, limit: int = 100) -> list[MensagemEcac]:
        empresa = self.get_empresa_or_404(empresa_id)
        stmt = (
            select(MensagemEcac)
            .where(MensagemEcac.empresa_id == empresa.id)
            .order_by(MensagemEcac.data_envio.desc().nulls_last(), MensagemEcac.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def detalhar_mensagem(self, empresa_id: int, isn_msg: str) -> MensagemEcac:
        """Busca o detalhe na API, atualiza `conteudo_html` e devolve o registro."""
        empresa = self.get_empresa_or_404(empresa_id)
        try:
            payload = self.provider.caixa_postal_detalhe(empresa.cnpj, isn_msg)
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")

        dados = parse_dados(payload)
        detalhe = _extrair_detalhe_mensagem(dados)

        mensagem = self.db.scalar(
            select(MensagemEcac).where(
                MensagemEcac.empresa_id == empresa.id,
                MensagemEcac.isn_msg == isn_msg,
            )
        )
        if not mensagem:
            mensagem = MensagemEcac(
                empresa_id=empresa.id,
                isn_msg=isn_msg,
                assunto=detalhe.get("assuntoModelo") or detalhe.get("assunto"),
                remetente=detalhe.get("descricaoOrigem") or detalhe.get("remetente"),
                data_envio=parse_data_hora_serpro(
                    detalhe.get("dataEnvio"), detalhe.get("horaEnvio"),
                ),
            )
            self.db.add(mensagem)
        mensagem.conteudo_html = (
            detalhe.get("corpoModelo")
            or detalhe.get("conteudoHtml")
            or detalhe.get("conteudo")
        )
        mensagem.raw = {**(mensagem.raw or {}), "detalhe": detalhe}
        self.db.commit()
        self.db.refresh(mensagem)
        return mensagem

    def _upsert_mensagem(
        self,
        empresa_id: int,
        isn_msg: str,
        raw: dict[str, Any],
        resultado: SyncCaixaPostalResultado,
    ) -> None:
        """Insere ou atualiza uma mensagem.

        Mapeamento Serpro -> modelo:
        - assuntoModelo / assunto -> assunto
        - descricaoOrigem / remetente -> remetente
        - dataEnvio + horaEnvio -> data_envio (datetime UTC)
        - indicadorLeitura -> indicador_leitura ("0" novo / "1" lido)
        - relevancia / indicadorRelevancia -> indicador_relevancia ("1" alta / "2" media / "3" baixa)
        """
        existente = self.db.scalar(
            select(MensagemEcac).where(
                MensagemEcac.empresa_id == empresa_id,
                MensagemEcac.isn_msg == isn_msg,
            )
        )
        assunto = raw.get("assuntoModelo") or raw.get("assunto")
        remetente = raw.get("descricaoOrigem") or raw.get("remetente")
        data_envio = parse_data_hora_serpro(
            raw.get("dataEnvio"), raw.get("horaEnvio"),
        )
        relevancia = str(raw.get("relevancia") or raw.get("indicadorRelevancia") or "")
        if existente:
            existente.assunto = assunto or existente.assunto
            existente.remetente = remetente or existente.remetente
            existente.data_envio = data_envio or existente.data_envio
            existente.indicador_leitura = (
                raw.get("indicadorLeitura") or existente.indicador_leitura
            )
            existente.indicador_relevancia = relevancia or existente.indicador_relevancia
            existente.raw = raw
            self.db.commit()
            resultado.atualizadas += 1
            return
        try:
            self.db.add(
                MensagemEcac(
                    empresa_id=empresa_id,
                    isn_msg=isn_msg,
                    assunto=assunto,
                    remetente=remetente,
                    data_envio=data_envio,
                    indicador_leitura=raw.get("indicadorLeitura"),
                    indicador_relevancia=relevancia,
                    raw=raw,
                )
            )
            self.db.commit()
            resultado.novas += 1
        except IntegrityError:
            # Race: outra thread inseriu entre o select e o commit.
            self.db.rollback()
            resultado.atualizadas += 1

    # --- Procuracao ---

    def sync_procuracao(self, empresa_id: int) -> Procuracao:
        empresa = self.get_empresa_or_404(empresa_id)
        try:
            payload = self.provider.consultar_procuracao(empresa.cnpj)
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")

        dados = parse_dados(payload)
        proc = Procuracao(
            empresa_id=empresa.id,
            cnpj_outorgante=str(dados.get("cnpjOutorgante") or empresa.cnpj),
            cnpj_outorgado=str(dados.get("cnpjOutorgado") or ""),
            data_inicio=dados.get("dataInicio"),
            data_fim=dados.get("dataFim"),
            situacao=str(dados.get("situacao") or "DESCONHECIDA").upper(),
            servicos_autorizados=dados.get("servicosAutorizados") or [],
            raw=dados,
        )
        self.db.add(proc)
        self.db.commit()
        self.db.refresh(proc)
        return proc

    def ultima_procuracao(self, empresa_id: int) -> Procuracao | None:
        empresa = self.get_empresa_or_404(empresa_id)
        return self.db.scalar(
            select(Procuracao)
            .where(Procuracao.empresa_id == empresa.id)
            .order_by(Procuracao.sincronizada_em.desc(), Procuracao.id.desc())
        )

    # --- DTE ---

    def consultar_dte(self, empresa_id: int) -> dict[str, Any]:
        empresa = self.get_empresa_or_404(empresa_id)
        try:
            payload = self.provider.dte_consultar(empresa.cnpj)
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        return parse_dados(payload)

    # --- SITFIS ---

    def gerar_situacao_fiscal(
        self, empresa_id: int, *, max_tentativas: int = 5
    ) -> SituacaoFiscal:
        """Fluxo de 2 etapas:

        1. SOLICITARPROTOCOLO91 -> protocolo (e tempo de espera).
           A Serpro tem cooldown por CNPJ. Se o protocolo retornar vazio
           (Serpro responde 200 com body vazio), aguardamos e tentamos de novo.
        2. RELATORIOSITFIS92 com o protocolo. Se a Serpro responder com
           `tempoEspera > 0`, dorme e tenta de novo (ate `max_tentativas`).

        PDF base64 retornado eh salvo em
        `<storage>/sitfis/<cnpj>/<timestamp>.pdf` e o caminho persistido em
        `situacoes_fiscais.pdf_path`.
        """
        empresa = self.get_empresa_or_404(empresa_id)

        # --- Etapa 1: obter protocolo (com retry no cooldown Serpro) ---
        # IMPORTANTE: os waits abaixo foram reduzidos pra somar < 40s no pior
        # caso, cabendo no timeout do Traefik (~60s) em prod. Se Serpro estiver
        # em cooldown prolongado, devolve 503 pedindo retry — melhor que 502
        # genérico do proxy. TODO: mover pra Celery background (task #81).
        protocolo: str | None = None
        sol_dados: dict = {}
        proto_max = 3 if _settings.use_mock_integra else 2  # era 6
        proto_wait_s = 0 if _settings.use_mock_integra else 8  # era 30
        for tentativa in range(1, proto_max + 1):
            try:
                solicitacao = self.provider.sitfis_solicitar_protocolo(empresa.cnpj)
            except IntegraContadorError as exc:
                raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
            sol_dados = parse_dados(solicitacao) or {}
            protocolo = sol_dados.get("protocoloRelatorio")
            if protocolo:
                break
            if tentativa >= proto_max:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "SITFIS em cooldown na Serpro (protocolo vazio apos "
                        f"{proto_max} tentativas). Aguarde alguns minutos e tente novamente."
                    ),
                )
            time.sleep(proto_wait_s)

        tempo_espera = int(sol_dados.get("tempoEspera") or 0)
        if tempo_espera and not _settings.use_mock_integra:
            time.sleep(min(tempo_espera, 8))  # era 30

        pdf_b64 = ""
        relatorio_dados: dict = {}
        # max_tentativas vem do parametro; pra prod reduzimos pra 2 (era ate 5)
        max_efetivo = max_tentativas if _settings.use_mock_integra else min(max_tentativas, 2)
        for tentativa in range(1, max_efetivo + 1):
            try:
                relatorio = self.provider.sitfis_emitir_relatorio(
                    empresa.cnpj, protocolo
                )
            except IntegraContadorError as exc:
                raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
            relatorio_dados = parse_dados(relatorio)
            pdf_b64 = relatorio_dados.get("pdf") or ""
            wait = int(relatorio_dados.get("tempoEspera") or 0)
            if pdf_b64:
                break
            if tentativa >= max_efetivo:
                raise HTTPException(
                    status_code=504,
                    detail=(
                        "SITFIS nao retornou PDF dentro do tempo limite. "
                        "Aguarde alguns segundos e tente novamente — o protocolo "
                        f"foi solicitado ({protocolo})."
                    ),
                )
            if not _settings.use_mock_integra:
                time.sleep(min(max(wait, 5), 8))  # era min(max(wait,5),30)

        # Salva PDF no storage
        storage_root = Path(_settings.storage_path).parent / "sitfis"
        empresa_dir = storage_root / empresa.cnpj
        empresa_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        pdf_path = empresa_dir / f"{ts}.pdf"
        try:
            pdf_path.write_bytes(base64.b64decode(pdf_b64))
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"PDF SITFIS invalido: {exc}"
            ) from exc

        # Defensivo: protocolo Serpro real eh base64 ~250 chars. Se a migration
        # 0019 (VARCHAR 80->500) nao rodou em prod, o commit estoura com
        # StringDataRightTruncation = 500 nao tratado. Truncamos pra 500 por
        # garantia + capturamos o erro de DB pra devolver 502 limpo (com CORS)
        # em vez de 500 cru.
        situacao = SituacaoFiscal(
            empresa_id=empresa.id,
            protocolo=str(protocolo)[:500],
            pdf_path=str(pdf_path),
            status="GERADO",
            raw={"solicitacao": sol_dados, "relatorio": {k: v for k, v in relatorio_dados.items() if k != "pdf"}},
        )
        self.db.add(situacao)
        try:
            self.db.commit()
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            raise HTTPException(
                status_code=502,
                detail=(
                    f"SITFIS gerado mas falhou ao salvar no banco: "
                    f"{type(exc).__name__}: {str(exc)[:300]}. "
                    "Pode ser migration pendente (alembic upgrade head)."
                ),
            ) from exc
        self.db.refresh(situacao)
        return situacao

    def ultima_situacao_fiscal(self, empresa_id: int) -> SituacaoFiscal | None:
        empresa = self.get_empresa_or_404(empresa_id)
        return self.db.scalar(
            select(SituacaoFiscal)
            .where(SituacaoFiscal.empresa_id == empresa.id)
            .order_by(SituacaoFiscal.gerada_em.desc(), SituacaoFiscal.id.desc())
        )

    def obter_situacao_fiscal(self, situacao_id: int) -> SituacaoFiscal:
        situacao = self.db.get(SituacaoFiscal, situacao_id)
        if not situacao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Situacao fiscal nao encontrada",
            )
        return situacao

    # --- Pagamentos ---

    def listar_pagamentos(
        self,
        empresa_id: int,
        data_inicio: str,
        data_fim: str,
    ) -> list[dict[str, Any]]:
        empresa = self.get_empresa_or_404(empresa_id)
        try:
            payload = self.provider.pagamentos_listar(
                empresa.cnpj, data_inicial=data_inicio, data_final=data_fim,
            )
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        dados = parse_dados(payload)
        return dados.get("pagamentos") or []

    def emitir_comprovante_pagamento(
        self, empresa_id: int, numero_documento: str
    ) -> bytes:
        """Retorna o PDF binario do comprovante (decodificado de base64)."""
        empresa = self.get_empresa_or_404(empresa_id)
        try:
            payload = self.provider.pagamentos_emitir_comprovante(
                empresa.cnpj, numero_documento,
            )
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        dados = parse_dados(payload)
        pdf_b64 = dados.get("pdf") or ""
        if not pdf_b64:
            raise HTTPException(
                status_code=502,
                detail="Comprovante nao retornado pela Serpro.",
            )
        try:
            return base64.b64decode(pdf_b64)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"PDF comprovante invalido: {exc}"
            ) from exc
