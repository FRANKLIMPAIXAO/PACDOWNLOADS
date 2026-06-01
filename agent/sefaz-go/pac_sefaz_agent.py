"""PAC SEFAZ-GO Agent (Playwright async).

Versão produção-ready: Linux headless + mTLS via clientCertificates +
integração total com a API PAC.

Fluxo por empresa (em loop):
1. Pega .pfx + senha da empresa via API PAC
2. Abre context Playwright com clientCertificates configurado
3. Navega no portal nfeweb.sefaz.go.gov.br
4. Browser apresenta cert automaticamente (mTLS — sem popup)
5. Aguarda Cloudflare Turnstile (~5-10s)
6. Preenche filtros (datas)
7. Clica Pesquisar → enfileira
8. Vai pro Histórico Downloads, faz poll até "Concluído"
9. Baixa ZIP
10. POSTa no PAC /api/v1/documentos/upload-em-massa
11. Loga resultado estruturado

Uso:
    python pac_sefaz_agent.py                          # mês anterior, todas empresas
    python pac_sefaz_agent.py --empresa 5              # só empresa id=5
    python pac_sefaz_agent.py --periodo 2026-04        # mês específico
    python pac_sefaz_agent.py --headed                 # browser visível (debug)
    python pac_sefaz_agent.py --dry-run                # não envia pro PAC, só baixa

Logs: ./logs/agente_YYYY-MM-DD.jsonl (JSON Lines, 1 evento por linha).
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import datetime as dt
import json
import logging
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import re

from dotenv import load_dotenv
from playwright.async_api import (
    BrowserContext,
    Download,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    async_playwright,
)
from playwright_stealth import Stealth
from twocaptcha import TwoCaptcha

from pac_client import CertificadoBaixado, EmpresaPAC, PacClient


# ============================================================
# Config
# ============================================================

load_dotenv()

PAC_API_URL = os.getenv("PAC_API_URL", "http://127.0.0.1:8000")
PAC_EMAIL = os.getenv("PAC_EMAIL", "admin@pacxml.com.br")
PAC_PASSWORD = os.getenv("PAC_PASSWORD", "admin123")
# Entry point oficial do portal SEFAZ-GO Documentos Fiscais.
# Daqui o user clica no link "Arquivo XML dos Documentos Fiscais" que redireciona
# pra nfeweb.sefaz.go.gov.br com o referer correto (importante p/ Turnstile).
SEFAZ_GO_ENTRY = os.getenv(
    "SEFAZ_GO_ENTRY",
    "https://goias.gov.br/economia/documentos-fiscais/",
)
SEFAZ_GO_URL = os.getenv(
    "SEFAZ_GO_URL",
    "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/principal",
)
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
STEP_TIMEOUT_MS = int(os.getenv("STEP_TIMEOUT", "60")) * 1000
DOWNLOAD_TIMEOUT_S = int(os.getenv("DOWNLOAD_TIMEOUT", "600"))
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "200"))
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "./downloads")).resolve()
CERT_DIR = Path(os.getenv("CERT_DIR", "./certs-temp")).resolve()
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs")).resolve()

# Em dev local Windows, Chromium do Playwright pode falhar por falta de
# VC++ Redistributable. Pra contornar: usa o Chrome do sistema se instalado.
# Em produção VPS Linux, deixe vazio pra usar o Chromium do Playwright.
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "")  # "chrome" | "msedge" | ""
BROWSER_EXECUTABLE_PATH = os.getenv("BROWSER_EXECUTABLE_PATH", "")

# 2Captcha pra resolver Turnstile (Cloudflare bloqueia auto-resolve em browsers
# automatizados, então a gente paga pra terceirizar)
TWOCAPTCHA_API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")


# ============================================================
# Logging estruturado JSONL
# ============================================================


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def log_evento(evento: str, **kwargs: Any) -> None:
    """Append JSONL com o evento estruturado."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"agente_{dt.date.today().isoformat()}.jsonl"
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
class ResultadoEmpresa:
    empresa_id: int
    cnpj: str
    razao_social: str
    sucesso: bool
    motivo: str | None = None
    zip_path: str | None = None
    upload_pac: dict[str, Any] | None = None
    duracao_segundos: float = 0.0
    sem_resultados: bool = False  # portal respondeu "Sem resultados" pro período


@dataclass(slots=True)
class DownloadFila:
    """Resultado do polling do histórico de downloads.

    `zip_path`: caminho do ZIP baixado (caso de sucesso com notas).
    `sem_resultados`: True quando portal marcou "Concluído" + observação "Sem resultados"
        — período não tem notas, NÃO é erro nem timeout.
    `motivo_erro`: string descrevendo erro/timeout quando zip_path é None e sem_resultados False.
    """
    zip_path: Path | None = None
    sem_resultados: bool = False
    motivo_erro: str = ""


@dataclass(slots=True)
class JanelaPeriodo:
    data_inicio: dt.date
    data_fim: dt.date

    @property
    def formatado_br_inicio(self) -> str:
        return self.data_inicio.strftime("%d/%m/%Y")

    @property
    def formatado_br_fim(self) -> str:
        return self.data_fim.strftime("%d/%m/%Y")


def janela_mes_anterior() -> JanelaPeriodo:
    hoje = dt.date.today()
    primeiro_anterior = dt.date(hoje.year, hoje.month, 1) - dt.timedelta(days=1)
    inicio = dt.date(primeiro_anterior.year, primeiro_anterior.month, 1)
    ultimo = calendar.monthrange(primeiro_anterior.year, primeiro_anterior.month)[1]
    fim = dt.date(primeiro_anterior.year, primeiro_anterior.month, ultimo)
    return JanelaPeriodo(inicio, fim)


def janela_mes_especifico(ano_mes: str) -> JanelaPeriodo:
    """ano_mes formato 'YYYY-MM'."""
    ano, mes = ano_mes.split("-")
    ano_i, mes_i = int(ano), int(mes)
    ultimo = calendar.monthrange(ano_i, mes_i)[1]
    return JanelaPeriodo(dt.date(ano_i, mes_i, 1), dt.date(ano_i, mes_i, ultimo))


# ============================================================
# Browser Playwright
# ============================================================


def reembrulhar_pfx_moderno(pfx_bytes: bytes, senha: str) -> bytes:
    """Re-empacota um PFX da ICP-Brasil em formato moderno (AES-256+SHA256).

    PFX legado (RC2-40 + 3DES + SHA1) é bloqueado pelo OpenSSL 3.x que
    Node.js/Playwright usam. Esta função decifra o PFX antigo via Python
    cryptography (que tem provider legacy) e re-empacota com algoritmos
    modernos compatíveis com OpenSSL 3 sem flags especiais.
    """
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption, pkcs12,
    )

    senha_bytes = senha.encode("utf-8")
    private_key, certificate, additional = pkcs12.load_key_and_certificates(
        pfx_bytes, senha_bytes,
    )
    if not private_key or not certificate:
        raise RuntimeError("PFX sem chave/certificado ao re-empacotar")

    # Mantém a MESMA senha mas re-empacota com AES-256 + SHA256 (compatível OpenSSL 3)
    return pkcs12.serialize_key_and_certificates(
        name=b"agent-cert",
        key=private_key,
        cert=certificate,
        cas=additional or None,
        encryption_algorithm=BestAvailableEncryption(senha_bytes),
    )


