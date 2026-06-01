"""Serviço de emissão de guias DCTFWeb via Integra Contador.

Suporta duas modalidades de emissão:
- ATIVA (GERARGUIA31): declaração já transmitida, gera DARF normal
- ANDAMENTO (GERARGUIAANDAMENTO313): declaração em apuração, gera DARF prévio

Categorias mais usadas no MVP:
- 40 / GERAL_MENSAL — mensal padrão (PJ Lucro Real/Presumido + Simples Anexo IV)
- 50 / PF_MENSAL — pessoa física empregador
- 41 / GERAL_13o_SALARIO — 13º (NÃO usa mesPA)
- 51 / PF_13o_SALARIO — 13º PF
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.empresa import Empresa
from app.models.guia_dctfweb import GuiaDctfweb
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)

logger = logging.getLogger(__name__)

STORAGE_DCTFWEB = Path(os.getenv("STORAGE_DCTFWEB_DIR", "./storage/guias_dctfweb")).resolve()


class GuiaDctfwebService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    # ------------------------------------------------------------------
    # Emissão
    # ------------------------------------------------------------------
    def emitir_guia_ativa(
        self,
        empresa_id: int,
        *,
        categoria: str | int = "GERAL_MENSAL",
        ano_pa: str,
        mes_pa: str | None = None,
        **kwargs: Any,
    ) -> GuiaDctfweb:
        return self._emitir(
            empresa_id,
            origem="ativa",
            categoria=categoria,
            ano_pa=ano_pa,
            mes_pa=mes_pa,
            extras=kwargs,
        )

    def emitir_guia_andamento(
        self,
        empresa_id: int,
        *,
        categoria: str | int = "GERAL_MENSAL",
        ano_pa: str,
        mes_pa: str | None = None,
        **kwargs: Any,
    ) -> GuiaDctfweb:
        return self._emitir(
            empresa_id,
            origem="andamento",
            categoria=categoria,
            ano_pa=ano_pa,
            mes_pa=mes_pa,
            extras=kwargs,
        )

    def _emitir(
        self,
        empresa_id: int,
        *,
        origem: str,
        categoria: str | int,
        ano_pa: str,
        mes_pa: str | None,
        extras: dict[str, Any],
    ) -> GuiaDctfweb:
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        if origem == "ativa":
            resp = self.provider.dctfweb_gerar_guia(
                empresa.cnpj,
                categoria=categoria,
                ano_pa=ano_pa,
                mes_pa=mes_pa,
                **extras,
            )
        elif origem == "andamento":
            resp = self.provider.dctfweb_gerar_guia_andamento(
                empresa.cnpj,
                categoria=categoria,
                ano_pa=ano_pa,
                mes_pa=mes_pa,
                **extras,
            )
        else:
            raise ValueError(f"Origem inválida: {origem!r}")

        dados = parse_dados(resp)
        pdf_b64 = (
            dados.get("PDFByteArrayBase64")
            or dados.get("pdf")
            or dados.get("docArrecadacaoPdfB64")
        )
        if not pdf_b64:
            raise IntegraContadorError(
                f"PDF não retornado pela Serpro ({origem})", codigo="SEM_PDF",
            )

        cnpj_clean = "".join(c for c in empresa.cnpj if c.isdigit())
        dest_dir = STORAGE_DCTFWEB / cnpj_clean
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        periodo_str = f"{ano_pa}{mes_pa or ''}"
        dest_path = dest_dir / f"dctfweb_{origem}_{categoria}_{periodo_str}_{ts}.pdf"
        try:
            dest_path.write_bytes(base64.b64decode(pdf_b64))
        except Exception as exc:
            raise IntegraContadorError(
                f"Falha ao salvar PDF: {exc!r}", codigo="PDF_WRITE",
            ) from exc

        guia = GuiaDctfweb(
            empresa_id=empresa_id,
            categoria=str(categoria),
            ano_pa=ano_pa,
            mes_pa=mes_pa,
            dia_pa=extras.get("dia_pa"),
            cno_afericao=extras.get("cno_afericao"),
            num_proc_reclamatoria=extras.get("num_proc_reclamatoria"),
            origem=origem,
            pdf_path=str(dest_path),
        )
        self.db.add(guia)
        self.db.commit()
        self.db.refresh(guia)
        logger.info(
            "Guia DCTFWeb emitida: id=%s empresa=%s origem=%s pdf=%s",
            guia.id, empresa_id, origem, dest_path,
        )
        return guia

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def listar_empresa(self, empresa_id: int) -> list[GuiaDctfweb]:
        stmt = (
            select(GuiaDctfweb)
            .where(GuiaDctfweb.empresa_id == empresa_id)
            .order_by(desc(GuiaDctfweb.emitida_em))
        )
        return list(self.db.scalars(stmt).all())

    def listar_todas(self, *, limit: int = 100) -> list[GuiaDctfweb]:
        stmt = (
            select(GuiaDctfweb)
            .order_by(desc(GuiaDctfweb.emitida_em))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def obter(self, guia_id: int) -> GuiaDctfweb | None:
        return self.db.get(GuiaDctfweb, guia_id)
