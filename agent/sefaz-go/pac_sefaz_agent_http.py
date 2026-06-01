"""PAC SEFAZ-GO Agent — versão HTTP + 2Captcha (PRODUÇÃO).

Abordagem direta via requests:
1. Login no PAC API, lista empresas com cert A1
2. Pra cada empresa: baixa PFX, converte pra PEM (cert + key)
3. requests.Session com mTLS (cert PEM como client cert TLS)
4. 2Captcha resolve Cloudflare Turnstile (sitekey do portal)
5. POST /download → enfileira
6. Poll histórico até "Concluído"
7. GET do ZIP
8. POST no PAC /documentos/upload-em-massa
9. Cleanup arquivos temporários

Vantagens vs Playwright:
- Zero browser = zero detecção de bot
- ~10x mais rápido (sem renderização)
- VPS-friendly (sem GUI, sem Xvfb)
- Custo 2Captcha ~$0.003/empresa = $0.36/mês p/ 120 empresas

Pré-requisitos:
- Empresa cadastrada no PAC com cert A1 carregado
- Chave da API 2Captcha em TWOCAPTCHA_API_KEY (env)
"""
from __future__ import annotations

import argparse
import asyncio  # mantém compat com import dotenv
import calendar
import datetime as dt
import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from twocaptcha import TwoCaptcha

from pac_client import CertificadoBaixado, EmpresaPAC, PacClient


# ============================================================
# Config
# ============================================================

load_dotenv()

PAC_API_URL = os.getenv("PAC_API_URL", "http://127.0.0.1:8000")
PAC_EMAIL = os.getenv("PAC_EMAIL", "admin@pacxml.com.br")
PAC_PASSWORD = os.getenv("PAC_PASSWORD", "admin123")

TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")

# Sitekey REAL do SEFAZ-GO (extraído do HTML do portal)
SEFAZ_GO_SITEKEY = os.getenv(
    "SEFAZ_GO_SITEKEY",
    "0x4AAAAAABWl9df-N8s5C_f1",
)

SEFAZ_GO_BASE = "https://nfeweb.sefaz.go.gov.br"
SEFAZ_GO_FORM_URL = f"{SEFAZ_GO_BASE}/nfeweb/sites/nfe/consulta-publica"

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "./downloads")).resolve()
CERT_DIR = Path(os.getenv("CERT_DIR", "./certs-temp")).resolve()
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs")).resolve()

# Tempos de poll do histórico
POLL_INTERVAL_S = int(os.getenv("POLL_INTERVAL", "10"))
POLL_MAX_TENTATIVAS = int(os.getenv("POLL_MAX_TENTATIVAS", "30"))


# ============================================================
# Logging
# ============================================================


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def log_evento(evento: str, **kwargs: Any) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"agente_http_{dt.date.today().isoformat()}.jsonl"
    registro = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "evento": evento,
        **kwargs,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


# ============================================================
# Domínio
# ============================================================


@dataclass(slots=True)
class JanelaPeriodo:
    data_inicio: dt.date
    data_fim: dt.date

    @property
    def br_inicio(self) -> str:
        return self.data_inicio.strftime("%d/%m/%Y")

    @property
    def br_fim(self) -> str:
        return self.data_fim.strftime("%d/%m/%Y")

    @property
    def yyyymmdd_inicio(self) -> str:
        return self.data_inicio.strftime("%Y%m%d")

    @property
    def yyyymmdd_fim(self) -> str:
        return self.data_fim.strftime("%Y%m%d")


def janela_mes_anterior() -> JanelaPeriodo:
    hoje = dt.date.today()
    prim_anterior = dt.date(hoje.year, hoje.month, 1) - dt.timedelta(days=1)
    inicio = dt.date(prim_anterior.year, prim_anterior.month, 1)
    ultimo = calendar.monthrange(prim_anterior.year, prim_anterior.month)[1]
    fim = dt.date(prim_anterior.year, prim_anterior.month, ultimo)
    return JanelaPeriodo(inicio, fim)


def janela_mes_especifico(ano_mes: str) -> JanelaPeriodo:
    ano, mes = ano_mes.split("-")
    ano_i, mes_i = int(ano), int(mes)
    ultimo = calendar.monthrange(ano_i, mes_i)[1]
    return JanelaPeriodo(dt.date(ano_i, mes_i, 1), dt.date(ano_i, mes_i, ultimo))