async def criar_context(
    pw: Playwright,
    cert: CertificadoBaixado,
    download_dir: Path,
    *,
    headless: bool,
) -> BrowserContext:
    """Cria um BrowserContext com clientCertificate carregado do PFX da empresa.

    O Playwright vai apresentar o cert AUTOMATICAMENTE no handshake TLS
    quando o servidor pedir (mTLS). Sem popup nativo do Chrome.
    """
    # Args específicos por SO. Windows não precisa --no-sandbox.
    args = ["--disable-blink-features=AutomationControlled"]
    if sys.platform != "win32":
        args += ["--no-sandbox", "--disable-dev-shm-usage"]

    launch_kwargs: dict = {
        "headless": headless,
        "slow_mo": SLOW_MO_MS if not headless else 0,
        "args": args,
    }
    # Permite usar Chrome/Edge do sistema (ex: Windows sem VC++ Redist)
    if BROWSER_CHANNEL:
        launch_kwargs["channel"] = BROWSER_CHANNEL
    if BROWSER_EXECUTABLE_PATH:
        launch_kwargs["executable_path"] = BROWSER_EXECUTABLE_PATH

    # Log diag pré-launch — quando falha em prod, esses prints ajudam a achar
    # o erro real (path do chromium, PLAYWRIGHT_BROWSERS_PATH, args).
    import os as _os
    print(f"[diag] PLAYWRIGHT_BROWSERS_PATH={_os.environ.get('PLAYWRIGHT_BROWSERS_PATH','<default>')}", flush=True)
    print(f"[diag] launch_kwargs={launch_kwargs}", flush=True)
    try:
        # Lista o que tem no path do chromium pra confirmar instalação
        bp = _os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
        if bp and _os.path.isdir(bp):
            print(f"[diag] {bp} contains: {_os.listdir(bp)[:20]}", flush=True)
        # Lista também o default cache (~/.cache/ms-playwright) caso esteja lá
        from pathlib import Path as _P
        default_cache = _P.home() / ".cache" / "ms-playwright"
        if default_cache.is_dir():
            print(f"[diag] {default_cache} contains: {list(default_cache.iterdir())[:10]}", flush=True)
    except Exception as _e:
        print(f"[diag] listdir erro: {_e}", flush=True)

    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context(
        accept_downloads=True,
        viewport={"width": 1366, "height": 768},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        client_certificates=[
            {
                "origin": "https://nfeweb.sefaz.go.gov.br",
                # Re-empacota PFX da ICP-Brasil em formato moderno (AES-256/SHA256)
                # pra evitar erro "Unsupported TLS certificate" do OpenSSL 3.
                "pfx": reembrulhar_pfx_moderno(cert.pfx_path.read_bytes(), cert.senha),
                "passphrase": cert.senha,
            }
        ],
    )
    context.set_default_timeout(STEP_TIMEOUT_MS)

    # Aplica stealth: remove fingerprints de automação que Cloudflare detecta
    # (navigator.webdriver, plugins fake, UA realista, etc).
    stealth = Stealth(
        navigator_webdriver=True,  # remove navigator.webdriver=true
        chrome_app=True,
        chrome_csi=True,
        chrome_load_times=True,
        chrome_runtime=True,
        iframe_content_window=True,
        navigator_languages=True,
        navigator_permissions=True,
        navigator_plugins=True,
        navigator_vendor=True,
        webgl_vendor=True,
        media_codecs=True,
    )
    await stealth.apply_stealth_async(context)
    return context


def resolver_turnstile_2captcha(sitekey: str, url: str) -> str:
    """Pede pro 2Captcha resolver Turnstile e retorna o token.

    Roda síncrono (a biblioteca 2captcha não é async). Cloudflare bloqueia
    auto-resolve em browsers automatizados, então terceirizamos.
    """
    log = logging.getLogger("2captcha")
    if not TWOCAPTCHA_API_KEY:
        raise RuntimeError("TWOCAPTCHA_API_KEY vazio. Configure no .env.")
    solver = TwoCaptcha(TWOCAPTCHA_API_KEY, defaultTimeout=300, pollingInterval=5)
    log.info("Solicitando 2Captcha resolver Turnstile (sitekey=%s)...", sitekey)
    inicio = dt.datetime.now()
    result = solver.turnstile(sitekey=sitekey, url=url)
    token = result["code"]
    elapsed = (dt.datetime.now() - inicio).total_seconds()
    log.info("✓ Turnstile resolvido em %.1fs (token: %d chars)", elapsed, len(token))
    return token


async def resolver_e_injetar_turnstile(page: Page) -> bool:
    """Pipeline completo de resolver Turnstile via 2Captcha + injetar no DOM.

    Estratégia (vinda do script Claude Extension):
    1. Extrai sitekey do HTML (`.cf-turnstile data-sitekey`)
    2. Chama 2Captcha → token
    3. Injeta token no input #cf-turnstile-response
    4. Dispara callback do widget (`data-callback="pegarTokenSuccess"`)
    5. Sucesso quando input tem value populado
    """
    log = logging.getLogger("turnstile")

    # Extrai sitekey + callback do HTML
    info = await page.evaluate("""
        () => {
            const widget = document.querySelector('.cf-turnstile, [data-sitekey]');
            if (!widget) return null;
            return {
                sitekey: widget.getAttribute('data-sitekey'),
                callback: widget.getAttribute('data-callback'),
                url: window.location.href,
            };
        }
    """)
    if not info or not info.get("sitekey"):
        log.error("Não achei widget .cf-turnstile na página")
        return False

    sitekey = info["sitekey"]
    callback_name = info.get("callback") or ""
    log.info("Widget Turnstile: sitekey=%s callback=%s", sitekey, callback_name)

    # Roda 2Captcha em thread (síncrono) sem bloquear o event loop.
    # IMPORTANTE: Playwright async_api às vezes desconecta o driver durante
    # esperas longas (>30s) sem atividade. Pra mitigar, periodicamente fazemos
    # uma "ping" no page (evaluate trivial) enquanto 2Captcha tá processando.
    loop = asyncio.get_running_loop()
    captcha_task = loop.run_in_executor(
        None, resolver_turnstile_2captcha, sitekey, info["url"],
    )
    # Keep-alive: page.evaluate a cada 10s pra não deixar driver dormir
    token: str | None = None
    while not captcha_task.done():
        try:
            await page.evaluate("() => 1")  # ping
        except Exception as ping_exc:
            log.warning("Ping falhou (driver pode ter caído): %s", ping_exc)
            break
        try:
            token = await asyncio.wait_for(asyncio.shield(captcha_task), timeout=10)
        except asyncio.TimeoutError:
            continue
        except Exception as exc:  # noqa: BLE001
            log.error("Falha no 2Captcha: %s", exc)
            return False
    if token is None:
        # captcha terminou; busca o resultado
        try:
            token = await captcha_task
        except Exception as exc:  # noqa: BLE001
            log.error("Falha no 2Captcha: %s", exc)
            return False

    # Re-confirma que a página ainda está viva
    try:
        url_atual = page.url
        log.info("Página ainda viva em: %s", url_atual)
    except Exception as exc:
        log.error("Page morreu durante 2Captcha: %s", exc)
        return False

    # Injeta o token no DOM: input #cf-turnstile-response + callback JS
    try:
        sucesso = await page.evaluate("""
            (token) => {
                const els = document.querySelectorAll(
                    '#cf-turnstile-response, input[id="cf-turnstile-response"], ' +
                    'input[name="g-recaptcha-response"], textarea[name="g-recaptcha-response"]'
                );
                for (const el of els) { el.value = token; }
                return els.length > 0 && [...els].some(el => el.value && el.value.length > 50);
            }
        """, token)
    except Exception as exc:
        log.error("Page.evaluate(injetar) falhou: %s", exc)
        return False

    if not sucesso:
        log.error("Não consegui injetar o token no DOM")
        return False

    # Dispara o callback do widget (best effort)
    if callback_name:
        try:
            await page.evaluate(
                """
                ({cb, token}) => {
                    if (cb && window[cb]) {
                        try { window[cb](token); } catch (e) { console.error(e); }
                    }
                }
                """,
                {"cb": callback_name, "token": token},
            )
        except Exception:
            pass  # callback é best-effort

    log.info("✓ Token Turnstile injetado no DOM com sucesso")
    return True


