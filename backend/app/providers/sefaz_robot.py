"""Robô SEFAZ — emissão automática de CNDs nos portais oficiais.

Cada CND tem seu portal próprio:
- FEDERAL    → solucoes.receita.fazenda.gov.br/Servicos/certidaointernet/PJ/Emitir
              (RFB+PGFN unificadas; sem cert: reCAPTCHA / com eCNPJ A1: eCAC SAML)
- TRABALHISTA → cndt-certidao.tst.jus.br/inicio.faces
              (CNPJ + captcha de imagem)
- FGTS       → consulta-crf.caixa.gov.br/consultacrf
              (CNPJ + captcha; ou via Conectividade Social com eCNPJ)
- ESTADUAL   → varia por SEFAZ (PE, SP, RJ, ...) — fora do MVP
- MUNICIPAL  → varia por prefeitura — fora do MVP

Esta arquitetura segue o mesmo padrão do `focus_nfe.py`:
- Classe base `SefazRobotProvider` com método `emitir_cnd(...)`
- Implementacao real (Playwright + serviço anti-captcha) — STUB nesta fase
- Mock determinístico para desenvolvimento (`USE_MOCK_SEFAZ=true`)

Uso típico:
    provider = SefazRobotProvider()
    pdf_bytes, metadata = provider.emitir_cnd(
        cnpj="12345678000195",
        tipo="FEDERAL",
        certificado_pfx=None,           # opcional para Federal/Trabalhista
        certificado_senha=None,
    )
    # metadata: {"numero": "...", "data_emissao": "YYYY-MM-DD", "data_validade": "YYYY-MM-DD"}

Para sair do mock:
1. Contratar serviço anti-captcha (2captcha.com ou anti-captcha.com — ~US$ 1/1000 captchas)
2. Instalar Playwright: `pip install playwright && playwright install chromium`
3. Implementar os métodos `_emitir_*_real` em `SefazRobotProvider`
4. Setar `USE_MOCK_SEFAZ=false` e `CAPTCHA_API_KEY=...` no .env
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from app.config import get_settings


settings = get_settings()


TipoCnd = Literal["FEDERAL", "FEDERAL_OFICIAL", "TRABALHISTA", "FGTS", "ESTADUAL", "MUNICIPAL"]


# --- Validades (em dias) por tipo ---
# FEDERAL (SITFIS via Integra Contador): 60d — relatorio detalhado da situacao
#     fiscal RFB+PGFN. Para uso interno do escritorio (controle mensal).
# FEDERAL_OFICIAL (CND Conjunta RFB+PGFN via portal): 180d (Lei 9.430/96 art.47
#     + Portaria PGFN/MF 33/2018). Necessaria para licitacoes/bancos/contratos.
# Trabalhista: 180d (Lei 12.440/2011 art. 1)
# FGTS: 30d
# Estadual/Municipal: varia (180d eh padrao geral)
VALIDADES_DIAS: dict[str, int] = {
    "FEDERAL": 60,             # SITFIS (Integra Contador)
    "FEDERAL_OFICIAL": 180,    # CND oficial RFB+PGFN (portal)
    "TRABALHISTA": 180,
    "FGTS": 30,
    "ESTADUAL": 180,
    "MUNICIPAL": 180,
}


def _gerar_pdf_minimo(titulo: str, linhas: list[str]) -> bytes:
    """Gera um PDF minimo valido (renderizavel em browsers) sem dep externa.

    Util para mocks ate o scraper real estar implementado — antes era so
    um header `%PDF-1.4` seguido de texto, o que faz Chrome/Firefox falhar
    com "Falha ao carregar documento PDF". Agora cria um PDF de 1 pagina A4
    com o titulo + linhas em Helvetica.

    Usa `Tm` (text matrix) para posicionamento absoluto de cada linha — `Td`
    eh relativo e bagunca quando misturado com mudanca de fonte. Tambem
    sanitiza chars fora do WinAnsiEncoding (em-dash, aspas curvas, etc.).
    """
    # Sanitiza chars que WinAnsi nao tem (em-dash -> hyphen, etc.)
    SANI = {
        "—": "-", "–": "-", "‒": "-", "−": "-",
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "…": "...", "•": "*", "·": "-",
    }

    def _clean(s: str) -> str:
        for k, v in SANI.items():
            s = s.replace(k, v)
        return s

    def _esc(s: str) -> str:
        # Escape de parenteses (delimitadores PDF) e backslash
        s = _clean(s)
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y = 780
    line_height = 16
    content_parts = [
        "BT",
        "/F1 16 Tf",
        f"1 0 0 1 50 {y} Tm",
        f"({_esc(titulo)}) Tj",
        "ET",
    ]
    y -= 28
    for linha in linhas:
        content_parts.extend([
            "BT",
            "/F1 11 Tf",
            f"1 0 0 1 50 {y} Tm",
            f"({_esc(linha)}) Tj",
            "ET",
        ])
        y -= line_height
    content_stream = "\n".join(content_parts).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    # 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # 2: Pages
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    # 3: Page (A4 = 595 x 842)
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 "
        b"/BaseFont /Helvetica /Encoding /WinAnsiEncoding >> >> >> "
        b"/Contents 4 0 R >>"
    )
    # 4: Content stream
    objects.append(
        b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n"
        + content_stream + b"\nendstream"
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    return bytes(out)


class SefazRobotError(Exception):
    """Erro generico do robo SEFAZ."""


class CertidaoNegativaIndisponivelError(SefazRobotError):
    """Portal retornou que a empresa tem pendencia (sem CND positiva).
    Para esses casos, eh emitido CND POSITIVA COM EFEITO DE NEGATIVA quando ha
    parcelamento ativo. Caso contrario, falha."""


@dataclass(slots=True)
class CndEmitida:
    pdf_bytes: bytes
    numero: str
    data_emissao: date
    data_validade: date
    tipo: str
    portal: str
    raw: dict | None = None


# ============================================================
#  PROVIDER
# ============================================================


class SefazRobotProvider:
    """Robô que emite CNDs automaticamente nos portais oficiais."""

    def emitir_cnd(
        self,
        cnpj: str,
        tipo: TipoCnd,
        *,
        certificado_pfx: bytes | None = None,
        certificado_senha: str | None = None,
    ) -> CndEmitida:
        """Emite uma CND. Retorna PDF + metadados.

        Para FEDERAL: certificado eCNPJ A1 eh recomendado (atende sem captcha).
        Para TRABALHISTA e FGTS: nao precisa cert, apenas CNPJ.
        """
        if settings.use_mock_sefaz:
            return self._emitir_mock(cnpj, tipo)

        # Implementacao real fica para o ciclo de Selenium/Playwright.
        # Cada portal tem fluxo proprio:
        if tipo == "FEDERAL":
            return self._emitir_federal_real(cnpj, certificado_pfx, certificado_senha)
        if tipo == "TRABALHISTA":
            return self._emitir_trabalhista_real(cnpj)
        if tipo == "FGTS":
            return self._emitir_fgts_real(cnpj)
        raise SefazRobotError(f"Emissao real de {tipo} nao implementada nesta fase.")

    # --- Implementacoes REAIS (a implementar em ciclo proprio) ---

    def _emitir_federal_real(
        self, cnpj: str, cert_pfx: bytes | None, cert_senha: str | None,
    ) -> CndEmitida:
        """STUB. Implementacao real:

        1. Se cert_pfx: usa Playwright com client cert no contexto do navegador.
           Acessa eCAC -> Certidoes -> Emitir CND. Sem captcha.
        2. Senao: anti-captcha (2captcha) para resolver reCAPTCHA do portal.
        3. Faz GET na URL final do PDF e devolve bytes.

        Validade do PDF: 180 dias. Numero da certidao no proprio PDF.
        """
        raise SefazRobotError(
            "Emissao FEDERAL real ainda nao implementada. "
            "Setar USE_MOCK_SEFAZ=true para usar mock. "
            "Producao: contratar 2captcha.com e descomentar implementacao em "
            "app/providers/sefaz_robot.py"
        )

    def _emitir_trabalhista_real(self, cnpj: str) -> CndEmitida:
        """Emite CND Trabalhista (CNDT) no portal TST.

        Fluxo:
        1. Abre `https://cndt-certidao.tst.jus.br/gerarCertidao.faces` com Playwright.
        2. Preenche CNPJ.
        3. Captura imagem do captcha (texto distorcido).
        4. Envia para 2captcha resolver.
        5. Submete formulario.
        6. Aguarda PDF retornar (download ou novo iframe).
        7. Le validade do PDF e devolve.

        Erros tratados:
        - Captcha errado: retry uma vez.
        - CNPJ invalido: levanta SefazRobotError.
        - Empresa com debito (CND positiva): retorna CND POSITIVA C/ EFEITO DE NEGATIVA
          se houver parcelamento; senao SefazRobotError.

        Requer:
        - `pip install playwright && playwright install chromium`
        - `CAPTCHA_API_KEY` no .env
        """
        # Lazy import — Playwright e dep opcional pesada (~200MB chromium).
        try:
            from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright
        except ImportError as exc:
            raise SefazRobotError(
                "Playwright nao instalado. Rode: pip install playwright && "
                "playwright install chromium"
            ) from exc

        from app.providers._captcha import (
            CaptchaError,
            reportar_captcha_errado,
            resolver_captcha_imagem,
        )

        url_form = "https://cndt-certidao.tst.jus.br/gerarCertidao.faces"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
            )
            page = context.new_page()

            tentativa = 0
            ultimo_captcha_id: str | None = None
            while tentativa < 2:
                tentativa += 1
                try:
                    page.goto(url_form, timeout=30_000, wait_until="domcontentloaded")

                    # Preenche CNPJ. O nome do input no JSF varia, mas
                    # tipicamente eh `gerarCertidaoForm:cpfCnpj` ou similar.
                    cnpj_input = page.locator(
                        "input[name*='cpfCnpj'], input[id*='cpfCnpj'], input[type='text']"
                    ).first
                    cnpj_input.fill(cnpj)

                    # Captura imagem do captcha
                    captcha_img = page.locator(
                        "img[id*='captcha'], img[src*='captcha'], img[alt*='captcha' i]"
                    ).first
                    captcha_bytes = captcha_img.screenshot()

                    # Resolve via 2captcha
                    try:
                        captcha_texto = resolver_captcha_imagem(captcha_bytes)
                    except CaptchaError as exc:
                        raise SefazRobotError(f"Falha resolvendo captcha CNDT: {exc}") from exc

                    captcha_input = page.locator(
                        "input[name*='captcha'], input[id*='captcha']"
                    ).first
                    captcha_input.fill(captcha_texto)

                    # Submit
                    submit_btn = page.locator(
                        "input[type='submit'], button[type='submit']"
                    ).first
                    with page.expect_download(timeout=30_000) as dl_info:
                        submit_btn.click()
                    download = dl_info.value
                    pdf_path = download.path()
                    if not pdf_path:
                        raise SefazRobotError("Download CNDT sem path local.")
                    pdf_bytes = open(pdf_path, "rb").read()

                    # Detecta se e CND positiva (com debito)
                    if b"POSITIVA" in pdf_bytes.upper() and b"EFEITO DE NEGATIVA" not in pdf_bytes.upper():
                        raise CertidaoNegativaIndisponivelError(
                            "CND TRABALHISTA positiva (com debitos sem parcelamento)."
                        )

                    hoje = date.today()
                    return CndEmitida(
                        pdf_bytes=pdf_bytes,
                        numero=f"CNDT-{cnpj[-8:]}-{hoje.strftime('%Y%m%d')}",
                        data_emissao=hoje,
                        data_validade=hoje + timedelta(days=180),
                        tipo="TRABALHISTA",
                        portal="TST — CNDT",
                        raw={"fonte": "playwright", "tentativas": tentativa},
                    )
                except PWTimeout:
                    if tentativa >= 2:
                        raise SefazRobotError(
                            "Timeout no portal CNDT TST (possivel captcha errado)."
                        )
                    if ultimo_captcha_id:
                        reportar_captcha_errado(ultimo_captcha_id)
                except CertidaoNegativaIndisponivelError:
                    raise
                except SefazRobotError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if tentativa >= 2:
                        raise SefazRobotError(
                            f"Erro inesperado emitindo CNDT: {exc}"
                        ) from exc
                finally:
                    if tentativa >= 2:
                        browser.close()

            browser.close()
            raise SefazRobotError("Falha apos 2 tentativas no portal CNDT.")

    def _emitir_fgts_real(self, cnpj: str) -> CndEmitida:
        """STUB. Portal CRF Caixa. Captcha de imagem."""
        raise SefazRobotError(
            "Emissao FGTS real ainda nao implementada. "
            "Setar USE_MOCK_SEFAZ=true para usar mock."
        )

    # --- Mock determinístico ---

    @staticmethod
    def _emitir_mock(cnpj: str, tipo: TipoCnd) -> CndEmitida:
        """Mock devolve PDF MINIMO VALIDO (renderizavel em browsers) + metadados."""
        hoje = date.today()
        validade = hoje + timedelta(days=VALIDADES_DIAS.get(tipo, 180))
        portal = {
            "FEDERAL": "Integra Contador — SITFIS",
            "FEDERAL_OFICIAL": "Receita Federal + PGFN (CND oficial)",
            "TRABALHISTA": "TST — CNDT",
            "FGTS": "Caixa Economica — CRF",
            "ESTADUAL": "SEFAZ Estadual",
            "MUNICIPAL": "Prefeitura Municipal",
        }.get(tipo, "—")

        numero = f"{tipo[:3]}-{cnpj[-8:]}-{hoje.strftime('%Y%m%d')}"

        linhas = [
            "AVISO: PDF MOCK - NAO E CERTIDAO REAL",
            "",
            f"Tipo: {tipo}",
            f"Numero: {numero}",
            f"CNPJ: {cnpj}",
            f"Emitida em: {hoje.isoformat()}",
            f"Valida ate: {validade.isoformat()}",
            f"Portal: {portal}",
            "",
            "Implementar scraper real (Playwright + 2captcha)",
            "ou contratar API (Infosimples, etc.) p/ producao.",
        ]
        pdf_bytes = _gerar_pdf_minimo("MOCK CND — Nao usar em producao", linhas)

        return CndEmitida(
            pdf_bytes=pdf_bytes,
            numero=numero,
            data_emissao=hoje,
            data_validade=validade,
            tipo=tipo,
            portal=portal,
            raw={
                "fonte": "mock",
                "gerado_em": datetime.utcnow().isoformat() + "Z",
            },
        )