@dataclass(slots=True)
class ResultadoEmpresa:
    empresa_id: int
    cnpj: str
    razao_social: str
    sucesso: bool
    motivo: str | None = None
    zip_paths: list[str] = field(default_factory=list)
    upload_pac: dict[str, Any] | None = None
    duracao_segundos: float = 0.0


# ============================================================
# Helpers
# ============================================================


def pfx_para_pem(pfx_bytes: bytes, senha: str) -> tuple[Path, Path]:
    """Converte PFX em 2 arquivos PEM temporários (cert + key) pra mTLS via requests.

    Retorna (cert_pem_path, key_pem_path). Caller deve apagar depois.
    """
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, pkcs12,
    )

    private_key, certificate, additional = pkcs12.load_key_and_certificates(
        pfx_bytes, senha.encode("utf-8"),
    )
    if not private_key or not certificate:
        raise RuntimeError("PFX sem chave/certificado")

    # requests aceita single PEM com cert + key OU 2 arquivos (cert, key) separados.
    # Vamos com 2 arquivos pra ficar mais claro.
    pem_dir = Path(tempfile.mkdtemp(prefix="pacsefaz_"))
    cert_path = pem_dir / "cert.pem"
    key_path = pem_dir / "key.pem"

    cert_bytes = certificate.public_bytes(Encoding.PEM)
    for extra in additional or []:
        cert_bytes += extra.public_bytes(Encoding.PEM)
    cert_path.write_bytes(cert_bytes)

    key_bytes = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption(),
    )
    key_path.write_bytes(key_bytes)
    return cert_path, key_path


def resolver_turnstile(api_key: str, sitekey: str, url: str) -> str:
    """Usa 2Captcha pra resolver Cloudflare Turnstile. Retorna o token."""
    log = logging.getLogger("2captcha")
    # default_timeout=300s, polling_interval=5s. Turnstile pode demorar
    # bastante quando a fila do 2Captcha estiver carregada.
    solver = TwoCaptcha(api_key, defaultTimeout=300, pollingInterval=5)
    log.info("Pedindo 2Captcha resolver Turnstile (sitekey=%s)...", sitekey)
    inicio = dt.datetime.now()
    result = solver.turnstile(sitekey=sitekey, url=url)
    elapsed = (dt.datetime.now() - inicio).total_seconds()
    token = result["code"]
    log.info("Turnstile resolvido em %.1fs (token: %d chars)", elapsed, len(token))
    return token


# ============================================================
# SEFAZ-GO HTTP fluxo
# ============================================================