# ============================================================
# Fluxo SEFAZ-GO
# ============================================================


async def preencher_datepickers(
    page: Page,
    *,
    id_inicio: str,
    id_fim: str,
    data_ini: dt.date,
    data_fim: dt.date,
) -> bool:
    """Preenche dois inputs controlados por jQuery UI Datepicker.

    Por que isso é não-trivial:
    O jQuery UI Datepicker (`<input class="hasDatepicker">`) NÃO usa o valor
    do `<input>` no submit — usa o estado interno mantido pelo plugin via
    `$.datepicker._curInst`. Setar `el.value = "01/04/2026"` ou usar Playwright
    `.fill()` apenas atualiza o DOM, mas o widget mantém a data anterior.
    Resultado: o portal SEFAZ-GO submete o período DEFAULT (21/04-21/05) em vez do
    pedido (01/04-30/04). Visível pelo nome do ZIP gerado.

    Estratégia (3 camadas com fallback):
    1. `$('#id').datepicker('setDate', new Date(y, m-1, d))` — API oficial do widget,
       atualiza estado interno + value + dispara `onSelect`.
    2. Se jQuery não está carregado: `.click()` + `.fill()` + `.press('Tab')`
       (fechamento do popup via Tab dispara blur → portal lê o value).
    3. Sempre dispara eventos `change` + `blur` no final (best-effort defensive).

    Validação: chama em sequência e devolve True se ambos os valores ficaram
    como esperado.
    """
    log = logging.getLogger("datepicker")
    expected_ini = data_ini.strftime("%d/%m/%Y")
    expected_fim = data_fim.strftime("%d/%m/%Y")

    # Tentativa 1: jQuery UI setDate (caminho ideal)
    tem_jquery = await page.evaluate(
        "() => typeof window.jQuery === 'function' && typeof window.jQuery.fn.datepicker === 'function'"
    )
    log.info("jQuery UI Datepicker disponivel? %s", tem_jquery)

    if tem_jquery:
        try:
            resultado = await page.evaluate(
                """
                ({idIni, idFim, ano1, mes1, dia1, ano2, mes2, dia2}) => {
                    const $ = window.jQuery;
                    const $ini = $('#' + idIni);
                    const $fim = $('#' + idFim);
                    if (!$ini.length || !$fim.length) {
                        return {ok: false, motivo: 'inputs nao encontrados'};
                    }
                    // mes em JS é 0-based
                    $ini.datepicker('setDate', new Date(ano1, mes1 - 1, dia1));
                    $fim.datepicker('setDate', new Date(ano2, mes2 - 1, dia2));
                    // dispara change/blur por garantia
                    $ini.trigger('change').trigger('blur');
                    $fim.trigger('change').trigger('blur');
                    return {ok: true, ini: $ini.val(), fim: $fim.val()};
                }
                """,
                {
                    "idIni": id_inicio, "idFim": id_fim,
                    "ano1": data_ini.year, "mes1": data_ini.month, "dia1": data_ini.day,
                    "ano2": data_fim.year, "mes2": data_fim.month, "dia2": data_fim.day,
                },
            )
            if resultado.get("ok") and resultado.get("ini") == expected_ini and resultado.get("fim") == expected_fim:
                log.info("✓ Datas setadas via jQuery UI datepicker.setDate: %s — %s", resultado["ini"], resultado["fim"])
                return True
            log.warning("setDate retornou %s (esperado %s/%s) — tentando fallback", resultado, expected_ini, expected_fim)
        except Exception as exc:  # noqa: BLE001
            log.warning("setDate falhou: %s — tentando fallback", exc)

    # Tentativa 2: click + fill + Tab (fecha datepicker, dispara blur)
    for sel, valor in ((f"#{id_inicio}", expected_ini), (f"#{id_fim}", expected_fim)):
        try:
            inp = page.locator(sel).first
            await inp.click()
            await inp.fill(valor)
            await page.keyboard.press("Tab")
        except Exception as exc:
            log.warning("click+fill em %s falhou: %s", sel, exc)

    # Tentativa 3 (defensive): dispatch change/blur via DOM puro
    try:
        await page.evaluate(
            """
            ({idIni, idFim, valIni, valFim}) => {
                const fire = (el, ev) => el.dispatchEvent(new Event(ev, {bubbles: true}));
                const a = document.getElementById(idIni);
                const b = document.getElementById(idFim);
                if (a) { a.value = valIni; fire(a, 'change'); fire(a, 'blur'); }
                if (b) { b.value = valFim; fire(b, 'change'); fire(b, 'blur'); }
            }
            """,
            {"idIni": id_inicio, "idFim": id_fim, "valIni": expected_ini, "valFim": expected_fim},
        )
    except Exception as exc:
        log.warning("dispatch eventos falhou: %s", exc)

    # Validação final
    final = await page.evaluate(
        """
        ({idIni, idFim}) => ({
            ini: document.getElementById(idIni)?.value || '',
            fim: document.getElementById(idFim)?.value || '',
        })
        """,
        {"idIni": id_inicio, "idFim": id_fim},
    )
    ok = final.get("ini") == expected_ini and final.get("fim") == expected_fim
    if ok:
        log.info("✓ Datas confirmadas via fallback: %s — %s", final["ini"], final["fim"])
    else:
        log.error("✗ DOM final %s (esperado %s — %s)", final, expected_ini, expected_fim)
    return ok


