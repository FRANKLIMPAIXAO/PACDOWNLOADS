"""Download de NFS-e pelo ADN (Ambiente de Dados Nacional) da Receita Federal.

API REST+JSON do ADN Contribuinte, mTLS com o e-CNPJ A1 da PRÓPRIA empresa
(não dá pra consultar CNPJ de terceiro). Modelo cursor NSU: cada chamada devolve
um lote a partir do NSU pedido; guardamos o maior NSU e continuamos daí
(incremental). De graça (≠ Focus). Porta do pacote Node do PACSERVICE.

Vem TUDO junto: prestadas (emitidas), tomadas (recebidas) e eventos
(cancelamento/substituição). O ArquivoXml vem base64 → gzip → XML UTF-8.

Endpoints: produção `adn.nfse.gov.br/contribuintes` ·
homologação `adn.producaorestrita.nfse.gov.br/contribuintes`.
"""
from __future__ import annotations

import base64
import gzip
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from app.providers.nfe_distribuicao import NFeDistribuicaoProvider

logger = logging.getLogger(__name__)

HOST_PROD = "adn.nfse.gov.br"
HOST_HOM = "adn.producaorestrita.nfse.gov.br"

STATUS_OK = "DOCUMENTOS_LOCALIZADOS"
STATUS_VAZIO = "NENHUM_DOCUMENTO_LOCALIZADO"
STATUS_REJEICAO = "REJEICAO"


@dataclass
class DocNfse:
    nsu: int
    chave_acesso: str | None
    tipo_documento: str | None        # NFSe | EVENTO
    tipo_evento: str | None
    data_hora_geracao: str | None
    xml: str | None


@dataclass
class ResultadoNfse:
    documentos: list[DocNfse] = field(default_factory=list)
    total: int = 0
    lotes: int = 0
    cursor_final: int = 0
    motivo_parada: str = "limite_lotes"
    erros: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)


def decode_documento(base64_gzip: str) -> str:
    """ArquivoXml (base64 → gzip → XML UTF-8)."""
    if not base64_gzip:
        raise ValueError("decode_documento: entrada vazia")
    buf = base64.b64decode(base64_gzip)
    if len(buf) >= 2 and buf[0] == 0x1F and buf[1] == 0x8B:  # cabeçalho gzip
        return gzip.decompress(buf).decode("utf-8")
    # alguns ambientes devolvem o XML direto (sem gzip)
    return buf.decode("utf-8")


class NFSeAdnProvider:
    def __init__(self) -> None:
        self.homolog = os.getenv("NFSE_ADN_HOMOLOG", "false").lower() == "true"
        self.host = HOST_HOM if self.homolog else HOST_PROD
        self.base = "/contribuintes"
        self.timeout = int(os.getenv("NFSE_ADN_TIMEOUT_S", "30"))
        self.max_retries = int(os.getenv("NFSE_ADN_RETRIES", "4"))

    # ------------------------------------------------------------------
    def sincronizar(
        self, *, cnpj: str, pfx_path: str, pfx_senha: str,
        cursor_inicial: int = 0, max_lotes: int = 50, intervalo_ms: int = 300,
    ) -> ResultadoNfse:
        cnpj_num = "".join(c for c in (cnpj or "") if c.isdigit())
        if len(cnpj_num) != 14:
            raise ValueError(f"CNPJ inválido: {cnpj}")
        cert_pem, key_pem = NFeDistribuicaoProvider._pfx_para_pem(pfx_path, pfx_senha)

        cert_f = tempfile.NamedTemporaryFile(delete=False, suffix=".crt.pem")
        key_f = tempfile.NamedTemporaryFile(delete=False, suffix=".key.pem")
        res = ResultadoNfse(cursor_final=int(cursor_inicial or 0))
        cursor = int(cursor_inicial or 0)
        vazios = 0
        try:
            cert_f.write(cert_pem); cert_f.close()
            key_f.write(key_pem); key_f.close()
            cert = (cert_f.name, key_f.name)
            for _ in range(max_lotes):
                proximo = cursor + 1
                resp = self._get_dfe(proximo, cnpj_num, cert)
                status = resp.status_code

                if status in (400, 404):
                    res.motivo_parada = f"http_{status}"
                    break
                if status >= 500:
                    res.erros.append(f"HTTP {status} no NSU {proximo}")
                    res.motivo_parada = f"http_{status}"
                    break
                try:
                    env = resp.json()
                except Exception:  # noqa: BLE001
                    res.erros.append(f"resposta não-JSON (status={status})")
                    res.motivo_parada = "resposta_invalida"
                    break

                for a in (env.get("Alertas") or []):
                    if a:
                        res.alertas.append(str(a))
                sp = env.get("StatusProcessamento")
                if sp == STATUS_REJEICAO:
                    res.erros.extend(str(e) for e in (env.get("Erros") or []))
                    res.motivo_parada = "rejeicao"
                    break
                if sp == STATUS_VAZIO:
                    res.motivo_parada = "fim_fila"
                    break

                lote = env.get("LoteDFe") or []
                if not lote:
                    vazios += 1
                    if vazios >= 3:
                        res.motivo_parada = "lote_vazio_persistente"
                        break
                    time.sleep(intervalo_ms / 1000)
                    continue
                vazios = 0

                maior = cursor
                for item in lote:
                    try:
                        nsu_item = int(item.get("NSU"))
                    except (TypeError, ValueError):
                        nsu_item = cursor
                    if nsu_item > maior:
                        maior = nsu_item
                    try:
                        arq = item.get("ArquivoXml")
                        xml = decode_documento(arq) if arq else None
                        res.documentos.append(DocNfse(
                            nsu=nsu_item,
                            chave_acesso=item.get("ChaveAcesso"),
                            tipo_documento=item.get("TipoDocumento"),
                            tipo_evento=item.get("TipoEvento"),
                            data_hora_geracao=item.get("DataHoraGeracao"),
                            xml=xml,
                        ))
                        res.total += 1
                    except Exception as exc:  # noqa: BLE001
                        res.erros.append(f"NSU {nsu_item}: {exc}")

                if maior <= cursor:
                    res.motivo_parada = "estagnacao"
                    break
                cursor = maior
                res.lotes += 1
                res.cursor_final = cursor
                if intervalo_ms > 0:
                    time.sleep(intervalo_ms / 1000)
        finally:
            for f in (cert_f.name, key_f.name):
                try:
                    os.unlink(f)
                except OSError:
                    pass
        return res

    # ------------------------------------------------------------------
    def _get_dfe(self, nsu: int, cnpj: str, cert):
        url = f"https://{self.host}{self.base}/DFe/{nsu}"
        params = {"cnpjConsulta": cnpj, "lote": "true"}
        headers = {"Accept": "application/json", "Accept-Encoding": "identity",
                   "User-Agent": "pac-download/1.0 (+adn)"}
        last = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = requests.get(url, params=params, headers=headers, cert=cert,
                                 timeout=self.timeout)
                if 500 <= r.status_code < 600 and attempt < self.max_retries:
                    time.sleep(min(2 * 2 ** (attempt - 1), 15))
                    continue
                return r
            except requests.RequestException as exc:
                last = exc
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2 * 2 ** (attempt - 1), 15))
        if last:
            raise last
        raise RuntimeError("falha inesperada no _get_dfe")
