"""Serviço da Distribuição DF-e do CT-e — puxa os conhecimentos de transporte
direto com o cert A1 (mTLS), modelo NSU, de graça.

Espelha o `dfe_distribuicao_service.py` (NFe), mas:
- usa `empresa.cte_dist_ult_nsu` como cursor;
- grava como `DocumentoFiscal` tipo=CTE;
- CT-e COMPLETO (procCTe) é salvo no disco aqui mesmo (o UploadXmlService é
  NFe-only: parseia `infNFe`, não serve pro `infCte`);
- elegíveis = ativas + cert A1, SEM excluir Focus — a fila do CT-e é SEPARADA
  da NFe (Focus consome a fila da NFe, não a do CT-e).

O CT-e entra como RECEBIDA (entrada): a empresa é a TOMADORA do frete; o
emitente é a transportadora. Importa pro crédito de ICMS/PIS-COFINS de frete.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.providers.cte_distribuicao import CteDistribuicaoProvider, DocCteDistribuido
from app.services.xml_storage import XMLStorageService

logger = logging.getLogger(__name__)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None


def _dec(s: str | None) -> Decimal | None:
    if not s:
        return None
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError):
        return None


class CteDistribuicaoService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = CteDistribuicaoProvider()
        self.storage = XMLStorageService()

    def distribuir_empresa(self, empresa_id: int, *, max_paginas: int = 15,
                           reset_nsu: bool = False) -> dict:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        if not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Empresa sem certificado A1 — a Distribuição CT-e exige o cert.",
            )
        senha = empresa.get_cert_a1_senha() or ""
        uf = (getattr(empresa, "uf", None) or "GO")
        ult_nsu = "0" if reset_nsu else (empresa.cte_dist_ult_nsu or "0")

        resumos_novos = 0
        completas_novas = 0
        eventos = 0
        paginas = 0
        cstat = ""
        motivo = ""
        concluido = False

        try:
            while paginas < max_paginas:
                res = self.provider.distribuir(
                    cnpj=empresa.cnpj, uf=uf,
                    pfx_path=empresa.cert_a1_path, pfx_senha=senha,
                    ult_nsu=ult_nsu,
                )
                cstat, motivo = res.cstat, res.motivo
                if res.cstat == "656":  # consumo indevido → para e avisa
                    break

                for doc in res.docs:
                    if doc.tipo == "CTE_COMPLETA" and doc.xml:
                        if self._salvar_completa(empresa, doc):
                            completas_novas += 1
                    elif doc.tipo == "RECEBIDA_RESUMO":
                        if self._salvar_resumo(empresa, doc):
                            resumos_novos += 1
                    elif doc.tipo == "EVENTO":
                        eventos += 1

                if res.ult_nsu and res.ult_nsu != "0":
                    ult_nsu = res.ult_nsu
                    empresa.cte_dist_ult_nsu = ult_nsu
                    self.db.commit()

                paginas += 1
                if res.cstat == "137" or not res.tem_mais:
                    concluido = True
                    break
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha na distribuição CT-e da empresa %s", empresa_id)
            raise HTTPException(status_code=502, detail=f"Distribuição CT-e falhou: {exc}")

        return {
            "empresa_id": empresa.id,
            "razao_social": empresa.razao_social,
            "ult_nsu": ult_nsu,
            "paginas": paginas,
            "concluido": concluido,
            "resumos_recebidas_novos": resumos_novos,
            "ctes_completas_novas": completas_novas,
            "eventos": eventos,
            "cstat": cstat,
            "motivo": motivo,
            "aviso": (
                "Consumo indevido (656): a SEFAZ pede pra esperar ~1h entre cargas. "
                "Tente de novo mais tarde." if cstat == "656" else None
            ),
        }

    def listar_elegiveis(self) -> list[Empresa]:
        """Empresas aptas pra Distribuição CT-e: ativas + cert A1. (Diferente da
        NFe, NÃO exclui as com Focus — a fila do CT-e é separada da NFe.)"""
        return list(self.db.scalars(
            select(Empresa).where(
                Empresa.ativo.is_(True),
                Empresa.cert_a1_path.isnot(None),
            ).order_by(Empresa.razao_social)
        ).all())

    def distribuir_lote(self, empresa_ids: list[int], *, max_paginas: int = 8) -> list[dict]:
        """Distribui um BLOCO de empresas. Erro numa não derruba o bloco."""
        resultados: list[dict] = []
        for eid in empresa_ids:
            try:
                resultados.append(self.distribuir_empresa(eid, max_paginas=max_paginas))
            except HTTPException as exc:
                resultados.append({
                    "empresa_id": eid, "ok": False,
                    "erro": str(exc.detail), "resumos_recebidas_novos": 0,
                })
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                resultados.append({
                    "empresa_id": eid, "ok": False,
                    "erro": str(exc)[:200], "resumos_recebidas_novos": 0,
                })
        return resultados

    def cron_diario(self, *, chunk: int = 2, budget_s: int = 40) -> dict:
        """Passo do cron do CT-e: avança um PEDAÇO da carteira distribuindo os CT-e.

        Espelha o cron do DF-e (NFe), mas SEM manifestação — o CT-e não exige
        Ciência da Operação. Cursor próprio em arquivo (round-robin, sem migration);
        chamado por cron EXTERNO a cada ~15 min, drena a carteira ao longo do dia.
        O 656 (consumo indevido) é esperado: o cursor avança e a empresa é
        retentada na próxima volta (o bloqueio ~1h já passou).
        """
        import json
        import time
        from app.config import get_settings

        elegiveis = self.listar_elegiveis()
        n = len(elegiveis)
        if n == 0:
            return {"processadas": [], "total_elegiveis": 0, "cursor": 0}

        cursor_path = Path(get_settings().storage_path) / "cte_cron_cursor.json"
        cursor = 0
        try:
            cursor = int(json.loads(cursor_path.read_text()).get("cursor", 0))
        except Exception:  # noqa: BLE001 — sem estado ainda = começa do 0
            cursor = 0
        cursor %= n

        inicio = time.time()
        processadas: list[dict] = []
        i = cursor
        feitas = 0
        while feitas < chunk and (time.time() - inicio) < budget_s:
            emp = elegiveis[i % n]
            item: dict = {"empresa_id": emp.id, "razao_social": emp.razao_social}
            try:
                dist = self.distribuir_empresa(emp.id, max_paginas=2)
                item["resumos"] = dist.get("resumos_recebidas_novos")
                item["completas"] = dist.get("ctes_completas_novas")
                item["cstat"] = dist.get("cstat")
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                item["dist_erro"] = str(exc)[:140]
            processadas.append(item)
            feitas += 1
            i += 1

        novo_cursor = i % n
        try:
            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            cursor_path.write_text(json.dumps({"cursor": novo_cursor}))
        except OSError:
            pass

        return {
            "total_elegiveis": n,
            "cursor_anterior": cursor,
            "cursor_novo": novo_cursor,
            "processadas": processadas,
        }

    # ------------------------------------------------------------------
    def _salvar_completa(self, empresa: Empresa, doc: DocCteDistribuido) -> bool:
        """Grava o CT-e COMPLETO (procCTe): XML no disco + DocumentoFiscal.

        Se já existe como RESUMO (sem XML), COMPLETA o registro. Se já tem XML,
        é duplicado de verdade → pula.
        """
        if not doc.chave or not doc.xml:
            return False
        existente = self.db.scalar(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa.id,
                DocumentoFiscal.tipo_documento == TipoDocumento.CTE,
                DocumentoFiscal.chave_acesso == doc.chave,
            )
        )
        if existente and existente.xml_path:
            return False  # já completo

        data_emissao = _parse_dt(doc.data_emissao) or datetime.now()
        try:
            xml_path = self.storage.save_xml(
                empresa_cnpj=empresa.cnpj,
                tipo_documento=TipoDocumento.CTE.value,
                ano=data_emissao.year,
                mes=data_emissao.month,
                chave=doc.chave,
                xml_content=doc.xml,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao salvar XML do CT-e %s: %s", doc.chave, exc)
            return False

        if existente:  # resumo virando completo
            existente.xml_path = xml_path
            existente.status = "baixado"
            if existente.data_emissao is None:
                existente.data_emissao = _parse_dt(doc.data_emissao)
            if existente.valor_total is None:
                existente.valor_total = _dec(doc.valor)
            self.db.commit()
            return True

        self.db.add(DocumentoFiscal(
            empresa_id=empresa.id,
            tipo_documento=TipoDocumento.CTE,
            chave_acesso=doc.chave,
            cnpj_emitente=doc.cnpj_emitente,
            nome_emitente=doc.nome_emitente,
            cnpj_destinatario="".join(c for c in (empresa.cnpj or "") if c.isdigit()) or None,
            nome_destinatario=empresa.razao_social,
            valor_total=_dec(doc.valor),
            data_emissao=_parse_dt(doc.data_emissao),
            status="baixado",
            xml_path=xml_path,
            origem="recebida",
            eh_saida=False,
            cancelada=(doc.situacao == "3"),
            json_original={
                "fonte": "cte_distribuicao", "nsu": doc.nsu,
                "schema": doc.schema, "cSitCTe": doc.situacao,
            },
        ))
        self.db.commit()
        return True

    def _salvar_resumo(self, empresa: Empresa, doc: DocCteDistribuido) -> bool:
        """Grava o resumo de um CT-e (resCTe) — sem XML completo ainda."""
        if not doc.chave:
            return False
        existe = self.db.scalar(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa.id,
                DocumentoFiscal.tipo_documento == TipoDocumento.CTE,
                DocumentoFiscal.chave_acesso == doc.chave,
            )
        )
        if existe:
            return False
        self.db.add(DocumentoFiscal(
            empresa_id=empresa.id,
            tipo_documento=TipoDocumento.CTE,
            chave_acesso=doc.chave,
            cnpj_emitente=doc.cnpj_emitente,
            nome_emitente=doc.nome_emitente,
            cnpj_destinatario="".join(c for c in (empresa.cnpj or "") if c.isdigit()) or None,
            nome_destinatario=empresa.razao_social,
            valor_total=_dec(doc.valor),
            data_emissao=_parse_dt(doc.data_emissao),
            status="resumo",
            xml_path="",
            origem="recebida",
            eh_saida=False,
            cancelada=(doc.situacao == "3"),
            json_original={
                "fonte": "cte_distribuicao", "nsu": doc.nsu,
                "schema": doc.schema, "cSitCTe": doc.situacao,
            },
        ))
        self.db.commit()
        return True