async def processar_empresa(
    pw: Playwright,
    empresa: EmpresaPAC,
    cert: CertificadoBaixado,
    janela: JanelaPeriodo,
    download_dir: Path,
    *,
    headless: bool,
) -> ResultadoEmpresa:
    log = logging.getLogger(f"empresa[{empresa.cnpj}]")
    inicio = dt.datetime.now()
    res = ResultadoEmpresa(
        empresa_id=empresa.id, cnpj=empresa.cnpj, razao_social=empresa.razao_social,
        sucesso=False,
    )

    context = await criar_context(pw, cert, download_dir, headless=headless)
    page: Page = await context.new_page()

    try:
        # Passo 0: começa pelo entry point oficial do gov.br (referer correto)
        log.info("Abrindo entry point: %s", SEFAZ_GO_ENTRY)
        await page.goto(SEFAZ_GO_ENTRY, wait_until="domcontentloaded")
        log_evento("entry_aberto", cnpj=empresa.cnpj, url=SEFAZ_GO_ENTRY)

        # Click no link "Arquivo XML dos Documentos Fiscais"
        # (texto exato pode variar — tenta variações)
        link = page.get_by_role(
            "link", name=re.compile("Arquivo XML.*Documentos Fiscais", re.I),
        )
        if await link.count() == 0:
            # fallback: link contendo "arquivo xml"
            link = page.locator("a:has-text('Arquivo XML')").first

        log.info("Clicando no link 'Arquivo XML dos Documentos Fiscais'...")
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            await link.click()
        log.info("Redirecionou pra: %s", page.url)
        log_evento("portal_aberto", cnpj=empresa.cnpj, url=page.url)

        # Aguarda DOM estabilizar antes de procurar botão "Certificado Digital".
        # Em batches, Cloudflare às vezes injeta interstitial antes da página
        # final renderizar — networkidle dá tempo do JS do portal terminar.
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            log.debug("networkidle timeout — seguindo mesmo assim")

        # Passo 1: Click "Acesso Por Certificado Digital" — 3 estratégias
        # com 30s cada, total ~90s no pior caso (vs 15s+15s antes).
        # Em CLAVEAUX caiu nesse passo em batch — portal lenta demais.
        estrategias_cert = [
            ("role-button", lambda: page.get_by_role(
                "button", name=re.compile("certificado", re.I),
            )),
            ("role-link", lambda: page.get_by_role(
                "link", name=re.compile("certificado", re.I),
            )),
            ("text-css", lambda: page.locator(
                "text=/acesso por certificado digital/i",
            ).first),
            ("contains-cert", lambda: page.locator(
                ":text('Certificado Digital')",
            ).first),
        ]
        clicou_cert = False
        ultimo_erro: Exception | None = None
        for nome, fab in estrategias_cert:
            try:
                el = fab()
                # Espera visível antes de clicar — evita race com Cloudflare
                await el.first.wait_for(state="visible", timeout=30_000)
                await el.first.click(timeout=10_000)
                log.info("Clicou cert via estratégia '%s'", nome)
                clicou_cert = True
                break
            except Exception as exc:
                ultimo_erro = exc
                log.warning("Estratégia '%s' falhou: %s", nome, str(exc)[:200])
                continue

        if not clicou_cert:
            # Debug dump — salva screenshot + HTML + lista botões/links visíveis
            DEBUG_DIR = LOG_DIR / "debug"
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot = DEBUG_DIR / f"sem_cert_btn_{empresa.cnpj}_{ts}.png"
            html_dump = DEBUG_DIR / f"sem_cert_btn_{empresa.cnpj}_{ts}.html"
            try:
                await page.screenshot(path=str(screenshot), full_page=True)
                html_dump.write_text(await page.content(), encoding="utf-8")
                # Lista TODOS os textos clicáveis visíveis pra diagnosticar
                visiveis = await page.evaluate("""
                    () => {
                        const els = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                        return els.filter(e => e.offsetParent !== null)
                            .map(e => ({tag: e.tagName, texto: (e.innerText || e.textContent || '').trim().slice(0,80), href: e.href || null}))
                            .filter(e => e.texto);
                    }
                """)
                log.error(
                    "Botão cert NÃO ENCONTRADO. URL=%s. Visíveis: %s. "
                    "Screenshot=%s",
                    page.url, visiveis[:20], screenshot,
                )
            except Exception as exc:
                log.warning("Falha ao salvar debug: %s", exc)
            res.motivo = (
                f"Botão 'Acesso Por Certificado Digital' não encontrado em 4 estratégias. "
                f"Pode ser Cloudflare interstitial / portal lento. URL atual: {page.url}. "
                f"Ver {screenshot}"
            )
            log_evento(
                "cert_btn_nao_encontrado", cnpj=empresa.cnpj,
                url=page.url, screenshot=str(screenshot),
            )
            return res

        log.info("Clicou 'Acesso Por Certificado Digital' — mTLS deve disparar")
        log_evento("login_cert_iniciado", cnpj=empresa.cnpj)

        # Passo 2: mTLS — Playwright apresenta cert AUTOMATICAMENTE pelo
        # context.client_certificates. SEM popup nativo Chrome.

        # Passo 3: Aguarda form carregar (URL muda pra .../consulta-publica)
        await page.wait_for_selector(
            "input[type='text'], select",
            timeout=30_000,
        )
        log.info("Form carregado (URL: %s)", page.url)
        log_evento("form_carregado", cnpj=empresa.cnpj, url=page.url)

        # Captura HTML logo após form carregar (pra debug)
        DEBUG_DIR = LOG_DIR / "debug"
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts_form = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        html_form = DEBUG_DIR / f"form_carregado_{empresa.cnpj}_{ts_form}.html"
        try:
            html_form.write_text(await page.content(), encoding="utf-8")
            log.info("HTML do form salvo: %s", html_form)
        except Exception:
            pass

        # Passo 4: Resolve Cloudflare Turnstile via 2Captcha + injeta no DOM
        # (Cloudflare bloqueia auto-resolve em browsers automatizados)
        if not await resolver_e_injetar_turnstile(page):
            res.motivo = "Falha ao resolver Turnstile via 2Captcha"
            log.error(res.motivo)
            return res

        # Passo 4.5: Seleciona CNPJ no dropdown #cmpCnpj
        # CRITICAL: certificado A1 com múltiplas filiais carrega todos os
        # CNPJs no dropdown (matriz + filiais). Sem seleção explícita, o
        # portal usa a PRIMEIRA opção (que pode ser uma filial sem movimento)
        # em vez do CNPJ que o usuário cadastrou no PAC.
        # Bug visto na AGIMED: cert lista 4 CNPJs (0196 matriz + 0277/0358/0439
        # filiais). Default = filial 0277 sem NFes → "Sem Resultados", mesmo
        # a matriz 0196 tendo notas.
        try:
            cnpj_select = page.locator("#cmpCnpj")
            if await cnpj_select.count() > 0:
                # Lê opções disponíveis pra log + escolhe match exato pelo value
                opcoes_cnpj = await page.evaluate(
                    """
                    () => {
                        const sel = document.querySelector('#cmpCnpj');
                        if (!sel) return [];
                        return Array.from(sel.options).map(o => o.value);
                    }
                    """
                )
                log.info("Dropdown CNPJ tem %d opções: %s", len(opcoes_cnpj), opcoes_cnpj)
                if empresa.cnpj in opcoes_cnpj:
                    await cnpj_select.select_option(empresa.cnpj)
                    log.info("✓ CNPJ %s selecionado no dropdown", empresa.cnpj)
                    log_evento(
                        "cnpj_selecionado", cnpj=empresa.cnpj,
                        opcoes=opcoes_cnpj, escolhido=empresa.cnpj,
                    )
                elif opcoes_cnpj:
                    log.warning(
                        "CNPJ %s NÃO está nas opções do dropdown %s — "
                        "cert pode não autorizar essa empresa. Mantendo default.",
                        empresa.cnpj, opcoes_cnpj,
                    )
                    log_evento(
                        "cnpj_nao_encontrado_no_dropdown", cnpj=empresa.cnpj,
                        opcoes=opcoes_cnpj,
                    )
            else:
                log.debug("Sem dropdown #cmpCnpj — cert tem 1 CNPJ só, OK")
        except Exception as exc:
            log.warning("Erro ao selecionar CNPJ no dropdown: %s", exc)

        # Passo 5: Preenche datas — JÁ via jQuery UI Datepicker
        # IDs vêm do HTML do portal: cmpDataInicial / cmpDataFinal.
        # FIX (bug #10): fill() puro NÃO funciona com jQuery UI Datepicker
        # (a classe `hasDatepicker` indica que o JS controla o valor via .datepicker('setDate')).
        # Sem essa API, o submit pega o estado interno do widget, não o value do input,
        # e o portal usa o período DEFAULT (21/04-21/05) em vez do solicitado.
        ok = await preencher_datepickers(
            page,
            id_inicio="cmpDataInicial",
            id_fim="cmpDataFinal",
            data_ini=janela.data_inicio,
            data_fim=janela.data_fim,
        )
        if not ok:
            raise RuntimeError("Falha ao setar datas no datepicker do portal")
        # Valida o que o portal realmente tem nos inputs (debug imediato)
        vals = await page.evaluate(
            """
            () => ({
                inicio: document.querySelector('#cmpDataInicial')?.value || '',
                fim:    document.querySelector('#cmpDataFinal')?.value || '',
            })
            """
        )
        log.info("Período no DOM após setDate: inicio=%r fim=%r", vals.get("inicio"), vals.get("fim"))
        esperado_ini = janela.formatado_br_inicio
        esperado_fim = janela.formatado_br_fim
        if vals.get("inicio") != esperado_ini or vals.get("fim") != esperado_fim:
            log.warning(
                "DOM não bate com período esperado (esperado %s-%s, lido %s-%s)",
                esperado_ini, esperado_fim, vals.get("inicio"), vals.get("fim"),
            )
        log_evento("periodo_preenchido", cnpj=empresa.cnpj, dom=vals,
                   esperado=[esperado_ini, esperado_fim])

        # Passo 6: Confirma que token Turnstile está no input (foi injetado no passo 4)
        # Se Turnstile expirou enquanto preenchia datas (~120s validade), refaz.
        token_atual = await page.evaluate("""
            () => document.querySelector('#cf-turnstile-response')?.value || ''
        """)
        if not token_atual or len(token_atual) < 50:
            log.warning("Token Turnstile sumiu/expirou — resolvendo de novo...")
            if not await resolver_e_injetar_turnstile(page):
                res.motivo = "Falha ao re-resolver Turnstile antes de Pesquisar"
                log.error(res.motivo)
                return res

        # Passo 7: Clica Pesquisar
        pesquisar = page.get_by_role("button", name=re.compile("pesquisar", re.I))
        await pesquisar.click()
        log.info("Pesquisa enviada — aguardando resultados")
        log_evento("pesquisa_enviada", cnpj=empresa.cnpj)

        # 7.5. Aguarda DOM estabilizar e checa banner "Sem Resultados!"
        # O portal SEFAZ-GO retorna esse banner vermelho quando a empresa não
        # tem NFes no período. O botão "Baixar todos os arquivos" CONTINUA
        # visível no rodapé mesmo sem dados — se clicarmos, o modal abre vazio
        # e nunca renderiza o botão de confirmação (timeout). Detectar aqui é
        # mais barato do que esperar 60s no modal.
        await asyncio.sleep(2)  # dá tempo do DOM atualizar pós-pesquisa
        try:
            sem_resultados = await page.evaluate(
                """
                () => {
                    // Procura por texto "Sem Resultados" no body inteiro
                    const bodyText = document.body.innerText || '';
                    const semResultadosMatches = bodyText.match(/sem\\s+resultados/gi);
                    // Conta ocorrências: 2+ = banner topo + texto tabela
                    return (semResultadosMatches || []).length >= 1;
                }
                """
            )
        except Exception as exc:
            log.warning("Falha ao checar 'Sem Resultados': %s", exc)
            sem_resultados = False

        if sem_resultados:
            log.info("Portal retornou 'Sem Resultados' — empresa sem NFes no período")
            log_evento(
                "sem_resultados_pesquisa", cnpj=empresa.cnpj,
                periodo=[janela.formatado_br_inicio, janela.formatado_br_fim],
            )
            res.sucesso = True
            res.sem_resultados = True
            res.motivo = "Período sem documentos no portal SEFAZ-GO"
            return res

        # 8. Procura botão "Baixar todos os arquivos"
        # Tenta vários textos possíveis pra ser tolerante a mudanças no portal
        candidatos = [
            "button:has-text('Baixar todos os arquivos')",
            "button:has-text('Baixar Todos os Arquivos')",
            "button:has-text('Baixar todos')",
            "a:has-text('Baixar todos')",
            "button:has-text('Download')",
        ]
        achou = False
        for seletor in candidatos:
            try:
                await page.wait_for_selector(seletor, timeout=5_000)
                achou = True
                # Salva o seletor que funcionou pra usar no próximo step
                btn_baixar_seletor = seletor
                break
            except PWTimeout:
                continue

        if not achou:
            # Salva screenshot + HTML pra debug
            DEBUG_DIR = LOG_DIR / "debug"
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot = DEBUG_DIR / f"sem_docs_{empresa.cnpj}_{ts}.png"
            html_dump = DEBUG_DIR / f"sem_docs_{empresa.cnpj}_{ts}.html"
            try:
                await page.screenshot(path=str(screenshot), full_page=True)
                html_dump.write_text(await page.content(), encoding="utf-8")
                log.warning("Debug salvo: %s e %s", screenshot, html_dump)
            except Exception:
                pass
            res.motivo = (
                "Botão 'Baixar todos os arquivos' não apareceu. "
                f"Pode ser: (a) sem NFes no período, (b) selector mudou. Veja {screenshot}"
            )
            log.warning(res.motivo)
            log_evento("sem_documentos", cnpj=empresa.cnpj, screenshot=str(screenshot))
            return res

        await page.click(btn_baixar_seletor)
        log.info("Clicou no botão de baixar (selector: %s)", btn_baixar_seletor)

        # 9. Modal — seleciona "Documentos" (NFes) + confirma
        # CRITICAL: o portal SEFAZ-GO tem 3 opções no modal de download:
        #   1) Documentos + Eventos (NFes + cancelamentos + CCe)
        #   2) Somente Documentos (só procNFe — NFes autorizadas)  ← QUEREMOS ISSO
        #   3) Somente Eventos (procEventoNFe — cancelamentos + CCe)
        # Bug anterior: marcava o segundo radio "às cegas" (radios.nth(1)) que
        # pegava "Somente Eventos" e baixava só eventos de cancelamento/CCe,
        # NÃO as NFes! (https://github.com/.../issues/sefaz-go-eventos)
        try:
            await page.wait_for_selector(
                "input[type='radio']", state="visible", timeout=10_000,
            )

            # Lê TODOS os radios + texto de cada label associado pra escolher
            # certo (e logar pra futura debug se o portal mudar).
            opcoes = await page.evaluate(
                """
                () => {
                    const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                    return radios.map((r, idx) => {
                        // Procura label associado: <label for="id"> ou <label><input/></label> ou texto vizinho
                        let texto = '';
                        if (r.id) {
                            const lbl = document.querySelector(`label[for="${r.id}"]`);
                            if (lbl) texto = lbl.textContent.trim();
                        }
                        if (!texto && r.parentElement) {
                            texto = r.parentElement.textContent.trim();
                        }
                        return {idx, value: r.value || '', name: r.name || '', texto};
                    });
                }
                """
            )
            log.info("Opções do modal de download (%d radios):", len(opcoes))
            for op in opcoes:
                log.info("  [%d] value=%r texto=%r", op["idx"], op["value"], op["texto"][:100])

            # Estratégia 1: procurar o radio cujo label fala "Documento"
            # (mas NÃO "Evento") — é o que baixa só as NFes
            idx_escolhido = None
            for op in opcoes:
                t = op["texto"].lower()
                if "documento" in t and "evento" not in t:
                    idx_escolhido = op["idx"]
                    log.info("✓ Radio 'somente documentos' detectado no idx=%d", idx_escolhido)
                    break

            # Estratégia 2 (fallback): se não achou, marca o que tem AMBOS
            # ("Documentos e Eventos") — melhor sobrar do que faltar
            if idx_escolhido is None:
                for op in opcoes:
                    t = op["texto"].lower()
                    if "documento" in t and "evento" in t:
                        idx_escolhido = op["idx"]
                        log.warning("Radio 'só documentos' não achado, usando 'documentos + eventos' (idx=%d)", idx_escolhido)
                        break

            # Estratégia 3 (último recurso): primeiro radio
            if idx_escolhido is None:
                idx_escolhido = 0
                log.warning("Nenhum label legível, marcando primeiro radio (idx=0)")

            radios = page.locator("input[type='radio']")
            await radios.nth(idx_escolhido).check()
            log_evento(
                "modal_radio_escolhido", cnpj=empresa.cnpj,
                opcoes=opcoes, escolhido=idx_escolhido,
            )
        except Exception as exc:
            log.warning("Erro ao selecionar radio modal: %s", exc)

        # 10. Confirma "Baixar" do modal — tolera variações de texto do portal
        candidatos_confirmar = [
            "button:has-text('Baixar'):not(:has-text('todos'))",
            "button:has-text('Confirmar')",
            "button:has-text('OK')",
            "button[type='submit']:has-text('Baixar')",
            ".modal button:has-text('Baixar')",
        ]
        clicou_confirmar = False
        for sel in candidatos_confirmar:
            try:
                # 15s por candidato — total ~75s no pior caso (vs 60s do default)
                await page.locator(sel).first.wait_for(state="visible", timeout=15_000)
                await page.locator(sel).first.click()
                log.info("Confirmou modal com seletor: %s", sel)
                clicou_confirmar = True
                break
            except PWTimeout:
                continue
            except Exception as exc:
                log.warning("Seletor %r falhou: %s", sel, exc)
                continue

        if not clicou_confirmar:
            # Salva screenshot + HTML pra debug — modal apareceu mas botão sumiu
            DEBUG_DIR = LOG_DIR / "debug"
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot = DEBUG_DIR / f"modal_sem_confirmar_{empresa.cnpj}_{ts}.png"
            html_dump = DEBUG_DIR / f"modal_sem_confirmar_{empresa.cnpj}_{ts}.html"
            try:
                await page.screenshot(path=str(screenshot), full_page=True)
                html_dump.write_text(await page.content(), encoding="utf-8")
                log.warning("Debug salvo: %s e %s", screenshot, html_dump)
            except Exception:
                pass
            res.motivo = (
                "Modal de download abriu mas botão 'Baixar' (confirmar) não apareceu. "
                f"Texto pode ter mudado no portal. Veja {screenshot}"
            )
            log.error(res.motivo)
            log_evento("modal_confirmar_falhou", cnpj=empresa.cnpj, screenshot=str(screenshot))
            return res

        log.info("Solicitação enviada à fila SEFAZ-GO. Aguardando Histórico...")
        log_evento("solicitacao_enfileirada", cnpj=empresa.cnpj)

        # 11. Após confirmar modal, portal NEM SEMPRE navega sozinho.
        # Em CNPJs grandes (matriz com filiais), modal fecha e usuário fica
        # parado na /resultado com as NFes listadas — precisa clicar manualmente
        # no botão "Histórico de Downloads de XMLs" no rodapé pra ir pra fila.
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except PWTimeout:
            pass
        log.info("Tela após confirmar modal: %s", page.url)

        # Detecta se já está no histórico (URL contém /historico) ou se precisa navegar
        if "/historico" not in page.url:
            log.info("Não navegou sozinho — clicando 'Histórico de Downloads de XMLs'")
            candidatos_hist = [
                "a:has-text('Histórico de Downloads de XMLs')",
                "button:has-text('Histórico de Downloads de XMLs')",
                "a:has-text('Histórico de Downloads')",
                "button:has-text('Histórico de Downloads')",
                "a:has-text('Histórico')",
            ]
            clicou_hist = False
            for sel in candidatos_hist:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.click()
                        log.info("Navegou para histórico via: %s", sel)
                        clicou_hist = True
                        break
                except Exception as exc:
                    log.warning("Falha ao clicar %r: %s", sel, exc)
                    continue
            if not clicou_hist:
                # Fallback: navega direto pela URL conhecida (pode mudar entre versões)
                hist_url = "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/historico"
                log.warning("Nenhum botão 'Histórico' encontrado — tentando URL direta: %s", hist_url)
                try:
                    await page.goto(hist_url, wait_until="domcontentloaded", timeout=30_000)
                except Exception as exc:
                    log.error("Falha ao navegar para histórico via URL: %s", exc)

            # Aguarda página de histórico carregar
            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30_000)
            except PWTimeout:
                pass

        log.info("Tela atual após navegação histórico: %s", page.url)
        log_evento("na_pagina_historico", cnpj=empresa.cnpj, url=page.url)

        # 12. Poll até status "Concluído" + click no link de download
        # FIX (bug #11): filtra o histórico pelo período REQUISITADO + CNPJ + timestamp mais recente,
        # senão o agente baixa o primeiro "Concluído" da tabela (que pode ser ZIP antigo de outro período).
        fila = await aguardar_e_baixar_zip(
            page, download_dir, max_segundos=DOWNLOAD_TIMEOUT_S,
            cnpj=empresa.cnpj,
            data_ini=janela.data_inicio,
            data_fim=janela.data_fim,
        )

        # Caso A: portal respondeu "Sem resultados" — sucesso vazio, nada pra enviar pro PAC
        if fila.sem_resultados:
            res.sucesso = True
            res.sem_resultados = True
            res.motivo = "Período sem documentos no portal SEFAZ-GO"
            log.info("→ Empresa sem notas no período. Pulando upload PAC.")
            log_evento("sem_resultados", cnpj=empresa.cnpj,
                       periodo=[janela.formatado_br_inicio, janela.formatado_br_fim])
            return res

        # Caso B: erro/timeout sem ZIP
        if fila.zip_path is None:
            res.motivo = fila.motivo_erro or "Timeout aguardando ZIP ficar pronto na fila"
            log.error(res.motivo)
            log_evento("timeout_fila", cnpj=empresa.cnpj)
            return res

        # Caso C: ZIP baixado com sucesso
        zip_path = fila.zip_path
        res.zip_path = str(zip_path)
        res.sucesso = True
        log.info("✓ ZIP baixado: %s (%d KB)", zip_path.name, zip_path.stat().st_size / 1024)
        log_evento(
            "zip_baixado",
            cnpj=empresa.cnpj,
            zip_path=str(zip_path),
            zip_size=zip_path.stat().st_size,
        )

    except Exception as exc:
        res.motivo = f"Erro inesperado: {exc!r}"
        log.exception("Falha no processamento")
        log_evento("erro_inesperado", cnpj=empresa.cnpj, erro=str(exc))
    finally:
        res.duracao_segundos = (dt.datetime.now() - inicio).total_seconds()
        try:
            await context.close()
        except Exception:
            pass

    return res


