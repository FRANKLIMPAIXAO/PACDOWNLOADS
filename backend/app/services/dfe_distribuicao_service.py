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
from datetime import datetime, timedelta, timezone
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

        # Janela da Ciência da Operação ~10 dias: notas mais velhas SEMPRE dão
        # cStat 596 ("fora do prazo"). Pular as antigas (>15d, com folga) evita
        # gastar milhares de chamadas assinadas à toa — e o lote drena rápido.
        # data_emissao NULL entra (não dá pra saber a idade → tenta).
        corte = datetime.now(timezone.utc) - timedelta(days=15)
        na_janela = (
            (DocumentoFiscal.data_emissao.is_(None))
            | (DocumentoFiscal.data_emissao >= corte)
        )
        pendentes = list(self.db.scalars(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa_id,
                DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
                DocumentoFiscal.origem == "recebida",
                DocumentoFiscal.status == "resumo",
                na_janela,
            ).order_by(DocumentoFiscal.data_emissao.desc().nullslast()).limit(limite)
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

        # Conta só as DENTRO da janela — assim o lote drena até 0 e para (as
        # antigas ficam em resumo de propósito, não são manifestáveis).
        restantes = self.db.scalar(
            select(func.count(DocumentoFiscal.id)).where(
                DocumentoFiscal.empresa_id == empresa_id,
                DocumentoFiscal.origem == "recebida",
                DocumentoFiscal.status == "resumo",
                na_janela,
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

    def manifestar_documento(self, documento_id: int) -> dict:
        """Manifesta (Ciência da Operação) UMA nota específica (botão da linha)."""
        doc = self.db.get(DocumentoFiscal, documento_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        empresa = self.db.get(Empresa, doc.empresa_id)
        if not empresa or not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
            raise HTTPException(status_code=400, detail="Empresa sem certificado A1.")
        if not doc.chave_acesso or len(doc.chave_acesso) != 44:
            raise HTTPException(status_code=400, detail="Documento sem chave de acesso válida.")
        senha = empresa.get_cert_a1_senha() or ""
        try:
            res = NFeManifestacaoProvider().manifestar_ciencia(
                chave=doc.chave_acesso, cnpj=empresa.cnpj,
                pfx_path=empresa.cert_a1_path, pfx_senha=senha,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Falha ao manifestar: {exc}")
        if res["ok"]:
            doc.status = "manifestado"
            self.db.commit()
        return {
            "documento_id": documento_id,
            "ok": res["ok"],
            "cstat": res["cstat"],
            "motivo": res["motivo"],
            "aviso": (
                "Ciência registrada! Rode a Distribuição DF-e da empresa pra baixar o XML completo."
                if res["ok"] else None
            ),
        }

    def cron_diario(self, *, chunk: int = 2, manifestar_limite: int = 8,
                    budget_s: int = 40) -> dict:
        """Passo do cron diário: avança um PEDAÇO da carteira fazendo
        distribuir + manifestar. Cursor em arquivo (round-robin, sem migration).

        Pensado pra ser chamado por um cron EXTERNO a cada ~10-15 min: cada
        chamada processa `chunk` empresas (limitado por `budget_s` pra caber no
        Traefik ~60s) e avança o cursor; ao longo do dia drena a carteira toda.
        A defasagem natural (manifestar hoje → XML completo na distribuição de
        amanhã) é absorvida pela recorrência.
        """
        import json
        import time
        from app.config import get_settings

        elegiveis = self.listar_elegiveis()
        n = len(elegiveis)
        if n == 0:
            return {"processadas": [], "total_elegiveis": 0, "cursor": 0}

        cursor_path = Path(get_settings().storage_path) / "dfe_cron_cursor.json"
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
                item["completas"] = dist.get("nfes_completas_novas")
                item["cstat"] = dist.get("cstat")
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                item["dist_erro"] = str(exc)[:140]
            try:
                man = self.manifestar_recebidas(emp.id, limite=manifestar_limite)
                item["manifestadas"] = man.get("manifestadas")
                item["ja_cientes"] = man.get("ja_cientes")
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                item["manif_erro"] = str(exc)[:140]
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