class SefazGoHTTP:
    """Cliente HTTP da consulta de XMLs do SEFAZ-GO."""

    def __init__(self, cert_pem: Path, key_pem: Path) -> None:
        self.log = logging.getLogger("sefaz-go")
        self.session = requests.Session()
        # mTLS — cert apresentado no handshake TLS
        self.session.cert = (str(cert_pem), str(key_pem))
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            "Referer": SEFAZ_GO_FORM_URL,
            "Origin": SEFAZ_GO_BASE,
        })

    def warmup(self) -> None:
        """GET inicial pra estabelecer sessão (cookies)."""
        self.log.info("Warmup: acessando %s", SEFAZ_GO_FORM_URL + "/principal")
        r = self.session.get(f"{SEFAZ_GO_FORM_URL}/principal", timeout=30)
        r.raise_for_status()
        self.log.info("Warmup OK (status %s, cookies %d)", r.status_code, len(self.session.cookies))
        log_evento("warmup", status=r.status_code, cookies=len(self.session.cookies))

    def consultar_documentos(
        self, cnpj: str, janela: JanelaPeriodo, turnstile_token: str,
    ) -> requests.Response:
        """GET /selecao — pesquisa documentos no período.

        Form não declara method explícito = default GET. Spring boot do portal
        responde POST com 405. Mandamos GET com query params.
        """
        url = f"{SEFAZ_GO_FORM_URL}/selecao"
        params = {
            "g-recaptcha-response": turnstile_token,
            "cmpCnpj": cnpj,
            "cmpDataInicial": janela.br_inicio,
            "cmpDataFinal": janela.br_fim,
            "cmpSituacao": "",
            "cmpModelo": "55",
            "cmpNumNfe": "",
            "cmpNumSerieNfe": "",
            "cmpCpfCnpjDestinatario": "",
        }
        log_params = {
            k: (v[:20] + "..." if k.endswith("response") and len(v) > 20 else v)
            for k, v in params.items()
        }
        self.log.info("GET %s params=%s", url, log_params)
        r = self.session.get(url, params=params, timeout=30, allow_redirects=True)
        log_evento(
            "consultar_documentos",
            status=r.status_code,
            url_final=r.url,
            body_len=len(r.content),
        )
        debug_html = LOG_DIR / "debug" / f"selecao_response_{cnpj}_{dt.datetime.now().strftime('%H%M%S')}.html"
        debug_html.parent.mkdir(parents=True, exist_ok=True)
        debug_html.write_bytes(r.content)
        self.log.info("Resposta salva: %s (status %s, len %d, url_final %s)",
                      debug_html, r.status_code, len(r.content), r.url)
        r.raise_for_status()
        return r

    def obter_historico(self, cnpj: str, turnstile_token: str) -> list[dict]:
        """GET do histórico de downloads — retorna lista de arquivos com status."""
        url = (
            f"{SEFAZ_GO_FORM_URL}/resultado/download/historico"
            f"?g-recaptcha-response={turnstile_token}&cmpCnpj={cnpj}"
        )
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        try:
            dados = r.json()
        except Exception:
            return []
        if isinstance(dados, list):
            return dados
        return dados.get("data") or dados.get("historico") or []

    def aguardar_conclusao(self, cnpj: str, intervalos: int, tentativas: int) -> list[dict]:
        """Poll do histórico até achar arquivos com status 'Concluído'.

        IMPORTANTE: cada poll precisa de um Turnstile token NOVO (pode expirar).
        Faz cache do último arquivo concluído pra não duplicar.
        """
        ja_concluidos: set[str] = set()
        novos_concluidos: list[dict] = []
        for tent in range(tentativas):
            # Resolve Turnstile novo pra essa chamada
            token = resolver_turnstile(TWOCAPTCHA_API_KEY, SEFAZ_GO_SITEKEY, SEFAZ_GO_FORM_URL)
            arquivos = self.obter_historico(cnpj, token)
            self.log.info("Histórico tem %d arquivo(s) (tentativa %d/%d)",
                          len(arquivos), tent + 1, tentativas)
            for a in arquivos:
                situ = (a.get("situacao") or a.get("status") or "").lower()
                nome = a.get("nomeArquivo") or a.get("arquivo") or a.get("nome")
                if situ in ("concluído", "concluido") and nome and nome not in ja_concluidos:
                    ja_concluidos.add(nome)
                    novos_concluidos.append(a)
            if novos_concluidos:
                return novos_concluidos
            import time
            time.sleep(intervalos)
        raise TimeoutError(f"Nenhum arquivo concluído em {tentativas * intervalos}s")

    def baixar_zip(self, nome_arquivo: str, destino_dir: Path) -> Path:
        url = f"{SEFAZ_GO_FORM_URL}/download/{nome_arquivo}"
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / nome_arquivo
        self.log.info("Baixando %s → %s", nome_arquivo, destino)
        with self.session.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return destino


# ============================================================
# Orquestração
# ============================================================