async def aguardar_e_baixar_zip(
    page: Page,
    download_dir: Path,
    max_segundos: int,
    *,
    cnpj: str,
    data_ini: dt.date,
    data_fim: dt.date,
) -> DownloadFila:
    """Poll na tela /resultado/download/historico até status 'Concluído' DA LINHA QUE PEDIMOS.

    Por que filtrar a linha:
    A tabela mostra TODAS as solicitações anteriores daquele CNPJ. Pegar `tr:has-text('Concluído')`
    `.first` baixa um ZIP velho (potencialmente de outro período) sem perceber.
    Estrutura da linha (vide debug/historico_inicial_*.html):
        <tr id="{cnpj}_{ddmmyyyy_ini}_{ddmmyyyy_fim}_{seq}.zip">
            <td class="col-situacao">Concluído | Aguardando...</td>
            <td class="col-arquivo">{filename}</td>
            <td class="col-data">DD/MM/YYYY HH:MM:SS</td>
            <td class="col-observacoes"></td>
            <td class="col-acoes"><a class="btn btn-info" href="...arquivo/{filename}">Baixar XML</a></td>
        </tr>

    Estratégia:
    1. Calcula prefixo esperado = `{cnpj}_{ddmmyyyy_ini}_{ddmmyyyy_fim}_`
    2. Filtra `<tr>` cujo `id` começa com esse prefixo.
    3. Se há múltiplas (já existiam ZIPs antigos com o mesmo período), escolhe a de
       timestamp `col-data` MAIS RECENTE — essa é a que acabamos de enfileirar.
    4. Aguarda essa linha específica virar "Concluído"; só então clica no `<a>` dela.
    """
    log = logging.getLogger("download")
    deadline = dt.datetime.now() + dt.timedelta(seconds=max_segundos)
    DEBUG_DIR = LOG_DIR / "debug"
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    iteracoes = 0

    prefixo_esperado = (
        f"{cnpj}_{data_ini.strftime('%d%m%Y')}_{data_fim.strftime('%d%m%Y')}_"
    )
    log.info("Buscando linha no histórico com prefixo: %s", prefixo_esperado)

    # JS helper: devolve dados da linha (newest match) — id, situacao, link, ts, observacoes
    js_find_linha = """
    (prefixo) => {
        const trs = Array.from(document.querySelectorAll('tr.tbody-row, tr[id]'));
        const parseTs = (txt) => {
            if (!txt) return 0;
            // formato: DD/MM/YYYY HH:MM:SS
            const m = txt.trim().match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})\\s+(\\d{2}):(\\d{2}):(\\d{2})$/);
            if (!m) return 0;
            return new Date(+m[3], +m[2]-1, +m[1], +m[4], +m[5], +m[6]).getTime();
        };
        const matches = trs
            .filter(tr => tr.id && tr.id.startsWith(prefixo))
            .map(tr => {
                const situacao = (tr.querySelector('td.col-situacao')?.textContent || '').trim();
                const link = tr.querySelector('td.col-acoes a[href]')?.getAttribute('href') || '';
                const ts = parseTs(tr.querySelector('td.col-data')?.textContent);
                const observacoes = (tr.querySelector('td.col-observacoes')?.textContent || '').trim();
                return {id: tr.id, situacao, link, ts, observacoes};
            })
            .sort((a, b) => b.ts - a.ts);
        return matches[0] || null;
    }
    """

    while dt.datetime.now() < deadline:
        iteracoes += 1
        try:
            # Snapshot do HTML inicial
            if iteracoes == 1:
                snap = DEBUG_DIR / f"historico_inicial_{dt.datetime.now().strftime('%H%M%S')}.html"
                snap.write_text(await page.content(), encoding="utf-8")
                log.info("Snapshot inicial do histórico: %s", snap)

            # Procura linha cujo ID começa com nosso prefixo (CNPJ + período)
            linha_info = await page.evaluate(js_find_linha, prefixo_esperado)

            if linha_info is None:
                if iteracoes % 3 == 1:
                    log.info(
                        "Linha com prefixo %s ainda não apareceu (it %d)",
                        prefixo_esperado, iteracoes,
                    )
            else:
                situacao = linha_info.get("situacao", "")
                observacoes = linha_info.get("observacoes", "")
                log.info(
                    "Linha alvo: id=%s situacao=%r observacoes=%r (it %d)",
                    linha_info.get("id"), situacao, observacoes, iteracoes,
                )
                if situacao.lower().startswith("conclu"):
                    link_href = linha_info.get("link") or ""

                    # Caso 1: portal disse "Sem resultados" — período não tem notas, NÃO é erro.
                    obs_lower = observacoes.lower()
                    if (
                        "sem resultado" in obs_lower
                        or "nenhum" in obs_lower
                        or "sem documento" in obs_lower
                    ):
                        log.info(
                            "✓ Linha alvo Concluída SEM RESULTADOS (observacoes=%r) — "
                            "período não tem notas pra esse CNPJ",
                            observacoes,
                        )
                        return DownloadFila(
                            zip_path=None,
                            sem_resultados=True,
                            motivo_erro="",
                        )

                    # Caso 2: Concluído COM link de download
                    if link_href:
                        log.info("✓ Linha alvo Concluída com href — disparando download")
                        # Click via locator no <a> daquela linha específica (não confia em índice)
                        seletor_a = f"tr[id='{linha_info['id']}'] td.col-acoes a"
                        try:
                            async with page.expect_download(timeout=60_000) as dl_info:
                                await page.locator(seletor_a).first.click()
                            download: Download = await dl_info.value
                            nome = download.suggested_filename or linha_info["id"]
                            destino = download_dir / nome
                            download_dir.mkdir(parents=True, exist_ok=True)
                            await download.save_as(str(destino))
                            return DownloadFila(zip_path=destino)
                        except Exception as exc:
                            log.warning(
                                "Click no link da linha alvo falhou: %s — tentando href direto", exc,
                            )
                            # Fallback: navega direto pro href absoluto (sai pra GET, captura download)
                            from urllib.parse import urljoin
                            abs_url = urljoin(page.url, link_href)
                            try:
                                async with page.expect_download(timeout=60_000) as dl_info:
                                    await page.evaluate("(u) => { window.location.href = u; }", abs_url)
                                download = await dl_info.value
                                nome = download.suggested_filename or linha_info["id"]
                                destino = download_dir / nome
                                download_dir.mkdir(parents=True, exist_ok=True)
                                await download.save_as(str(destino))
                                return DownloadFila(zip_path=destino)
                            except Exception as exc2:
                                log.error("Fallback href falhou também: %s", exc2)
                    else:
                        log.warning(
                            "Linha alvo Concluída mas sem href E sem 'Sem resultados' — "
                            "talvez ainda renderizando, segue polling",
                        )
                # senão: ainda Aguardando, segue polling

        except Exception as exc:
            log.debug("Iteração falhou: %s", exc)

        # Recarrega pra refrescar o status (servidor processa de forma assíncrona)
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass

        await asyncio.sleep(10)

    # Timeout — salva HTML final pra debug
    try:
        snap_final = DEBUG_DIR / f"historico_timeout_{dt.datetime.now().strftime('%H%M%S')}.html"
        snap_final.write_text(await page.content(), encoding="utf-8")
        log.error(
            "Timeout aguardando ZIP %s. HTML final: %s",
            prefixo_esperado, snap_final,
        )
    except Exception:
        pass
    return DownloadFila(motivo_erro=f"Timeout polling histórico (prefixo {prefixo_esperado})")


