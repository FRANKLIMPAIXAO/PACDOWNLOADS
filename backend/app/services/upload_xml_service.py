"""Serviço de upload em massa de XMLs (NFe/NFCe/CTe/NFSe).

Aceita ZIP ou lista de arquivos individuais. Pra cada XML:
1. Detecta o tipo (NFe/NFCe/CTe/NFSe) pelo root XML
2. Identifica empresa pelo CNPJ emitente OU destinatário (auto-roteamento)
3. Decide origem ('emitida' vs 'recebida') comparando com empresa cadastrada
4. Persiste igual ao robô (storage local + DB com unique key)

Retorna resumo agregado + lista de detalhes por arquivo.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.documento_fiscal import DocumentoFiscal, TipoDocumento
from app.models.empresa import Empresa
from app.services.xml_parser import XMLParserService
from app.services.xml_storage import XMLStorageService


@dataclass(slots=True)
class UploadDetalhe:
    arquivo: str
    chave: str | None = None
    tipo: str | None = None
    empresa_id: int | None = None
    empresa_cnpj: str | None = None
    origem: str | None = None  # emitida | recebida
    status: str = "ok"          # ok | duplicado | erro | empresa_nao_cadastrada
    mensagem: str | None = None


@dataclass(slots=True)
class UploadResultado:
    total_arquivos: int = 0
    persistidos: int = 0
    duplicados: int = 0
    empresa_nao_cadastrada: int = 0
    # XMLs pulados por ISOLAMENTO multi-tenant: nota de OUTRA empresa enviada num
    # upload restrito (ex.: cliente no portal subindo nota que não é dele).
    fora_do_escopo: int = 0
    # Eventos de CANCELAMENTO (procEventoNFe/CTe) que marcaram uma nota como
    # cancelada; órfãos = evento sem a nota no sistema; ignorados = eventos que
    # não são cancelamento (ex.: Carta de Correção).
    cancelamentos: int = 0
    cancelamentos_orfaos: int = 0
    eventos_ignorados: int = 0
    erros: int = 0
    detalhes: list[UploadDetalhe] = field(default_factory=list)

    def to_dict(self) -> dict:
        # Cap nos detalhes: ZIP de varejo (milhares de XMLs) geraria uma lista
        # gigante na resposta (memória + transferência pro robô). Mantém os
        # contadores agregados; serializa só uma AMOSTRA dos detalhes.
        d = asdict(self)
        if len(self.detalhes) > 100:
            d["detalhes"] = [asdict(x) for x in self.detalhes[:100]]
            d["detalhes_total"] = len(self.detalhes)
            d["detalhes_truncado"] = True
        return d


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _detectar_tipo(root: ET.Element) -> TipoDocumento | None:
    """Identifica NFE/NFCe/CTe/NFSe pelo elemento raiz ou primeiro filho conhecido."""
    name = _local_name(root.tag).lower()
    # NFe / NFCe: procEventoNFe (cancelamento), nfeProc, NFe, resNFe
    if name in ("nfeproc", "nfe", "resnfe"):
        return TipoDocumento.NFE
    # NFCe usa o mesmo modelo da NFe (modelo 65 vs 55)
    # Eventos
    if name == "proceventonfe":
        return TipoDocumento.NFE
    # CTe
    if name in ("cteproc", "cte", "resctE".lower()):
        return TipoDocumento.CTE
    if name == "proceventocte":
        return TipoDocumento.CTE
    # NFSe: varia por município (ABRASF, Ginfes, etc.)
    if name in ("compnfse", "nfse", "rps", "consultanfsesresposta"):
        return TipoDocumento.NFSE
    # Procura nos primeiros filhos
    for child in list(root)[:3]:
        cn = _local_name(child.tag).lower()
        if cn in ("nfe", "resnfe"):
            return TipoDocumento.NFE
        if cn in ("cte", "resctE".lower()):
            return TipoDocumento.CTE
        if cn in ("nfse",):
            return TipoDocumento.NFSE
    return None


def _normalizar_cnpj(s: str | None) -> str | None:
    if not s:
        return None
    digits = "".join(c for c in s if c.isdigit())
    return digits if len(digits) == 14 else None


# tpEvento de Cancelamento na SEFAZ (NFe/NFCe e CTe usam o mesmo código base).
_TPEVENTO_CANCELAMENTO = "110111"


def _parece_evento(xml_bytes: bytes) -> bool:
    """Classificação BARATA (sem parsear): o XML é um evento (procEventoNFe/CTe)?

    Usada pra ADIAR eventos pro 2º passe do ZIP — a nota tem que ser persistida
    ANTES do evento de cancelamento que a referencia (senão o evento fica órfão).
    """
    return b"procEvento" in xml_bytes[:800]


def _eh_evento(root: ET.Element) -> bool:
    return _local_name(root.tag).lower() in ("proceventonfe", "proceventocte")


def _parse_evento_cancelamento(xml_str: str) -> dict | None:
    """Se o XML for um evento de CANCELAMENTO (tpEvento 110111), devolve
    `{chave, motivo, protocolo, data}` — `chave` é a chNFe/chCTe da nota cancelada.

    Retorna None pra eventos que NÃO são cancelamento (ex.: Carta de Correção
    110110) — o chamador ignora esses (não são documento nem cancelamento).
    Regex mirror do RoboXMLService._extrair_evento_cancelamento (tags sem prefixo
    de namespace, como vêm no procEventoNFe da SEFAZ)."""
    import re

    def _get(tag: str) -> str | None:
        m = re.search(rf"<{tag}[^>]*>([^<]+)</{tag}>", xml_str)
        return m.group(1).strip() if m else None

    tp = _get("tpEvento") or ""
    desc = (_get("descEvento") or "").lower()
    if tp != _TPEVENTO_CANCELAMENTO and "cancel" not in desc:
        return None
    chave = _get("chNFe") or _get("chCTe") or ""
    chave = "".join(c for c in chave if c.isdigit())
    if len(chave) != 44:
        return None
    return {
        "chave": chave,
        "motivo": _get("xJust"),
        "protocolo": _get("nProt"),
        "data": _get("dhEvento") or _get("dhRegEvento"),
    }


def _parse_data_evento(data_evento: str | None):
    """'2026-04-15T08:23:59-03:00' ou '20260415' -> date. Fallback: hoje."""
    from datetime import date
    if data_evento:
        try:
            return datetime.fromisoformat(data_evento.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            if len(data_evento) == 8 and data_evento.isdigit():
                try:
                    return datetime.strptime(data_evento, "%Y%m%d").date()
                except ValueError:
                    pass
    return date.today()


class UploadXmlService:
    """Recebe XMLs (avulsos ou em ZIP) e persiste roteando pra empresa correta."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.parser = XMLParserService()
        self.storage = XMLStorageService()
        # Cache CNPJ -> Empresa pra agilizar lote grande
        self._empresas_por_cnpj: dict[str, Empresa] = {}

    def _empresa_por_cnpj(self, cnpj: str | None) -> Empresa | None:
        if not cnpj:
            return None
        if cnpj in self._empresas_por_cnpj:
            return self._empresas_por_cnpj[cnpj]
        emp = self.db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
        if emp:
            self._empresas_por_cnpj[cnpj] = emp
        return emp

    def processar_zip(
        self,
        zip_bytes: bytes,
        *,
        empresa_id_fallback: int | None = None,
        restringir_empresa_id: int | None = None,
        on_progress=None,
    ) -> UploadResultado:
        """Descompacta ZIP em memória e processa cada XML.

        `restringir_empresa_id`: ISOLAMENTO multi-tenant — quando setado, SÓ grava
        notas dessa empresa; nota de outra é PULADA (fora_do_escopo). Usado no
        upload pelo PORTAL do cliente (default None = sem restrição, robô/escritório).
        `on_progress(feitas, total)`: callback opcional p/ barra de progresso (varejo
        com milhares de NFC-e demora minutos — o portal sobe em background)."""
        resultado = UploadResultado()
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            resultado.erros = 1
            resultado.detalhes.append(UploadDetalhe(
                arquivo="(zip)", status="erro", mensagem=f"ZIP invalido: {exc}",
            ))
            return resultado

        entradas = [
            i for i in zf.infolist()
            if not i.is_dir() and i.filename.lower().endswith(".xml")
        ]
        total = len(entradas)
        if on_progress:
            on_progress(0, total)
        # 2 PASSES: as NOTAS primeiro, os EVENTOS de cancelamento depois. O ZIP do
        # SEFAZ ("Documentos + Eventos") traz a nota E o procEventoNFe que a
        # cancela; se o evento fosse processado antes da nota, ficaria órfão (nota
        # ainda não existe). Adiar os eventos garante a ordem certa dentro do ZIP.
        eventos_adiados: list[tuple[str, bytes]] = []
        for idx, info in enumerate(entradas, 1):
            resultado.total_arquivos += 1
            try:
                xml_bytes = zf.read(info)
            except Exception as exc:  # noqa: BLE001
                resultado.erros += 1
                resultado.detalhes.append(UploadDetalhe(
                    arquivo=info.filename,
                    status="erro",
                    mensagem=f"Falha ao ler do ZIP: {exc}",
                ))
            else:
                if _parece_evento(xml_bytes):
                    eventos_adiados.append((info.filename, xml_bytes))
                else:
                    self._processar_xml(
                        info.filename, xml_bytes, empresa_id_fallback, resultado,
                        restringir_empresa_id=restringir_empresa_id,
                    )
            # Reporta a cada 25 (ou no fim) pra não martelar o lock.
            if on_progress and (idx % 25 == 0 or idx == total):
                on_progress(idx, total)
        for nome, xml_bytes in eventos_adiados:
            self._processar_xml(
                nome, xml_bytes, empresa_id_fallback, resultado,
                restringir_empresa_id=restringir_empresa_id,
            )
        return resultado

    def processar_xmls(
        self,
        arquivos: list[tuple[str, bytes]],
        *,
        empresa_id_fallback: int | None = None,
        restringir_empresa_id: int | None = None,
    ) -> UploadResultado:
        """Processa lista de (filename, bytes)."""
        resultado = UploadResultado()
        eventos_adiados: list[tuple[str, bytes]] = []
        for nome, content in arquivos:
            if not nome.lower().endswith(".xml"):
                continue
            resultado.total_arquivos += 1
            if _parece_evento(content):
                eventos_adiados.append((nome, content))  # eventos por último
                continue
            self._processar_xml(
                nome, content, empresa_id_fallback, resultado,
                restringir_empresa_id=restringir_empresa_id,
            )
        for nome, content in eventos_adiados:
            self._processar_xml(
                nome, content, empresa_id_fallback, resultado,
                restringir_empresa_id=restringir_empresa_id,
            )
        return resultado

    def _processar_xml(
        self,
        nome: str,
        xml_bytes: bytes,
        empresa_id_fallback: int | None,
        resultado: UploadResultado,
        *,
        restringir_empresa_id: int | None = None,
    ) -> None:
        det = UploadDetalhe(arquivo=nome)
        try:
            xml_str = xml_bytes.decode("utf-8", errors="replace")
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            det.status = "erro"
            det.mensagem = f"XML invalido: {exc}"
            resultado.erros += 1
            resultado.detalhes.append(det)
            return

        tipo = _detectar_tipo(root)
        if not tipo:
            det.status = "erro"
            det.mensagem = "Tipo de documento nao reconhecido (esperado NFe/CTe/NFSe)"
            resultado.erros += 1
            resultado.detalhes.append(det)
            return
        det.tipo = tipo.value

        # EVENTO (procEventoNFe/CTe) NÃO é um documento novo — é um evento SOBRE
        # uma nota já capturada. Cancelamento (110111) marca a nota como cancelada;
        # outros eventos (Carta de Correção) são ignorados. Sem isto, o evento caía
        # no fluxo normal e virava "duplicado" (nota seguia ATIVA) ou um documento
        # lixo — era a causa de "o sistema não traz as notas canceladas".
        if _eh_evento(root):
            self._aplicar_evento_cancelamento(
                xml_str, tipo, det, resultado, restringir_empresa_id,
            )
            return

        # Parser extrai chave + CNPJs
        try:
            parsed = self.parser.parse(tipo.value, xml_str)
        except Exception as exc:  # noqa: BLE001
            det.status = "erro"
            det.mensagem = f"Falha no parser: {exc}"
            resultado.erros += 1
            resultado.detalhes.append(det)
            return

        chave = parsed.get("chave_acesso") or ""
        det.chave = chave or None
        cnpj_emitente = _normalizar_cnpj(parsed.get("cnpj_emitente"))
        cnpj_destinatario = _normalizar_cnpj(parsed.get("cnpj_destinatario"))

        # Roteamento: empresa = quem é cadastrado (emitente OU destinatario)
        empresa: Empresa | None = None
        origem: str | None = None
        if cnpj_emitente and (e := self._empresa_por_cnpj(cnpj_emitente)):
            empresa = e
            origem = "emitida"
        elif cnpj_destinatario and (e := self._empresa_por_cnpj(cnpj_destinatario)):
            empresa = e
            origem = "recebida"
        elif empresa_id_fallback:
            empresa = self.db.get(Empresa, empresa_id_fallback)
            # Decide origem comparando com o CNPJ da empresa
            if empresa:
                if cnpj_emitente == empresa.cnpj:
                    origem = "emitida"
                elif cnpj_destinatario == empresa.cnpj:
                    origem = "recebida"
                else:
                    origem = "recebida"  # default conservador

        if not empresa:
            det.status = "empresa_nao_cadastrada"
            det.mensagem = (
                f"Nenhuma empresa cadastrada com CNPJ emitente "
                f"({cnpj_emitente}) ou destinatario ({cnpj_destinatario}). "
                "Cadastre a empresa primeiro ou use empresa_id_fallback."
            )
            det.empresa_cnpj = cnpj_emitente or cnpj_destinatario
            resultado.empresa_nao_cadastrada += 1
            resultado.detalhes.append(det)
            return

        # ISOLAMENTO MULTI-TENANT: upload RESTRITO (portal do cliente) só grava
        # nota da PRÓPRIA empresa. Nota resolvida pra OUTRA empresa é PULADA — não
        # grava e NÃO vaza dados (razão/CNPJ) da outra empresa na resposta.
        if restringir_empresa_id is not None and empresa.id != restringir_empresa_id:
            det.status = "fora_do_escopo"
            det.mensagem = "Documento não pertence a esta empresa — ignorado."
            det.empresa_id = None
            det.empresa_cnpj = None
            resultado.fora_do_escopo += 1
            resultado.detalhes.append(det)
            return

        det.empresa_id = empresa.id
        det.empresa_cnpj = empresa.cnpj
        det.origem = origem

        if not chave or len(chave) != 44 or not chave.isdigit():
            # NFSe nem sempre tem chave de 44 dígitos — gera fallback baseado em conteudo
            chave = chave or f"NFSE-{empresa.cnpj}-{parsed.get('numero','')}-{parsed.get('serie','') or '0'}"
            chave = chave[:64]

        # Verifica duplicidade
        existente = self.db.scalar(
            select(DocumentoFiscal).where(
                DocumentoFiscal.empresa_id == empresa.id,
                DocumentoFiscal.tipo_documento == tipo,
                DocumentoFiscal.chave_acesso == chave,
            )
        )
        # Duplicado DE VERDADE só se o existente já tem XML completo. Se existe
        # mas é só RESUMO (recebida da Distribuição, xml_path vazio), NÃO pula:
        # completa o registro com o procNFe que acabou de chegar (pós-Ciência).
        if existente and existente.xml_path:
            det.status = "duplicado"
            det.mensagem = f"Documento ja existe (id={existente.id})"
            resultado.duplicados += 1
            resultado.detalhes.append(det)
            return

        # Salva XML no storage
        data_emissao = parsed.get("data_emissao") or datetime.now()
        try:
            xml_path = self.storage.save_xml(
                empresa_cnpj=empresa.cnpj,
                tipo_documento=tipo.value,
                ano=data_emissao.year,
                mes=data_emissao.month,
                chave=chave,
                xml_content=xml_str,
            )
        except Exception as exc:  # noqa: BLE001
            det.status = "erro"
            det.mensagem = f"Falha ao salvar XML: {exc}"
            resultado.erros += 1
            resultado.detalhes.append(det)
            return

        # tpNF: "1"=saída (venda/remessa), "0"=entrada (nota de entrada própria).
        _tp = (parsed.get("tipo_nf") or "").strip()
        eh_saida = True if _tp == "1" else (False if _tp == "0" else None)

        # Se já existia como RESUMO (sem XML), COMPLETA com o XML que chegou —
        # é a recebida virando completa pós-manifestação. Não cria duplicado.
        if existente:
            existente.xml_path = xml_path
            existente.status = "baixado"
            existente.numero = existente.numero or parsed.get("numero")
            existente.serie = existente.serie or parsed.get("serie")
            if existente.data_emissao is None:
                existente.data_emissao = parsed.get("data_emissao")
            if existente.valor_total is None:
                existente.valor_total = parsed.get("valor_total")
            if existente.eh_saida is None:
                existente.eh_saida = eh_saida
            try:
                self.db.commit()
                resultado.persistidos += 1
                det.status = "ok"
                det.mensagem = "Resumo completado com XML"
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                resultado.erros += 1
                det.status = "erro"
                det.mensagem = f"Falha ao completar resumo: {exc}"
            resultado.detalhes.append(det)
            return

        documento = DocumentoFiscal(
            empresa_id=empresa.id,
            tipo_documento=tipo,
            chave_acesso=chave,
            numero=parsed.get("numero"),
            serie=parsed.get("serie"),
            data_emissao=parsed.get("data_emissao"),
            cnpj_emitente=cnpj_emitente,
            nome_emitente=parsed.get("nome_emitente"),
            cnpj_destinatario=cnpj_destinatario,
            nome_destinatario=parsed.get("nome_destinatario"),
            valor_total=parsed.get("valor_total"),
            status="baixado",
            xml_path=xml_path,
            origem=origem or "emitida",
            eh_saida=eh_saida,
            json_original={"importado_em": datetime.utcnow().isoformat(), "arquivo_origem": nome},
        )
        try:
            self.db.add(documento)
            self.db.commit()
            resultado.persistidos += 1
            det.status = "ok"
        except IntegrityError:
            self.db.rollback()
            resultado.duplicados += 1
            det.status = "duplicado"
            det.mensagem = "Constraint unique disparou (race)"
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            resultado.erros += 1
            det.status = "erro"
            det.mensagem = f"Falha ao persistir: {exc}"

        resultado.detalhes.append(det)

    def _aplicar_evento_cancelamento(
        self,
        xml_str: str,
        tipo: TipoDocumento,
        det: UploadDetalhe,
        resultado: UploadResultado,
        restringir_empresa_id: int | None,
    ) -> None:
        """Aplica um evento (procEventoNFe/CTe). Se for CANCELAMENTO, acha a nota
        pela chave e marca `cancelada=True` (+ motivo/protocolo/data). Eventos que
        não são cancelamento (ex.: Carta de Correção) são ignorados. NUNCA cria
        um DocumentoFiscal a partir de um evento."""
        ev = _parse_evento_cancelamento(xml_str)
        if not ev:
            det.status = "evento_ignorado"
            det.mensagem = "Evento não-cancelamento (ex.: Carta de Correção) — ignorado."
            resultado.eventos_ignorados += 1
            resultado.detalhes.append(det)
            return

        chave = ev["chave"]
        det.chave = chave
        stmt = select(DocumentoFiscal).where(
            DocumentoFiscal.tipo_documento == tipo,
            DocumentoFiscal.chave_acesso == chave,
        )
        # ISOLAMENTO: num upload restrito (portal), só marca nota da própria empresa.
        if restringir_empresa_id is not None:
            stmt = stmt.where(DocumentoFiscal.empresa_id == restringir_empresa_id)
        doc = self.db.scalar(stmt)

        if not doc:
            # A nota ainda não está no sistema (pode chegar num run futuro, ou não
            # foi capturada). Não é erro nem documento — registra pra diagnóstico.
            det.status = "cancelamento_sem_nota"
            det.mensagem = "Evento de cancelamento sem a nota correspondente no sistema."
            resultado.cancelamentos_orfaos += 1
            resultado.detalhes.append(det)
            return

        det.empresa_id = doc.empresa_id
        det.empresa_cnpj = doc.cnpj_emitente
        if doc.cancelada:
            det.status = "duplicado"
            det.mensagem = "Nota já estava marcada como cancelada."
            resultado.duplicados += 1
            resultado.detalhes.append(det)
            return

        doc.cancelada = True
        doc.motivo_cancelamento = (ev.get("motivo") or "")[:255] or None
        doc.protocolo_cancelamento = (ev.get("protocolo") or "")[:30] or None
        doc.cancelada_em = _parse_data_evento(ev.get("data"))
        if not doc.status or doc.status == "baixado":
            doc.status = "cancelada"
        try:
            self.db.commit()
            resultado.cancelamentos += 1
            det.status = "cancelada"
            det.mensagem = "Nota marcada como cancelada pelo evento SEFAZ."
        except Exception as exc:  # noqa: BLE001
            self.db.rollback()
            resultado.erros += 1
            det.status = "erro"
            det.mensagem = f"Falha ao marcar cancelamento: {exc}"
        resultado.detalhes.append(det)