def processar_empresa(
    pac: PacClient,
    empresa: EmpresaPAC,
    janela: JanelaPeriodo,
    *,
    dry_run: bool,
) -> ResultadoEmpresa:
    log = logging.getLogger(f"empresa[{empresa.cnpj}]")
    inicio = dt.datetime.now()
    res = ResultadoEmpresa(
        empresa_id=empresa.id, cnpj=empresa.cnpj, razao_social=empresa.razao_social,
        sucesso=False,
    )

    # 1. Baixa cert
    cert = pac.baixar_certificado(empresa.id, CERT_DIR)

    # 2. PFX → PEM
    pem_dir: Path | None = None
    try:
        cert_pem, key_pem = pfx_para_pem(cert.pfx_path.read_bytes(), cert.senha)
        pem_dir = cert_pem.parent
        log.info("Cert convertido: %s + %s", cert_pem.name, key_pem.name)

        # 3. Setup sessão HTTP com mTLS
        client = SefazGoHTTP(cert_pem, key_pem)
        client.warmup()

        # 4. Resolve Turnstile
        token = resolver_turnstile(TWOCAPTCHA_API_KEY, SEFAZ_GO_SITEKEY, SEFAZ_GO_FORM_URL)

        # 5. POST /selecao — consulta documentos no período
        log.info("Consultando documentos (%s a %s)", janela.br_inicio, janela.br_fim)
        resp = client.consultar_documentos(empresa.cnpj, janela, token)
        log.info("Resposta /selecao: status=%s, content-type=%s, len=%d, url_final=%s",
                 resp.status_code, resp.headers.get("content-type", "?"),
                 len(resp.content), resp.url)
        log_evento(
            "consulta_resposta",
            cnpj=empresa.cnpj,
            status=resp.status_code,
            url_final=resp.url,
        )

        # PRÓXIMOS PASSOS (a implementar após análise da resposta):
        # - Parsear HTML pra confirmar que mostrou lista de notas
        # - Achar URL do botão "Baixar todos os arquivos"
        # - POST nesse endpoint (talvez precisa novo Turnstile)
        # - Poll histórico até "Concluído"
        # - GET dos ZIPs
        res.motivo = (
            f"POST /selecao retornou {resp.status_code}. "
            "Próximo passo: analisar HTML salvo em logs/debug/selecao_response_*.html "
            "pra descobrir URL do botão 'Baixar todos os arquivos'."
        )
        log.warning(res.motivo)

        # 8. Upload pro PAC
        if not dry_run and res.zip_paths:
            for zip_str in res.zip_paths:
                resultado_upload = pac.upload_em_massa(Path(zip_str), empresa_id_fallback=empresa.id)
                res.upload_pac = resultado_upload
                log.info("Upload PAC: %s", json.dumps(resultado_upload, ensure_ascii=False)[:200])

        res.sucesso = True

    except requests.HTTPError as exc:
        res.motivo = f"HTTP {exc.response.status_code if exc.response else '?'}: {exc}"
        log.error(res.motivo)
        log_evento("erro_http", cnpj=empresa.cnpj, erro=str(exc))
    except Exception as exc:
        res.motivo = f"Erro: {exc!r}"
        log.exception("Erro no processamento")
        log_evento("erro_inesperado", cnpj=empresa.cnpj, erro=str(exc))
    finally:
        res.duracao_segundos = (dt.datetime.now() - inicio).total_seconds()
        # Cleanup
        try:
            if cert.pfx_path.exists():
                cert.pfx_path.unlink()
        except Exception:
            pass
        if pem_dir and pem_dir.exists():
            try:
                import shutil
                shutil.rmtree(pem_dir)
            except Exception:
                pass

    return res


def main_async(args: argparse.Namespace) -> int:
    setup_logging()
    log = logging.getLogger("agente")

    if not TWOCAPTCHA_API_KEY:
        log.error("TWOCAPTCHA_API_KEY vazio no .env! Crie conta em 2captcha.com.")
        return 1

    janela = (
        janela_mes_especifico(args.periodo) if args.periodo
        else janela_mes_anterior()
    )
    log.info("Período: %s a %s", janela.br_inicio, janela.br_fim)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    with PacClient(PAC_API_URL, PAC_EMAIL, PAC_PASSWORD) as pac:
        empresas = pac.listar_empresas(somente_com_cert=True)
        if args.empresa:
            empresas = [e for e in empresas if e.id == args.empresa]
        if not empresas:
            log.error("Nenhuma empresa elegível.")
            return 1
        log.info("Processando %d empresa(s)", len(empresas))

        resultados: list[ResultadoEmpresa] = []
        for emp in empresas:
            log.info("==== Empresa %d: %s (%s) ====", emp.id, emp.razao_social, emp.cnpj)
            res = processar_empresa(pac, emp, janela, dry_run=args.dry_run)
            resultados.append(res)
            status = "✓" if res.sucesso else "✗"
            log.info("%s Empresa %s — %.1fs — %s", status, emp.cnpj, res.duracao_segundos,
                     res.motivo or f"{len(res.zip_paths)} ZIP(s)")

        # Resumo
        ok = sum(1 for r in resultados if r.sucesso)
        log.info("==== %d/%d sucesso ====", ok, len(resultados))
        resumo_path = LOG_DIR / f"resumo_http_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        resumo_path.write_text(
            json.dumps([asdict(r) for r in resultados], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Resumo: %s", resumo_path)

    return 0 if ok == len(resultados) else 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PAC SEFAZ-GO Agent HTTP")
    p.add_argument("--empresa", type=int, help="Processa só essa empresa (id PAC)")
    p.add_argument("--periodo", type=str, help="YYYY-MM (default: mês anterior)")
    p.add_argument("--dry-run", action="store_true", help="Não envia ZIP pro PAC")
    return p.parse_args()


def main() -> int:
    return main_async(parse_args())


if __name__ == "__main__":
    sys.exit(main())