# ============================================================
# Orquestração
# ============================================================


async def main_async(args: argparse.Namespace) -> int:
    setup_logging()
    log = logging.getLogger("agente")

    headless = HEADLESS and not args.headed
    log.info("Modo: %s | Periodo: %s", "headless" if headless else "headed", args.periodo or "mes anterior")

    janela = (
        janela_mes_especifico(args.periodo) if args.periodo
        else janela_mes_anterior()
    )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    with PacClient(PAC_API_URL, PAC_EMAIL, PAC_PASSWORD) as pac:
        empresas = pac.listar_empresas(somente_com_cert=True)
        if args.empresa:
            empresas = [e for e in empresas if e.id == args.empresa]
        if not empresas:
            log.error("Nenhuma empresa elegível (ativa + com cert A1).")
            return 1

        log.info("Vai processar %d empresa(s)", len(empresas))

        resultados: list[ResultadoEmpresa] = []
        async with async_playwright() as pw:
            for emp in empresas:
                log.info(
                    "==== Empresa %d: %s (%s) ====",
                    emp.id, emp.razao_social, emp.cnpj,
                )
                try:
                    cert = pac.baixar_certificado(emp.id, CERT_DIR)
                except Exception as exc:
                    log.error("Falha ao baixar cert da empresa %d: %s", emp.id, exc)
                    resultados.append(ResultadoEmpresa(
                        empresa_id=emp.id, cnpj=emp.cnpj,
                        razao_social=emp.razao_social, sucesso=False,
                        motivo=f"cert_indisponivel: {exc}",
                    ))
                    continue

                try:
                    res = await processar_empresa(
                        pw, emp, cert, janela, DOWNLOAD_DIR, headless=headless,
                    )
                    # Upload pro PAC se baixou
                    if res.sucesso and res.zip_path and not args.dry_run:
                        try:
                            res.upload_pac = pac.upload_em_massa(
                                Path(res.zip_path), empresa_id_fallback=emp.id,
                            )
                            log.info(
                                "Upload PAC: %d persistidos, %d duplicados, %d erros",
                                res.upload_pac["persistidos"],
                                res.upload_pac["duplicados"],
                                res.upload_pac["erros"],
                            )
                            log_evento(
                                "upload_pac_ok", cnpj=emp.cnpj,
                                resultado=res.upload_pac,
                            )
                        except Exception as exc:
                            log.error("Falha upload PAC: %s", exc)
                            log_evento("upload_pac_erro", cnpj=emp.cnpj, erro=str(exc))
                    resultados.append(res)
                finally:
                    # Limpa cert temporário
                    try:
                        cert.pfx_path.unlink()
                    except Exception:
                        pass

        # Resumo
        ok = sum(1 for r in resultados if r.sucesso and not r.sem_resultados)
        vazios = sum(1 for r in resultados if r.sem_resultados)
        erros = sum(1 for r in resultados if not r.sucesso)
        log.info(
            "==== Concluído: %d com ZIP | %d sem notas | %d erros (total %d) ====",
            ok, vazios, erros, len(resultados),
        )
        for r in resultados:
            if r.sem_resultados:
                status = "○"  # sucesso vazio
            elif r.sucesso:
                status = "✓"
            else:
                status = "✗"
            log.info(
                "  %s %s (%s) — %s",
                status, r.razao_social, r.cnpj,
                r.motivo or f"upload={r.upload_pac.get('persistidos', '?') if r.upload_pac else 'skip'}",
            )

        # Salva resumo JSON
        resumo_path = LOG_DIR / f"resumo_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        resumo_path.write_text(
            json.dumps([asdict(r) for r in resultados], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Resumo salvo: %s", resumo_path)

    # Exit 0 = tudo ok (com ZIP ou sem notas, sem erros).
    # Exit 2 = pelo menos uma empresa falhou.
    return 0 if erros == 0 else 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PAC SEFAZ-GO Agent")
    p.add_argument("--empresa", type=int, help="Processa só essa empresa (id PAC)")
    p.add_argument("--periodo", type=str, help="YYYY-MM (default: mês anterior)")
    p.add_argument("--headed", action="store_true", help="Mostra browser (debug)")
    p.add_argument("--dry-run", action="store_true", help="Não envia ZIP pro PAC")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
