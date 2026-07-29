"""Serviço de sincronização das NFS-e pelo ADN — persiste como DocumentoFiscal.

Orquestra o cursor NSU: chama o provider, e pra cada NFS-e completa:
- determina se é EMITIDA (empresa é a prestadora → saída/faturamento) ou
  RECEBIDA (empresa é a tomadora → entrada);
- salva o XML no storage local;
- grava DocumentoFiscal(tipo=NFSE), dedup por chave.
Guarda o cursor em `empresa.nfse_adn_ult_nsu` pra continuar incremental.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.providers.nfse_adn import NFSeAdnProvider
from app.services.nfse_parser import parse_nfse
from app.services.xml_storage import XMLStorageService

logger = logging.getLogger(__name__)


def _ano_mes(dh: str | None) -> tuple[int, int]:
    if dh and len(dh) >= 7:
        try:
            return int(dh[0:4]), int(dh[5:7])
        except ValueError:
            pass
    return 2000, 1


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class NFSeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = NFSeAdnProvider()
        self.storage = XMLStorageService()

    def listar_elegiveis(self) -> list[Empresa]:
        """Ativas com cert A1 (NFSe ADN exige o A1 do próprio CNPJ)."""
        return list(self.db.scalars(
            select(Empresa).where(
                Empresa.ativo.is_(True),
                Empresa.cert_a1_path.isnot(None),
            ).order_by(Empresa.razao_social)
        ).all())

    def sincronizar_empresa(self, empresa_id: int, *, max_lotes: int = 50) -> dict:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        if not empresa.cert_a1_path or not Path(empresa.cert_a1_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Empresa sem certificado A1 — o ADN NFS-e exige o cert.",
            )
        senha = empresa.get_cert_a1_senha() or ""
        cnpj_emp = "".join(c for c in (empresa.cnpj or "") if c.isdigit())
        cursor_ini = int(empresa.nfse_adn_ult_nsu or "0")

        try:
            res = self.provider.sincronizar(
                cnpj=empresa.cnpj, pfx_path=empresa.cert_a1_path, pfx_senha=senha,
                cursor_inicial=cursor_ini, max_lotes=max_lotes,
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha no sync NFSe da empresa %s", empresa_id)
            raise HTTPException(status_code=502, detail=f"Sync NFSe falhou: {exc}")

        emitidas = recebidas = eventos = novos = canceladas = 0
        for doc in res.documentos:
            is_evento = (doc.tipo_documento or "").upper() == "EVENTO"
            if not doc.xml:
                if is_evento:
                    eventos += 1
                continue
            meta = parse_nfse(doc.xml)
            if meta.get("_erro"):
                continue
            # EVENTO (cancelamento/substituição): NÃO é uma NFS-e nova — é um
            # evento SOBRE uma NFS-e existente. Antes era só contado e descartado
            # (bug "serviço não vem cancelada" — a NFS-e ficava eternamente ativa).
            # Agora, se for cancelamento, acha a NFS-e pela chNFSe e marca cancelada.
            if is_evento or meta.get("tipo_raiz") == "evento":
                eventos += 1
                if self._aplicar_evento_nfse(empresa, meta):
                    canceladas += 1
                continue
            chave = meta.get("chave_acesso") or doc.chave_acesso
            if not chave:
                continue
            existe = self.db.scalar(
                select(DocumentoFiscal.id).where(
                    DocumentoFiscal.empresa_id == empresa.id,
                    DocumentoFiscal.tipo_documento == TipoDocumento.NFSE,
                    DocumentoFiscal.chave_acesso == chave,
                )
            )
            if existe:
                continue

            eh_saida = bool(meta.get("cnpj_prestador") and meta["cnpj_prestador"] == cnpj_emp)
            ano, mes = _ano_mes(meta.get("dh_emissao") or doc.data_hora_geracao)
            try:
                xml_path = self.storage.save_xml(
                    cnpj_emp or "sem-cnpj", "nfse", ano, mes, chave, doc.xml)
            except OSError as exc:
                res.erros.append(f"NSU {doc.nsu}: salvar XML: {exc}")
                continue

            self.db.add(DocumentoFiscal(
                empresa_id=empresa.id,
                tipo_documento=TipoDocumento.NFSE,
                chave_acesso=chave,
                numero=meta.get("numero"),
                serie=meta.get("serie"),
                data_emissao=_parse_dt(meta.get("dh_emissao")),
                cnpj_emitente=meta.get("cnpj_prestador"),
                nome_emitente=meta.get("nome_prestador"),
                cnpj_destinatario=meta.get("cnpj_tomador"),
                nome_destinatario=meta.get("nome_tomador"),
                valor_total=meta.get("valor_servico") or meta.get("valor_liquido"),
                status="completo",
                xml_path=xml_path,
                origem="emitida" if eh_saida else "recebida",
                eh_saida=eh_saida,
                json_original={"fonte": "nfse_adn", "nsu": doc.nsu},
            ))
            novos += 1
            if eh_saida:
                emitidas += 1
            else:
                recebidas += 1

        if res.cursor_final and res.cursor_final != cursor_ini:
            empresa.nfse_adn_ult_nsu = str(res.cursor_final)
        self.db.commit()

        return {
            "empresa_id": empresa.id,
            "razao_social": empresa.razao_social,
            "novos": novos,
            "emitidas": emitidas,
            "recebidas": recebidas,
            "eventos": eventos,
            "canceladas": canceladas,
            "lotes": res.lotes,
            "cursor_final": res.cursor_final,
            "motivo_parada": res.motivo_parada,
            "erros": res.erros[:10],
            "alertas": res.alertas[:5],
        }

    def _aplicar_evento_nfse(self, empresa: Empresa, meta: dict) -> bool:
        """Aplica um evento de NFS-e. Se for CANCELAMENTO (ou cancelamento por
        substituição), acha a NFS-e pela chNFSe e marca `cancelada=True`. Retorna
        True se marcou. Conservador: só cancela quando o motivo do evento indica
        cancelamento — outros eventos (ciência do tomador etc.) são ignorados."""
        chave = meta.get("chave_acesso")
        if not chave:
            return False
        # Só trata como cancelamento se o texto do evento indicar. Evita marcar
        # NFS-e válida como cancelada por um evento benigno (ex.: ciência).
        texto = " ".join(str(meta.get(k) or "") for k in ("motivo_evento", "tipo_evento")).lower()
        if "cancel" not in texto and "substitu" not in texto:
            return False
        doc = self.db.scalar(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa.id,
                DocumentoFiscal.tipo_documento == TipoDocumento.NFSE,
                DocumentoFiscal.chave_acesso == chave,
            )
        )
        if not doc or doc.cancelada:
            return False
        doc.cancelada = True
        doc.motivo_cancelamento = (meta.get("motivo_evento") or "Cancelamento NFS-e")[:255]
        dt_ev = _parse_dt(meta.get("dh_emissao"))
        doc.cancelada_em = dt_ev.date() if dt_ev else datetime.now().date()
        if not doc.status or doc.status in ("baixado", "completo"):
            doc.status = "cancelada"
        return True

    def sincronizar_lote(self, empresa_ids: list[int], *, max_lotes: int = 30) -> list[dict]:
        resultados: list[dict] = []
        for eid in empresa_ids:
            try:
                resultados.append(self.sincronizar_empresa(eid, max_lotes=max_lotes))
            except HTTPException as exc:
                resultados.append({"empresa_id": eid, "ok": False, "erro": str(exc.detail), "novos": 0})
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                resultados.append({"empresa_id": eid, "ok": False, "erro": str(exc)[:200], "novos": 0})
        return resultados

    def cron_sincronizar(self, *, chunk: int = 3, budget_s: int = 40, max_lotes: int = 10) -> dict:
        """Passo do cron de NFS-e (ADN): avança um PEDAÇO da carteira sincronizando
        o cursor NSU de cada empresa. Cursor round-robin em ARQUIVO (sem migration).

        Feito pra um cron EXTERNO chamar a cada ~10-15 min: cada chamada processa
        `chunk` empresas (limitado por `budget_s` pra caber no Traefik ~60s) e
        avança o cursor; ao longo do dia drena a carteira toda. Erro numa empresa
        não derruba as outras."""
        import json
        import time
        from pathlib import Path

        from app.config import get_settings as _gs

        elegiveis = self.listar_elegiveis()
        n = len(elegiveis)
        if n == 0:
            return {"total_elegiveis": 0, "processadas": []}

        cursor_path = Path(_gs().storage_path).parent / "nfse_cron_cursor.json"
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
                r = self.sincronizar_empresa(emp.id, max_lotes=max_lotes)
                item["novos"] = r.get("novos")
                item["canceladas"] = r.get("canceladas")
                item["motivo_parada"] = r.get("motivo_parada")
            except HTTPException as exc:
                self.db.rollback()
                item["erro"] = str(exc.detail)[:140]
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                item["erro"] = str(exc)[:140]
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
