"""Serviço da Distribuição DF-e da NFe — puxa as notas direto com o cert A1.

Orquestra o loop de NSU: chama o provider em páginas (até ~50 docs cada) até
zerar o backlog (maxNSU == ultNSU), persistindo:
- NFE_COMPLETA (procNFe) → importa via UploadXmlService (parse + dedup + disco).
- RECEBIDA_RESUMO (resNFe) → grava DocumentoFiscal "resumo" (sem XML; o XML
  completo só vem após MANIFESTAÇÃO — fase 2). Já mostra chave/emitente/valor.

Guarda o ultNSU em `empresa.nfe_dist_ult_nsu` pra continuar de onde parou.
SEM custo por nota (≠ Focus).
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.providers.nfe_distribuicao import NFeDistribuicaoProvider
from app.providers.nfe_manifestacao import NFeManifestacaoProvider
from app.services.upload_xml_service import UploadXmlService

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


class DfeDistribuicaoService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = NFeDistribuicaoProvider()
        self.upload = UploadXmlService(db)

    def distribuir_empresa(self, empresa_id: int, *, max_paginas: int = 15) -> dict:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        if not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Empresa sem certificado A1 — a Distribuição DF-e exige o cert.",
            )
        senha = empresa.get_cert_a1_senha() or ""
        uf = (getattr(empresa, "uf", None) or "GO")
        ult_nsu = empresa.nfe_dist_ult_nsu or "0"

        resumos_novos = 0
        completas_novas = 0
        eventos = 0
        paginas = 0
        cstat = ""
        motivo = ""
        concluido = False  # True quando drenou tudo (137 ou sem mais backlog)

        try:
            while paginas < max_paginas:
                res = self.provider.distribuir(
                    cnpj=empresa.cnpj, uf=uf,
                    pfx_path=empresa.cert_a1_path, pfx_senha=senha,
                    ult_nsu=ult_nsu,
                )
                cstat, motivo = res.cstat, res.motivo
                # 656 = consumo indevido (chamou demais) → para e avisa
                if res.cstat == "656":
                    break

                for doc in res.docs:
                    if doc.tipo == "NFE_COMPLETA" and doc.xml:
                        r = self.upload.processar_xmls(
                            [(f"{doc.chave or doc.nsu}.xml", doc.xml.encode("utf-8"))],
                            empresa_id_fallback=empresa.id,
                        )
                        completas_novas += r.persistidos
                    elif doc.tipo == "RECEBIDA_RESUMO":
                        if self._salvar_resumo(empresa, doc):
                            resumos_novos += 1
                    elif doc.tipo == "EVENTO":
                        eventos += 1

                # Avança o NSU e persiste (continua daí na próxima vez)
                if res.ult_nsu and res.ult_nsu != "0":
                    ult_nsu = res.ult_nsu
                    empresa.nfe_dist_ult_nsu = ult_nsu
                    self.db.commit()

                paginas += 1
                # 137 = nenhum doc; sem mais backlog → drenou tudo
                if res.cstat == "137" or not res.tem_mais:
                    concluido = True
                    break
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha na distribuição DF-e da empresa %s", empresa_id)
            raise HTTPException(status_code=502, detail=f"Distribuição DF-e falhou: {exc}")

        return {
            "empresa_id": empresa.id,
            "razao_social": empresa.razao_social,
            "ult_nsu": ult_nsu,
            "paginas": paginas,
            "concluido": concluido,
            "resumos_recebidas_novos": resumos_novos,
            "nfes_completas_novas": completas_novas,
            "eventos": eventos,
            "cstat": cstat,
            "motivo": motivo,
            "aviso": (
                "Consumo indevido (656): a SEFAZ pede pra esperar ~1h entre cargas "
                "completas. Tente de novo mais tarde." if cstat == "656" else None
            ),
        }

    def listar_elegiveis(self) -> list[Empresa]:
        """Empresas aptas pra Distribuição Direta: ativas, com cert A1, SEM token
        Focus (as com Focus já têm a fila consumida por ela → 656)."""
        return list(self.db.scalars(
            select(Empresa).where(
                Empresa.ativo.is_(True),
                Empresa.cert_a1_path.isnot(None),
                Empresa.focus_token.is_(None),
            ).order_by(Empresa.razao_social)
        ).all())

    def distribuir_lote(self, empresa_ids: list[int], *, max_paginas: int = 8) -> list[dict]:
        """Distribui um BLOCO de empresas (o frontend fatia a carteira). Erro
        numa empresa não derruba o bloco."""
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

    def manifestar_recebidas(self, empresa_id: int, *, limite: int = 20) -> dict:
        """Manifesta (Ciência da Operação) as recebidas em RESUMO da empresa.

        Libera o XML completo: após a ciência, a próxima Distribuição traz o
        procNFe. Aqui só ENVIA o evento assinado (XML-DSig) e marca status.
        Processa em lote (`limite`) pra caber no timeout.
        """
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        if not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
            raise HTTPException(status_code=400, detail="Empresa sem certificado A1.")
        senha = empresa.get_cert_a1_senha() or ""

        pendentes = list(self.db.scalars(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa_id,
                DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
                DocumentoFiscal.origem == "recebida",
                DocumentoFiscal.status == "resumo",
            ).limit(limite)
        ).all())

        prov = NFeManifestacaoProvider()
        manifestadas = 0
        ja_cientes = 0
        erros: list[str] = []
        for doc in pendentes:
            try:
                res = prov.manifestar_ciencia(
                    chave=doc.chave_acesso, cnpj=empresa.cnpj,
                    pfx_path=empresa.cert_a1_path, pfx_senha=senha,
                )
                if res["ok"]:
                    doc.status = "manifestado"
                    if res["cstat"] == "573":
                        ja_cientes += 1
                    else:
                        manifestadas += 1
                    self.db.commit()
                else:
                    erros.append(f"{doc.chave_acesso[-6:]}: {res['cstat']} {res['motivo']}")
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                erros.append(f"{doc.chave_acesso[-6:]}: {exc}")

        restantes = self.db.scalar(
            select(func.count(DocumentoFiscal.id)).where(
                DocumentoFiscal.empresa_id == empresa_id,
                DocumentoFiscal.origem == "recebida",
                DocumentoFiscal.status == "resumo",
            )
        )
        return {
            "empresa_id": empresa_id,
            "manifestadas": manifestadas,
            "ja_cientes": ja_cientes,
            "erros": erros[:10],
            "restantes_resumo": int(restantes or 0),
            "aviso": (
                "Pronto! Rode a Distribuição DF-e de novo pra baixar o XML "
                "completo das que você acabou de dar ciência."
                if (manifestadas or ja_cientes) else None
            ),
        }

    def diagnosticar_evento(self, empresa_id: int) -> dict:
        """Dispara o evento assinado em várias formas de envelope/transporte e
        devolve o que cada uma respondeu — pra achar a combinação que o
        NFeRecepcaoEvento4 aceita. Usa uma chave de uma recebida em resumo."""
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        if not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
            raise HTTPException(status_code=400, detail="Empresa sem certificado A1.")
        doc = self.db.scalar(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa_id,
                DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
                DocumentoFiscal.origem == "recebida",
                DocumentoFiscal.status == "resumo",
            ).limit(1)
        )
        if not doc:
            raise HTTPException(status_code=400, detail="Sem recebida em resumo pra testar.")
        senha = empresa.get_cert_a1_senha() or ""
        variantes = NFeManifestacaoProvider().diagnosticar_variantes(
            chave=doc.chave_acesso, cnpj=empresa.cnpj,
            pfx_path=empresa.cert_a1_path, pfx_senha=senha,
        )
        return {"empresa_id": empresa_id, "chave": doc.chave_acesso, "variantes": variantes}

    def _salvar_resumo(self, empresa: Empresa, doc) -> bool:
        """Grava o resumo de uma recebida (resNFe) — sem XML completo ainda."""
        if not doc.chave:
            return False
        existe = self.db.scalar(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa.id,
                DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
                DocumentoFiscal.chave_acesso == doc.chave,
            )
        )
        if existe:
            return False
        self.db.add(DocumentoFiscal(
            empresa_id=empresa.id,
            tipo_documento=TipoDocumento.NFE,
            chave_acesso=doc.chave,
            cnpj_emitente=doc.cnpj_emitente,
            nome_emitente=doc.nome_emitente,
            cnpj_destinatario="".join(c for c in (empresa.cnpj or "") if c.isdigit()) or None,
            nome_destinatario=empresa.razao_social,
            valor_total=_dec(doc.valor),
            data_emissao=_parse_dt(doc.data_emissao),
            status="resumo",   # resumo da distribuição; XML completo só pós-manifestação
            xml_path="",       # sem arquivo ainda
            origem="recebida",
            eh_saida=False,    # recebida = entrada
            cancelada=(doc.situacao == "3"),  # cSitNFe 3 = cancelada
            json_original={
                "fonte": "dfe_distribuicao", "nsu": doc.nsu,
                "schema": doc.schema, "cSitNFe": doc.situacao,
            },
        ))
        self.db.commit()
        return True
