from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.consulta_log import ConsultaLog
from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.providers.focus_nfe import (
    DocumentoRecebidoFocus,
    FocusNFeProvider,
    FocusTokenAusenteError,
)
from app.services.xml_parser import XMLParserService
from app.services.xml_storage import XMLStorageService


@dataclass(slots=True)
class RoboResultado:
    processados: int = 0
    baixados: int = 0
    duplicados: int = 0
    erros: int = 0
    # True quando havia mais documentos na resposta Focus do que o limite
    # MAX_NFES_POR_REQUEST permitiu processar nesta chamada. Frontend usa
    # pra sinalizar "ha mais NFes — clica de novo".
    tem_mais: bool = False


# Limite de NFes recebidas processadas por chamada do robo.
# Cada NFe = 1 chamada Focus (GET XML) + parser + save disco + commit DB.
# Volume grande estoura o worker uvicorn em prod (OOM ou timeout Traefik).
# Frontend repete enquanto tem_mais=True.
MAX_NFES_POR_REQUEST = 25


class RoboXMLService:
    """Orquestra o download de XMLs (NFe recebidas via DF-e/Focus NFe).

    Hoje o robo cobre apenas o fluxo de NF-e RECEBIDAS (entradas), pois a Focus
    NFe nao expoe endpoint para baixar XMLs de notas EMITIDAS por outros sistemas
    (SAP, Bling, etc). Notas emitidas ficam fora do escopo do robo diario.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = FocusNFeProvider()
        self.storage = XMLStorageService()
        self.parser = XMLParserService()

    # --- API publica ---

    def baixar_distribuicao_empresa(
        self,
        empresa_id: int,
        data_inicio: datetime,
        data_fim: datetime,
    ) -> RoboResultado:
        """Baixa NF-es RECEBIDAS contra o CNPJ da empresa via Focus NFe.

        Usa NSU incremental persistido em `empresas.ultimo_nsu_distribuicao`.
        Pre-requisito: `empresa.focus_token` preenchido.
        Janela SEFAZ: 90 dias.
        """
        empresa = self._get_empresa(empresa_id)
        token = empresa.get_focus_token()
        if not token:
            self._log(
                empresa_id, "NFE_DIST", data_inicio, data_fim, "erro",
                "Empresa sem focus_token configurado.",
                {"ultimo_nsu": empresa.ultimo_nsu_distribuicao},
            )
            return RoboResultado(erros=1)

        try:
            documentos = self.provider.listar_nfes_recebidas(
                token,
                empresa.cnpj,
                nsu=empresa.ultimo_nsu_distribuicao,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
        except FocusTokenAusenteError as exc:
            self._log(
                empresa_id, "NFE_DIST", data_inicio, data_fim, "erro", str(exc),
                {"ultimo_nsu": empresa.ultimo_nsu_distribuicao},
            )
            return RoboResultado(erros=1)

        # Limita NFes processadas por request — protege o worker de OOM e
        # do Traefik timeout (60s). Em prod, indústria como CLAVEAUX pode ter
        # 50+ NFes recebidas em 7 dias. Frontend itera enquanto tem_mais=True.
        total_disponivel = len(documentos)
        tem_mais = total_disponivel > MAX_NFES_POR_REQUEST
        documentos_processar = documentos[:MAX_NFES_POR_REQUEST]

        resultado = self._processar_documentos_recebidos(
            empresa, documentos_processar, data_inicio, data_fim
        )
        resultado.tem_mais = tem_mais

        # Avanca NSU pelo maior NSU dos PROCESSADOS (nao dos disponíveis):
        # garante que a proxima chamada continua do ponto certo.
        novo_max_nsu = self._maior_nsu(documentos_processar)
        if novo_max_nsu and resultado.erros == 0:
            empresa.ultimo_nsu_distribuicao = novo_max_nsu
            self.db.commit()
        return resultado

    def baixar_distribuicao_empresa_completa(
        self,
        empresa_id: int,
        data_inicio: datetime,
        data_fim: datetime,
    ) -> dict:
        """Atalho que retorna o resultado da distribuicao no formato dict.

        Mantido para compatibilidade com a rota `/robo/empresa`. NFe/CTe/NFSe
        emitidas por outros sistemas saem do escopo (Focus nao oferece esse
        endpoint).
        """
        return {"distribuicao": asdict(self.baixar_distribuicao_empresa(empresa_id, data_inicio, data_fim))}

    def baixar_distribuicao_multiempresas(
        self,
        data_inicio: datetime,
        data_fim: datetime,
    ) -> dict:
        empresas = self.db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.id)
        ).all()
        resultado: dict[int, dict] = {}
        for empresa in empresas:
            resultado[empresa.id] = self.baixar_distribuicao_empresa_completa(
                empresa.id, data_inicio, data_fim
            )
        return resultado

    # --- Processamento interno ---

    def _processar_documentos_recebidos(
        self,
        empresa: Empresa,
        documentos: list[DocumentoRecebidoFocus],
        data_inicio: datetime,
        data_fim: datetime,
    ) -> RoboResultado:
        resultado = RoboResultado()
        for doc in documentos:
            chave = doc.chave or ""

            # Filtra eventos/resumos: so processa NF-e com chave de 44 digitos
            if not chave or len(chave) != 44 or not chave.isdigit():
                self._log(
                    empresa.id, "NFE_DIST", data_inicio, data_fim, "ignorado",
                    "Item ignorado (evento/resumo, chave invalida).",
                    {"chave": chave, "tipo": doc.tipo, "nsu": doc.nsu},
                )
                continue

            resultado.processados += 1

            exists = self.db.scalar(
                select(DocumentoFiscal).where(
                    DocumentoFiscal.empresa_id == empresa.id,
                    DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
                    DocumentoFiscal.chave_acesso == chave,
                )
            )
            if exists:
                resultado.duplicados += 1
                continue

            try:
                xml_content = self.provider.baixar_xml_nfe_recebida(
                    empresa.get_focus_token() or "", chave
                )
                parsed = self.parser.parse(TipoDocumento.NFE.value, xml_content)
                chave_parsed = parsed.get("chave_acesso") or chave
                if not chave_parsed:
                    raise ValueError("XML sem chave de acesso extraivel.")

                data_emissao = parsed.get("data_emissao") or doc.data_emissao or data_inicio
                xml_path = self.storage.save_xml(
                    empresa_cnpj=empresa.cnpj,
                    tipo_documento=TipoDocumento.NFE.value,
                    ano=data_emissao.year,
                    mes=data_emissao.month,
                    chave=chave_parsed,
                    xml_content=xml_content,
                )

                documento = DocumentoFiscal(
                    empresa_id=empresa.id,
                    tipo_documento=TipoDocumento.NFE,
                    chave_acesso=chave_parsed,
                    numero=parsed.get("numero"),
                    serie=parsed.get("serie"),
                    data_emissao=parsed.get("data_emissao"),
                    cnpj_emitente=parsed.get("cnpj_emitente") or doc.cnpj_emitente,
                    nome_emitente=parsed.get("nome_emitente") or doc.nome_emitente,
                    cnpj_destinatario=parsed.get("cnpj_destinatario"),
                    nome_destinatario=parsed.get("nome_destinatario"),
                    valor_total=parsed.get("valor_total") or doc.valor_total,
                    status="baixado",
                    xml_path=xml_path,
                    origem="recebida",
                    json_original=doc.raw,
                )
                self.db.add(documento)
                self.db.commit()
                resultado.baixados += 1
                self._log(
                    empresa.id, "NFE_DIST", data_inicio, data_fim, "sucesso",
                    "Documento da distribuicao baixado.",
                    {"chave": chave_parsed, "nsu": doc.nsu},
                )
            except IntegrityError:
                self.db.rollback()
                resultado.duplicados += 1
            except Exception as exc:
                self.db.rollback()
                resultado.erros += 1
                self._log(
                    empresa.id, "NFE_DIST", data_inicio, data_fim, "erro",
                    str(exc),
                    {"chave": chave, "nsu": doc.nsu},
                )
        return resultado

    @staticmethod
    def _maior_nsu(documentos: list[DocumentoRecebidoFocus]) -> str | None:
        valores: list[int] = []
        for doc in documentos:
            if not doc.nsu:
                continue
            try:
                valores.append(int(doc.nsu))
            except (TypeError, ValueError):
                continue
        return str(max(valores)) if valores else None

    # --- Manifestacao + atualizacao para procNFe completo ---

    @dataclass(slots=True)
    class ManifestacaoResultado:
        empresa_id: int
        total: int = 0
        manifestadas: int = 0
        ja_manifestadas: int = 0
        pdf_baixadas: int = 0
        xml_atualizadas: int = 0
        erros: int = 0
        detalhes: list[dict] | None = None

        def to_dict(self) -> dict:
            return {
                "empresa_id": self.empresa_id,
                "total": self.total,
                "manifestadas": self.manifestadas,
                "ja_manifestadas": self.ja_manifestadas,
                "pdf_baixadas": self.pdf_baixadas,
                "xml_atualizadas": self.xml_atualizadas,
                "erros": self.erros,
            }

    def manifestar_e_baixar_pdfs(
        self,
        empresa_id: int,
        *,
        tipo: str = "ciencia",
        sleep_entre_manifestos: float = 0.4,
        aguardar_sync_segundos: int = 30,
    ) -> "RoboXMLService.ManifestacaoResultado":
        """Para cada NFe da empresa, garante manifestacao (Ciencia) e baixa o
        DANFE PDF + XML completo (procNFe) ao lado do XML existente.

        Fluxo por NF:
          1. Verifica se o XML em disco eh `resNFe` (resumo) ou `nfeProc` (completo).
          2. Se ainda nao manifestado na Focus, POST /manifesto?tipo=ciencia.
          3. Apos manifestar todas, aguarda `aguardar_sync_segundos` (Focus
             leva alguns minutos pra refazer o sync da SEFAZ).
          4. Tenta baixar `.pdf` (DANFE) e re-baixar `.xml` (agora completo).
          5. Salva ao lado do XML existente: `<chave>.pdf` e sobrescreve `<chave>.xml`.

        Retorna contadores + lista de detalhes por chave.
        """
        empresa = self._get_empresa(empresa_id)
        token = empresa.get_focus_token() or ""
        if not token:
            raise FocusTokenAusenteError(
                f"Empresa {empresa.cnpj} sem token Focus. Importe primeiro."
            )

        resultado = RoboXMLService.ManifestacaoResultado(empresa_id=empresa_id, detalhes=[])
        docs = self.db.scalars(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa.id,
                DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
                DocumentoFiscal.origem == "recebida",
            )
        ).all()
        resultado.total = len(docs)

        # === Etapa 1: manifestar tudo que ainda nao foi ===
        # Marcamos `manifestado_em` no `json_original` pra nao re-manifestar
        # toda vez (Focus aceita, mas gasta quota a toa e demora).
        chaves_pendentes_sync: list[tuple[DocumentoFiscal, str]] = []
        for doc in docs:
            chave = doc.chave_acesso
            xml_local = Path(doc.xml_path) if doc.xml_path else None
            ja_completo = self._xml_eh_completo(xml_local)
            raw = doc.json_original or {}
            ja_manifestado = bool(raw.get("manifestado_em"))

            if ja_completo or ja_manifestado:
                resultado.ja_manifestadas += 1
                chaves_pendentes_sync.append((doc, chave))
                continue
            try:
                self.provider.manifestar_nfe_recebida(token, chave, tipo)
                resultado.manifestadas += 1
                # Marca como manifestado. SQLAlchemy NAO detecta mutacao em
                # dict JSON in-place: precisa copiar + flag_modified.
                novo_raw = dict(raw)
                novo_raw["manifestado_em"] = datetime.utcnow().isoformat()
                novo_raw["manifestado_tipo"] = tipo
                doc.json_original = novo_raw
                flag_modified(doc, "json_original")
                chaves_pendentes_sync.append((doc, chave))
            except Exception as exc:  # noqa: BLE001
                resultado.erros += 1
                if resultado.detalhes is not None:
                    resultado.detalhes.append({
                        "chave": chave, "fase": "manifestar", "erro": str(exc)[:200],
                    })
            if sleep_entre_manifestos:
                time.sleep(sleep_entre_manifestos)
        self.db.commit()

        # === Etapa 2: aguardar Focus sincronizar com SEFAZ ===
        if resultado.manifestadas > 0 and aguardar_sync_segundos > 0:
            time.sleep(aguardar_sync_segundos)

        # === Etapa 3: re-baixar XML completo + DANFE PDF ===
        for doc, chave in chaves_pendentes_sync:
            xml_local = Path(doc.xml_path) if doc.xml_path else None
            pdf_local = xml_local.with_suffix(".pdf") if xml_local else None

            # 3a. XML completo
            if xml_local and not self._xml_eh_completo(xml_local):
                try:
                    xml_novo = self.provider.baixar_xml_nfe_recebida(token, chave)
                    # Cancelamento: Focus pode devolver procEventoNFe em vez do procNFe
                    evento_cancel = self._extrair_evento_cancelamento(xml_novo)
                    if evento_cancel:
                        xml_local.write_text(xml_novo, encoding="utf-8")
                        self._marcar_cancelada(doc, evento_cancel)
                    elif "<nfeProc" in xml_novo or "<infNFe" in xml_novo:
                        xml_local.write_text(xml_novo, encoding="utf-8")
                        resultado.xml_atualizadas += 1
                except Exception as exc:  # noqa: BLE001
                    if resultado.detalhes is not None:
                        resultado.detalhes.append({
                            "chave": chave, "fase": "xml_completo", "erro": str(exc)[:200],
                        })

            # 3b. DANFE PDF
            if pdf_local and not pdf_local.exists():
                try:
                    pdf_bytes = self.provider.baixar_pdf_nfe_recebida(token, chave)
                    if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
                        pdf_local.write_bytes(pdf_bytes)
                        resultado.pdf_baixadas += 1
                except requests.HTTPError as exc:
                    # 404 eh esperado ate Focus completar sync (alguns min).
                    if exc.response is not None and exc.response.status_code != 404:
                        resultado.erros += 1
                    if resultado.detalhes is not None:
                        resultado.detalhes.append({
                            "chave": chave, "fase": "pdf",
                            "status": getattr(exc.response, "status_code", "?"),
                        })
                except Exception as exc:  # noqa: BLE001
                    resultado.erros += 1
                    if resultado.detalhes is not None:
                        resultado.detalhes.append({
                            "chave": chave, "fase": "pdf", "erro": str(exc)[:200],
                        })

        return resultado

    @staticmethod
    def _xml_eh_completo(xml_path: Path | None) -> bool:
        """True se o XML for `nfeProc` ou `NFe` completa (com `infNFe`)."""
        if not xml_path or not xml_path.exists():
            return False
        try:
            head = xml_path.read_text(encoding="utf-8", errors="replace")[:2000]
        except Exception:
            return False
        return ("<nfeProc" in head) or ("<infNFe" in head)

    def _marcar_cancelada(self, doc: DocumentoFiscal, evento: dict) -> None:
        """Persiste flag cancelada + metadata do evento no documento."""
        from datetime import date
        doc.cancelada = True
        doc.motivo_cancelamento = (evento.get("motivo") or "")[:255] or None
        doc.protocolo_cancelamento = (evento.get("protocolo") or "")[:30] or None
        # Parse data — pode vir "2026-04-15T08:23:59-03:00" ou só "20260415"
        data_evento = evento.get("data") or ""
        if data_evento:
            try:
                doc.cancelada_em = datetime.fromisoformat(
                    data_evento.replace("Z", "+00:00")
                ).date()
            except (ValueError, AttributeError):
                # Tenta YYYYMMDD
                if len(data_evento) == 8 and data_evento.isdigit():
                    try:
                        doc.cancelada_em = datetime.strptime(
                            data_evento, "%Y%m%d"
                        ).date()
                    except ValueError:
                        doc.cancelada_em = date.today()
                else:
                    doc.cancelada_em = date.today()
        else:
            doc.cancelada_em = date.today()
        # Status semantico no campo string
        if not doc.status or doc.status == "baixado":
            doc.status = "cancelada"
        self.db.commit()

    @staticmethod
    def _extrair_evento_cancelamento(xml_content: str) -> dict | None:
        """Detecta se o XML eh um evento de Cancelamento (procEventoNFe).

        Retorna dict com `data`, `motivo` (xJust), `protocolo` (nProt) ou None.
        SEFAZ tipoEvento 110111 = Cancelamento; descEvento contem 'Cancelamento'.
        """
        if "<procEventoNFe" not in xml_content[:500]:
            return None
        import re
        # Match flexivel (com ou sem prefixo de namespace)
        def _get(tag: str) -> str | None:
            m = re.search(rf"<{tag}[^>]*>([^<]+)</{tag}>", xml_content)
            return m.group(1).strip() if m else None

        desc = _get("descEvento") or ""
        tipo = _get("tpEvento") or ""
        if "cancelamento" not in desc.lower() and tipo != "110111":
            return None

        return {
            "motivo": _get("xJust"),
            "protocolo": _get("nProt"),
            "data": _get("dhEvento") or _get("dhRegEvento"),
        }

    def manifestar_documento(
        self,
        documento_id: int,
        *,
        tipo: str = "ciencia",
        tentar_baixar_pdf: bool = True,
    ) -> dict:
        """Manifesta UM documento especifico e tenta baixar PDF/XML completo.

        Diferente de `manifestar_e_baixar_pdfs` (lote), esta versao:
        - Aceita re-manifestar (user pode mudar de ideia: ciencia -> confirmacao)
        - Atualiza o `manifestado_em` no json_original
        - Tenta XML completo + PDF imediatamente (sem aguardar)
        - Retorna o estado pos-manifestacao do documento (raw json_original + flags)
        """
        doc = self.db.get(DocumentoFiscal, documento_id)
        if not doc:
            raise ValueError(f"Documento {documento_id} nao encontrado")
        if doc.tipo_documento != TipoDocumento.NFE:
            raise ValueError(
                f"Manifestacao so suportada para NFE; documento eh {doc.tipo_documento}"
            )
        if doc.origem != "recebida":
            raise ValueError(
                "Manifestacao soh faz sentido para NFes recebidas (DF-e)."
            )

        empresa = self._get_empresa(doc.empresa_id)
        token = empresa.get_focus_token() or ""
        if not token:
            raise FocusTokenAusenteError(
                f"Empresa {empresa.cnpj} sem token Focus. Importe primeiro."
            )

        chave = doc.chave_acesso
        resultado: dict = {
            "documento_id": documento_id,
            "chave_acesso": chave,
            "tipo_manifestacao": tipo,
            "status_sefaz": None,
            "protocolo": None,
            "manifestado_em": None,
            "xml_atualizado": False,
            "pdf_baixado": False,
            "ja_estava_manifestado": False,
        }

        raw = dict(doc.json_original or {})
        if raw.get("manifestado_em") and raw.get("manifestado_tipo") == tipo:
            resultado["ja_estava_manifestado"] = True
            resultado["manifestado_em"] = raw["manifestado_em"]
        else:
            try:
                resp = self.provider.manifestar_nfe_recebida(token, chave, tipo)
                resultado["status_sefaz"] = resp.get("status_sefaz")
                resultado["protocolo"] = resp.get("protocolo")
                # Marca no json_original
                novo_raw = dict(raw)
                novo_raw["manifestado_em"] = datetime.utcnow().isoformat()
                novo_raw["manifestado_tipo"] = tipo
                doc.json_original = novo_raw
                flag_modified(doc, "json_original")
                self.db.commit()
                resultado["manifestado_em"] = novo_raw["manifestado_em"]
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Falha ao manifestar: {exc}") from exc

        if not tentar_baixar_pdf:
            return resultado

        # Tenta XML completo + PDF imediatamente (pode dar 404 se Focus ainda
        # nao sincronizou — frontend mostra mensagem clara).
        xml_local = Path(doc.xml_path) if doc.xml_path else None
        pdf_local = xml_local.with_suffix(".pdf") if xml_local else None

        if xml_local and not self._xml_eh_completo(xml_local):
            try:
                xml_novo = self.provider.baixar_xml_nfe_recebida(token, chave)
                evento_cancel = self._extrair_evento_cancelamento(xml_novo)
                if evento_cancel:
                    xml_local.write_text(xml_novo, encoding="utf-8")
                    self._marcar_cancelada(doc, evento_cancel)
                    resultado["cancelada_detectada"] = True
                elif "<nfeProc" in xml_novo or "<infNFe" in xml_novo:
                    xml_local.write_text(xml_novo, encoding="utf-8")
                    resultado["xml_atualizado"] = True
            except Exception:  # noqa: BLE001
                pass  # 404 normal enquanto Focus nao sync

        if pdf_local and not pdf_local.exists():
            try:
                pdf_bytes = self.provider.baixar_pdf_nfe_recebida(token, chave)
                if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
                    pdf_local.write_bytes(pdf_bytes)
                    resultado["pdf_baixado"] = True
            except Exception:  # noqa: BLE001
                pass  # 404 normal enquanto Focus nao sync

        return resultado

    def verificar_canceladas(self, empresa_id: int | None = None) -> dict:
        """Varre XMLs locais e marca como cancelada quando detectar
        `procEventoNFe descEvento=Cancelamento`. Util pra empresas com
        XMLs ja baixados antes da feature.
        """
        stmt = select(DocumentoFiscal).where(
            DocumentoFiscal.tipo_documento == TipoDocumento.NFE,
            DocumentoFiscal.cancelada == False,  # noqa: E712
        )
        if empresa_id is not None:
            stmt = stmt.where(DocumentoFiscal.empresa_id == empresa_id)
        docs = self.db.scalars(stmt).all()

        verificadas = 0
        novas_canceladas = 0
        for doc in docs:
            if not doc.xml_path:
                continue
            p = Path(doc.xml_path)
            if not p.exists():
                continue
            verificadas += 1
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            evento = self._extrair_evento_cancelamento(content)
            if evento:
                self._marcar_cancelada(doc, evento)
                novas_canceladas += 1
        return {
            "verificadas": verificadas,
            "novas_canceladas": novas_canceladas,
            "empresa_id": empresa_id,
        }

    def _get_empresa(self, empresa_id: int) -> Empresa:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise ValueError("Empresa nao encontrada")
        return empresa

    def _log(
        self,
        empresa_id: int | None,
        tipo_documento: str | None,
        data_inicio: datetime,
        data_fim: datetime,
        status: str,
        mensagem: str,
        detalhes: dict | None = None,
    ) -> None:
        self.db.add(
            ConsultaLog(
                empresa_id=empresa_id,
                tipo_documento=tipo_documento,
                periodo_inicio=data_inicio,
                periodo_fim=data_fim,
                status=status,
                mensagem=mensagem,
                detalhes=detalhes,
            )
        )
        self.db.commit()
