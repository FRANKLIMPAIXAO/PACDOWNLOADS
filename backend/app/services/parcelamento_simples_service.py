"""Serviço de gestão de Parcelamentos Simples Nacional (PARCSN ordinário).

Fluxo de sync:
1. `sync_empresa(empresa_id)` chama PEDIDOSPARC163 → lista todos os parcelamentos
2. Pra cada um, chama OBTERPARC164 → enriquece com valor_total, parcelas_pagas etc
3. Persiste em `parcelamentos_simples` (upsert por (empresa_id, numero))

Emissão de DAS de parcela:
- `emitir_das_parcela(empresa_id, parcela_ano_mes)` chama GERARDAS161 e salva PDF.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.empresa import Empresa
from app.models.parcelamento_simples import ParcelamentoSimples
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)

logger = logging.getLogger(__name__)

STORAGE_PARCSN = Path(os.getenv("STORAGE_PARCSN_DIR", "./storage/parcsn")).resolve()


@dataclass(slots=True)
class SyncParcsnResultado:
    novos: int = 0
    atualizados: int = 0
    erros: int = 0
    detalhes: list[dict] | None = None


class ParcelamentoSimplesService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def sync_empresa(self, empresa_id: int) -> SyncParcsnResultado:
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        resultado = SyncParcsnResultado(detalhes=[])

        try:
            resp = self.provider.parcsn_listar_pedidos(empresa.cnpj)
        except IntegraContadorError as exc:
            logger.error(
                "Falha PEDIDOSPARC163 empresa=%s: %s", empresa_id, exc,
            )
            resultado.erros += 1
            resultado.detalhes.append(  # type: ignore[union-attr]
                {"erro": str(exc)[:300], "etapa": "listar_pedidos"},
            )
            return resultado

        dados = parse_dados(resp)
        # Estrutura esperada: {parcelamentos: [{numero, dataDoPedido, situacao, ...}]}
        parcs = dados.get("parcelamentos") or []

        for p in parcs:
            numero = p.get("numero")
            if numero is None:
                continue
            try:
                _, foi_novo = self._upsert_pedido(empresa_id, p)
                # Enriquecer com OBTERPARC164
                try:
                    det_resp = self.provider.parcsn_obter_parcelamento(
                        empresa.cnpj, numero=int(numero),
                    )
                    det = parse_dados(det_resp)
                    self._merge_detalhe(empresa_id, int(numero), det)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Falha OBTERPARC164 cnpj=%s numero=%s: %s",
                        empresa.cnpj, numero, exc,
                    )

                if foi_novo:
                    resultado.novos += 1
                else:
                    resultado.atualizados += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha upsert parcelamento %s", p)
                resultado.erros += 1
                resultado.detalhes.append(  # type: ignore[union-attr]
                    {"erro": str(exc)[:300], "numero": numero},
                )

        self.db.commit()
        return resultado

    # ------------------------------------------------------------------
    # Emissão DAS de parcela
    # ------------------------------------------------------------------
    def emitir_das_parcela(
        self, empresa_id: int, *, parcela_ano_mes: int,
    ) -> Path:
        """Chama GERARDAS161 + salva PDF. Devolve o caminho do PDF salvo.

        `parcela_ano_mes` formato YYYYMM (Number — ex: 202503).
        """
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        resp = self.provider.parcsn_gerar_das_parcela(
            empresa.cnpj, parcela_ano_mes=parcela_ano_mes,
        )
        dados = parse_dados(resp)
        pdf_b64 = (
            dados.get("docArrecadacaoPdfB64")
            or dados.get("PDFByteArrayBase64")
            or dados.get("pdf")
        )
        if not pdf_b64:
            raise IntegraContadorError(
                "PDF não retornado pela Serpro (GERARDAS161)", codigo="SEM_PDF",
            )

        cnpj_clean = "".join(c for c in empresa.cnpj if c.isdigit())
        dest_dir = STORAGE_PARCSN / cnpj_clean
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = dest_dir / f"parcsn_{parcela_ano_mes}_{ts}.pdf"
        try:
            dest_path.write_bytes(base64.b64decode(pdf_b64))
        except Exception as exc:
            raise IntegraContadorError(
                f"Falha ao salvar PDF: {exc!r}", codigo="PDF_WRITE",
            ) from exc
        logger.info(
            "DAS PARCSN salvo: empresa=%s parcela=%s pdf=%s",
            empresa_id, parcela_ano_mes, dest_path,
        )
        return dest_path

    def listar_parcelas_geraveis(self, empresa_id: int) -> list[dict[str, Any]]:
        """Lista parcelas disponíveis pra geração (PARCELASPARAGERAR162)."""
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")
        resp = self.provider.parcsn_listar_parcelas_geraveis(empresa.cnpj)
        dados = parse_dados(resp)
        return dados.get("listaParcelas") or []

    # ------------------------------------------------------------------
    # Consultas locais
    # ------------------------------------------------------------------
    def listar_empresa(self, empresa_id: int) -> list[ParcelamentoSimples]:
        stmt = (
            select(ParcelamentoSimples)
            .where(ParcelamentoSimples.empresa_id == empresa_id)
            .order_by(desc(ParcelamentoSimples.data_pedido))
        )
        return list(self.db.scalars(stmt).all())

    def dashboard_ativos(self) -> list[ParcelamentoSimples]:
        stmt = (
            select(ParcelamentoSimples)
            .where(ParcelamentoSimples.situacao.ilike("%parcelament%"))
            .order_by(desc(ParcelamentoSimples.data_pedido))
        )
        return list(self.db.scalars(stmt).all())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _upsert_pedido(
        self, empresa_id: int, p: dict[str, Any],
    ) -> tuple[ParcelamentoSimples, bool]:
        numero = int(p["numero"])
        existente = self.db.scalar(
            select(ParcelamentoSimples).where(
                ParcelamentoSimples.empresa_id == empresa_id,
                ParcelamentoSimples.numero == numero,
            ),
        )
        data_pedido = self._d_date_ms(p.get("dataDoPedido"))
        data_situacao = self._d_date_ms(p.get("dataDaSituacao"))
        situacao = (p.get("situacao") or "")[:64] or None

        if existente:
            if data_pedido:
                existente.data_pedido = data_pedido
            if data_situacao:
                existente.data_situacao = data_situacao
            if situacao:
                existente.situacao = situacao
            existente.sincronizado_em = datetime.now()
            return existente, False

        novo = ParcelamentoSimples(
            empresa_id=empresa_id,
            modalidade="PARCSN",
            numero=numero,
            data_pedido=data_pedido,
            data_situacao=data_situacao,
            situacao=situacao,
        )
        self.db.add(novo)
        return novo, True

    def _merge_detalhe(
        self, empresa_id: int, numero: int, det: dict[str, Any],
    ) -> None:
        self.db.flush()
        p = self.db.scalar(
            select(ParcelamentoSimples).where(
                ParcelamentoSimples.empresa_id == empresa_id,
                ParcelamentoSimples.numero == numero,
            ),
        )
        if not p:
            return
        if (v := det.get("valorTotalConsolidado")) is not None:
            p.valor_total = self._d(v)
        if (v := det.get("valorTotalPago")) is not None:
            p.valor_total_pago = self._d(v)
        if (v := det.get("quantidadeParcelas")) is not None:
            p.quantidade_parcelas = int(v)
        if (v := det.get("parcelasPagas")) is not None:
            p.parcelas_pagas = int(v)

    @staticmethod
    def _d(valor: Any) -> Decimal:
        if valor is None or valor == "":
            return Decimal("0.00")
        try:
            return Decimal(str(valor))
        except Exception:
            return Decimal("0.00")

    @staticmethod
    def _d_date_ms(v: Any) -> date | None:
        """Serpro PARCSN devolve datas como int YYYYMMDD (ex: 20170112).
        Aceita também epoch ms (legacy mock) e ISO YYYY-MM-DD.
        """
        if v is None:
            return None
        try:
            s = str(v) if not isinstance(v, str) else v
            # YYYYMMDD (formato Serpro real, 8 dígitos)
            if s.isdigit() and len(s) == 8:
                return datetime.strptime(s, "%Y%m%d").date()
            # epoch ms (mock antigo, 13 dígitos)
            if s.isdigit() and len(s) >= 12:
                return datetime.fromtimestamp(int(s) / 1000).date()
            # ISO YYYY-MM-DD
            if "-" in s:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            pass
        return None
