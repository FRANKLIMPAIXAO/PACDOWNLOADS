"""Service de Guias FGTS Digital via Infosimples (modo Procurador).

Fluxo de emissão (mensal):
1. `emitir_mensal(empresa_id, periodo)` chama InfosimplesProvider.fgts_emitir_guia_rapida
2. Resposta vem com valores + URL do PDF hospedado pela Infosimples
3. Baixa o PDF pra storage local (`storage/guias_fgts/{cnpj}/`)
4. Upsert em `guias_fgts` (unique por empresa+periodo)

Cache TTL pelo cache helper genérico — 7 dias (valor pode mudar com novas
admissões/demissões durante o mês).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import requests
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.empresa import Empresa
from app.models.guia_fgts import GuiaFgts
from app.providers.infosimples import (
    GuiaFgtsRapidaInfosimples,
    InfosimplesError,
    InfosimplesProdutoNaoHabilitado,
    InfosimplesProvider,
    InfosimplesSaldoInsuficiente,
)

logger = logging.getLogger(__name__)

STORAGE_FGTS = Path(os.getenv("STORAGE_FGTS_DIR", "./storage/guias_fgts")).resolve()


@dataclass(slots=True)
class EmitirFgtsResultado:
    sucesso: bool
    guia: GuiaFgts | None = None
    erro: str | None = None
    veio_do_cache: bool = False


class GuiaFgtsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = InfosimplesProvider()

    # ------------------------------------------------------------------
    # Emissão mensal
    # ------------------------------------------------------------------

    def emitir_mensal(
        self,
        empresa_id: int,
        *,
        periodo: str,  # YYYYMM
        baixar_pdf: bool = True,
    ) -> EmitirFgtsResultado:
        """Emite Guia Rápida FGTS Digital pra (empresa, periodo).

        Re-emitir mesmo periodo ATUALIZA o registro (valores podem mudar
        com admissão/demissão durante o mês).
        """
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            return EmitirFgtsResultado(sucesso=False, erro="Empresa não encontrada")

        try:
            api_result = self.provider.fgts_emitir_guia_rapida(
                empresa.cnpj, periodo=periodo,
            )
        except InfosimplesProdutoNaoHabilitado as exc:
            logger.error("FGTS Digital não habilitado: %s", exc)
            return EmitirFgtsResultado(
                sucesso=False,
                erro=(
                    "Produto 'FGTS Digital' não está habilitado na conta Infosimples. "
                    "Ative em https://infosimples.com/painel."
                ),
            )
        except InfosimplesSaldoInsuficiente as exc:
            return EmitirFgtsResultado(
                sucesso=False,
                erro=f"Sem saldo Infosimples: {exc}",
            )
        except InfosimplesError as exc:
            return EmitirFgtsResultado(
                sucesso=False, erro=f"Erro Infosimples: {exc}",
            )

        # Upsert no banco
        guia = self._upsert(empresa, periodo, api_result)

        # Baixa PDF se URL veio
        if baixar_pdf and api_result.guia_pdf_url:
            try:
                pdf_path = self._baixar_pdf(empresa.cnpj, periodo, api_result.guia_pdf_url)
                if pdf_path:
                    guia.pdf_path = str(pdf_path)
                    self.db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao baixar PDF FGTS (não bloqueia): %s", exc)

        return EmitirFgtsResultado(sucesso=True, guia=guia, veio_do_cache=False)

    # ------------------------------------------------------------------
    # Consulta de guias (histórico Infosimples)
    # ------------------------------------------------------------------

    def consultar_historico(
        self,
        empresa_id: int,
        *,
        periodo: str | None = None,
        pagina: int = 1,
    ) -> dict:
        """Consulta histórico de guias FGTS Digital (chama Infosimples)."""
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        lista = self.provider.fgts_consultar_guias(
            empresa.cnpj, periodo=periodo, pagina=pagina,
        )
        return {
            "total_guias": lista.total_guias,
            "total_paginas": lista.total_paginas,
            "pagina": lista.pagina,
            "guias": lista.guias,
            "empregador": lista.empregador,
            "procurador": lista.procurador,
        }

    # ------------------------------------------------------------------
    # Consultas locais (DB)
    # ------------------------------------------------------------------

    def listar_empresa(self, empresa_id: int) -> list[GuiaFgts]:
        stmt = (
            select(GuiaFgts)
            .where(GuiaFgts.empresa_id == empresa_id)
            .order_by(desc(GuiaFgts.periodo))
        )
        return list(self.db.scalars(stmt).all())

    def listar_todas_pendentes(self) -> list[GuiaFgts]:
        """Todas guias emitidas e ainda não pagas (dashboard global)."""
        stmt = (
            select(GuiaFgts)
            .where(GuiaFgts.situacao == "emitida")
            .order_by(GuiaFgts.data_vencimento.asc().nullslast())
        )
        return list(self.db.scalars(stmt).all())

    def marcar_paga(
        self, guia_id: int, *, data_pagamento: date | None = None,
    ) -> GuiaFgts:
        guia = self.db.get(GuiaFgts, guia_id)
        if guia is None:
            raise ValueError(f"Guia {guia_id} não encontrada")
        guia.situacao = "paga"
        guia.data_pagamento = data_pagamento or date.today()
        self.db.commit()
        self.db.refresh(guia)
        return guia

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upsert(
        self,
        empresa: Empresa,
        periodo: str,
        r: GuiaFgtsRapidaInfosimples,
    ) -> GuiaFgts:
        existente = self.db.scalar(
            select(GuiaFgts).where(
                GuiaFgts.empresa_id == empresa.id,
                GuiaFgts.periodo == periodo,
            ),
        )
        valor_total = self._d(r.valor_total)
        valor_mensal = self._d(r.valor_mensal)

        if existente:
            existente.competencia_formatada = r.competencia or existente.competencia_formatada
            if r.data_vencimento:
                existente.data_vencimento = r.data_vencimento
            if valor_total is not None:
                existente.valor_total = valor_total
            existente.valor_mensal = valor_mensal
            existente.valor_rescisorio = self._d(r.valor_rescisorio)
            existente.valor_compensatorio = self._d(r.valor_compensatorio)
            existente.valor_encargos = self._d(r.valor_encargos)
            existente.quantidade_trabalhadores = r.quantidade_trabalhadores
            if r.guia_pdf_url:
                existente.pdf_url_infosimples = r.guia_pdf_url
            # Re-emissão volta status pra 'emitida' (atualiza valores)
            if existente.situacao != "paga":
                existente.situacao = "emitida"
            self.db.commit()
            self.db.refresh(existente)
            return existente

        novo = GuiaFgts(
            empresa_id=empresa.id,
            periodo=periodo,
            competencia_formatada=r.competencia,
            data_vencimento=r.data_vencimento,
            valor_total=valor_total or Decimal("0.00"),
            valor_mensal=valor_mensal,
            valor_rescisorio=self._d(r.valor_rescisorio),
            valor_compensatorio=self._d(r.valor_compensatorio),
            valor_encargos=self._d(r.valor_encargos),
            quantidade_trabalhadores=r.quantidade_trabalhadores,
            pdf_url_infosimples=r.guia_pdf_url,
            situacao="emitida",
        )
        self.db.add(novo)
        self.db.commit()
        self.db.refresh(novo)
        return novo

    def _baixar_pdf(self, cnpj: str, periodo: str, url: str) -> Path | None:
        """Baixa o PDF da guia hospedado pela Infosimples e salva local."""
        cnpj_d = "".join(c for c in (cnpj or "") if c.isdigit())
        dest_dir = STORAGE_FGTS / cnpj_d
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = dest_dir / f"fgts_{periodo}_{ts}.pdf"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
        except requests.RequestException as exc:
            logger.warning("Falha ao baixar PDF FGTS: %s", exc)
            return None

    @staticmethod
    def _d(valor) -> Decimal | None:
        if valor is None or valor == "":
            return None
        try:
            return Decimal(str(valor))
        except Exception:
            return None
