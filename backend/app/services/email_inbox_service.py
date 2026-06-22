"""Conector de SAÍDAS por e-mail (Nível 2).

O cliente manda um e-mail com os XMLs/ZIP das próprias notas para a caixa única
(ex.: notas@pacgestao.com.br). O PAC lê por IMAP (TLS), extrai os anexos e joga no
MESMO motor de importação (UploadXmlService), que roteia cada nota por CNPJ
emitente/destinatário para a empresa cadastrada. Nota de CNPJ não cadastrado é
ignorada (não vira de ninguém). Dedup já existe (não infla faturamento).

Segurança (skill seguranca-de-dados):
- Senha do IMAP SÓ vem de env (config), nunca do código/DB. Conexão TLS (IMAP4_SSL).
- Só persiste nota cujo CNPJ bate com empresa cadastrada (comportamento padrão do
  UploadXmlService — sem `restringir_empresa_id`, mas o não-casado vira
  `empresa_nao_cadastrada` e NÃO é gravado).
- Auditoria por e-mail: remetente + quantos persistidos (SEM dado sensível/anexo).
- Caixa é aberta a qualquer remetente; a checagem de CNPJ é a barreira. Travar por
  lista de remetentes por empresa é evolução futura.
"""
from __future__ import annotations

import email
import imaplib
import logging
from dataclasses import dataclass, field
from email.message import Message

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.upload_xml_service import UploadResultado, UploadXmlService

logger = logging.getLogger("pac.conector_email")

# Anexo individual maior que isto é ignorado (anti-DoS de caixa pública).
_MAX_ANEXO_BYTES = 60 * 1024 * 1024


@dataclass(slots=True)
class ResultadoCaixa:
    emails_lidos: int = 0
    anexos: int = 0
    persistidos: int = 0
    duplicados: int = 0
    nao_cadastrada: int = 0
    erros: int = 0
    remetentes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "emails_lidos": self.emails_lidos,
            "anexos": self.anexos,
            "persistidos": self.persistidos,
            "duplicados": self.duplicados,
            "nao_cadastrada": self.nao_cadastrada,
            "erros": self.erros,
            "remetentes": self.remetentes[:50],  # amostra, sem inundar
        }


def _eh_anexo_util(part: Message) -> tuple[str, bool] | None:
    """Retorna (nome, eh_zip) se a parte for um XML/ZIP aproveitável, senão None."""
    nome = part.get_filename() or ""
    ctype = (part.get_content_type() or "").lower()
    low = nome.lower()
    if low.endswith(".zip") or ctype in ("application/zip", "application/x-zip-compressed"):
        return (nome or "anexo.zip", True)
    if low.endswith(".xml") or ctype in ("application/xml", "text/xml"):
        return (nome or "nota.xml", False)
    return None


class EmailInboxService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.upload = UploadXmlService(db)

    def _acumular(self, res: ResultadoCaixa, r: UploadResultado) -> None:
        res.anexos += 1
        res.persistidos += r.persistidos
        res.duplicados += r.duplicados
        res.nao_cadastrada += r.empresa_nao_cadastrada
        res.erros += r.erros

    def _processar_email(self, raw: bytes, res: ResultadoCaixa) -> None:
        msg = email.message_from_bytes(raw)
        remetente = (msg.get("From") or "?").strip()
        antes = res.persistidos
        xmls_soltos: list[tuple[str, bytes]] = []

        for part in msg.walk():
            if part.is_multipart():
                continue
            info = _eh_anexo_util(part)
            if not info:
                continue
            nome, eh_zip = info
            try:
                conteudo = part.get_payload(decode=True)
            except Exception:  # noqa: BLE001
                conteudo = None
            if not conteudo or len(conteudo) > _MAX_ANEXO_BYTES:
                continue
            if eh_zip:
                try:
                    r = self.upload.processar_zip(conteudo)
                    self._acumular(res, r)
                except Exception:  # noqa: BLE001
                    res.erros += 1
                    logger.exception("Falha ao processar ZIP de e-mail")
            else:
                xmls_soltos.append((nome, conteudo))

        if xmls_soltos:
            try:
                r = self.upload.processar_xmls(xmls_soltos)
                self._acumular(res, r)
            except Exception:  # noqa: BLE001
                res.erros += 1
                logger.exception("Falha ao processar XMLs soltos de e-mail")

        res.remetentes.append(remetente)
        # Auditoria SEM dado sensível (quem mandou, quanto entrou).
        logger.info(
            "AUDITORIA conector-email: de=%s persistidos=%s",
            remetente, res.persistidos - antes,
        )

    def processar(self, max_emails: int | None = None) -> ResultadoCaixa:
        """Lê os e-mails NÃO LIDOS da caixa, importa os anexos e marca como lidos."""
        res = ResultadoCaixa()
        if not self.settings.conector_email_ativo:
            raise RuntimeError(
                "Conector de e-mail desligado: configure IMAP_HOST/IMAP_USER/IMAP_PASSWORD."
            )
        limite = max_emails or self.settings.imap_max_emails

        conn = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port)
        try:
            conn.login(self.settings.imap_user, self.settings.imap_password)
            conn.select(self.settings.imap_folder)
            typ, dados = conn.uid("search", None, "UNSEEN")
            if typ != "OK":
                raise RuntimeError(f"IMAP search falhou: {typ}")
            uids = (dados[0].split() if dados and dados[0] else [])[:limite]
            for uid in uids:
                try:
                    # BODY.PEEK[] = lê SEM marcar \Seen (só marco após processar OK,
                    # senão um e-mail que falhe no meio ficaria "lido" e não voltaria).
                    typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        res.erros += 1
                        continue
                    raw = msg_data[0][1]
                    self._processar_email(raw, res)
                    res.emails_lidos += 1
                    # Marca como lido só DEPOIS de processar (se cair antes, reprocessa).
                    conn.uid("store", uid, "+FLAGS", "(\\Seen)")
                except Exception:  # noqa: BLE001 — um e-mail ruim não derruba a rodada
                    res.erros += 1
                    logger.exception("Falha ao processar um e-mail (uid=%s)", uid)
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
        return res
