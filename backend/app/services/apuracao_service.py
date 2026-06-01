"""Servico de apuracao mensal (PGDAS-D Simples Nacional + extensao futura)."""
from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.apuracao import Apuracao, RegimeApuracao, StatusApuracao
from app.models.empresa import Empresa
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)


_settings = get_settings()


class ApuracaoService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    # --- Acesso ---

    def get_or_404(self, apuracao_id: int) -> Apuracao:
        apur = self.db.get(Apuracao, apuracao_id)
        if not apur:
            raise HTTPException(status_code=404, detail="Apuracao nao encontrada")
        return apur

    def get_empresa_or_404(self, empresa_id: int) -> Empresa:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa nao encontrada")
        return empresa

    def listar(
        self,
        *,
        empresa_id: int | None = None,
        ano_mes: str | None = None,
    ) -> list[Apuracao]:
        stmt = select(Apuracao).order_by(Apuracao.ano_mes.desc(), Apuracao.id.desc())
        if empresa_id:
            stmt = stmt.where(Apuracao.empresa_id == empresa_id)
        if ano_mes:
            stmt = stmt.where(Apuracao.ano_mes == ano_mes)
        return list(self.db.scalars(stmt).all())

    # --- Criacao / DRAFT ---

    def criar_draft(
        self,
        empresa_id: int,
        ano_mes: str,
        receita_bruta: float,
        receitas_segregadas: list[dict] | None = None,
    ) -> Apuracao:
        empresa = self.get_empresa_or_404(empresa_id)
        # Idempotencia: se ja existir DRAFT/TRANSMITIDA/DAS_GERADO para esta competencia,
        # atualiza ao inves de criar nova.
        existente = self.db.scalar(
            select(Apuracao).where(
                Apuracao.empresa_id == empresa_id, Apuracao.ano_mes == ano_mes,
            )
        )
        regime = RegimeApuracao.SIMPLES_NACIONAL  # MVP
        if existente:
            existente.receita_bruta = Decimal(str(receita_bruta))
            existente.receitas_segregadas = receitas_segregadas or []
            existente.regime = regime
            self.db.commit()
            self.db.refresh(existente)
            return existente
        apur = Apuracao(
            empresa_id=empresa.id,
            ano_mes=ano_mes,
            regime=regime,
            status=StatusApuracao.DRAFT,
            receita_bruta=Decimal(str(receita_bruta)),
            receitas_segregadas=receitas_segregadas or [],
        )
        self.db.add(apur)
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Transmissao PGDAS-D ---

    def transmitir(self, apuracao_id: int) -> Apuracao:
        apur = self.get_or_404(apuracao_id)
        if not apur.receita_bruta:
            raise HTTPException(
                status_code=400, detail="Receita bruta obrigatoria para transmitir.",
            )
        empresa = self.get_empresa_or_404(apur.empresa_id)
        try:
            payload = self.provider.pgdas_transmitir_declaracao(
                empresa.cnpj,
                ano_mes=apur.ano_mes,
                receita_bruta=float(apur.receita_bruta),
                receitas=apur.receitas_segregadas or [],
            )
        except IntegraContadorError as exc:
            apur.status = StatusApuracao.ERRO
            self.db.commit()
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        dados = parse_dados(payload)
        apur.numero_declaracao = dados.get("numeroDeclaracao")
        apur.recibo = dados.get("recibo")
        valor = dados.get("valorDevido")
        if valor is not None:
            apur.valor_devido = Decimal(str(valor))
        apur.transmitida_em = datetime.now(timezone.utc)
        apur.status = StatusApuracao.TRANSMITIDA
        apur.raw_declaracao = dados
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Geracao DAS ---

    def gerar_das(self, apuracao_id: int) -> Apuracao:
        apur = self.get_or_404(apuracao_id)
        if apur.status not in (StatusApuracao.TRANSMITIDA, StatusApuracao.DAS_GERADO):
            raise HTTPException(
                status_code=400,
                detail="Transmita a declaracao antes de gerar o DAS.",
            )
        empresa = self.get_empresa_or_404(apur.empresa_id)
        try:
            payload = self.provider.pgdas_gerar_das(empresa.cnpj, ano_mes=apur.ano_mes)
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        dados = parse_dados(payload)
        pdf_b64 = dados.get("pdf") or ""
        if not pdf_b64:
            raise HTTPException(status_code=502, detail="DAS sem PDF retornado.")
        # Salvar PDF
        storage_root = Path(_settings.storage_path).parent / "apuracoes"
        empresa_dir = storage_root / empresa.cnpj
        empresa_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        pdf_path = empresa_dir / f"das_{apur.ano_mes}_{ts}.pdf"
        try:
            pdf_path.write_bytes(base64.b64decode(pdf_b64))
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"PDF DAS invalido: {exc}"
            ) from exc
        apur.das_numero_documento = dados.get("numeroDocumento")
        apur.das_codigo_barras = dados.get("codigoBarras")
        apur.das_data_vencimento = dados.get("dataVencimento")
        apur.das_pdf_path = str(pdf_path)
        valor = dados.get("valorTotal")
        if valor:
            apur.valor_devido = Decimal(str(valor))
        apur.status = StatusApuracao.DAS_GERADO
        # Remove o pdf do raw para nao inflar JSON (mantem so metadados)
        apur.raw_das = {k: v for k, v in dados.items() if k != "pdf"}
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Marcacao manual de pagamento ---

    def marcar_pago(self, apuracao_id: int) -> Apuracao:
        apur = self.get_or_404(apuracao_id)
        apur.status = StatusApuracao.PAGO
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Extrato detalhado (CONSEXTRATO16) ---

    def consultar_extrato(self, apuracao_id: int) -> dict[str, Any]:
        apur = self.get_or_404(apuracao_id)
        empresa = self.get_empresa_or_404(apur.empresa_id)
        try:
            payload = self.provider.pgdas_consultar_extrato(
                empresa.cnpj, ano_mes=apur.ano_mes,
            )
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        return parse_dados(payload)

    # --- Resumo do mes (todas empresas) ---

    def resumo_mes(self, ano_mes: str) -> dict[str, Any]:
        apuracoes = self.listar(ano_mes=ano_mes)
        empresas_ativas = self.db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True))
        ).all()

        empresas_apuradas = {a.empresa_id for a in apuracoes}
        pendentes = [e for e in empresas_ativas if e.id not in empresas_apuradas]
        valor_total = sum(
            (a.valor_devido or Decimal(0)) for a in apuracoes
        )
        valor_pago = sum(
            (a.valor_devido or Decimal(0))
            for a in apuracoes
            if a.status == StatusApuracao.PAGO
        )
        return {
            "ano_mes": ano_mes,
            "total_empresas_ativas": len(empresas_ativas),
            "apuracoes_geradas": len(apuracoes),
            "pendentes": len(pendentes),
            "transmitidas": sum(1 for a in apuracoes if a.status in (
                StatusApuracao.TRANSMITIDA, StatusApuracao.DAS_GERADO, StatusApuracao.PAGO
            )),
            "das_gerados": sum(1 for a in apuracoes if a.status in (
                StatusApuracao.DAS_GERADO, StatusApuracao.PAGO
            )),
            "pagos": sum(1 for a in apuracoes if a.status == StatusApuracao.PAGO),
            "valor_devido_total": float(valor_total),
            "valor_pago": float(valor_pago),
            "empresas_pendentes": [
                {"id": e.id, "razao_social": e.razao_social, "cnpj": e.cnpj}
                for e in pendentes[:20]
            ],
        }
