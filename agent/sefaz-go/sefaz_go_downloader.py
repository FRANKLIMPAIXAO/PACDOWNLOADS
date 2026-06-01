"""SEFAZ-GO XML Downloader Agent — v0 (Claude Extension generated)

Gerado pelo Claude Extension a partir de gravação de tela do fluxo manual
no portal `nfeweb.sefaz.go.gov.br`. Versão inicial — base pra evoluir.

Status atual:
- ✅ Setup Selenium + Chrome user profile (mantém certificados instalados)
- ✅ Loop por empresa (lê de empresas.xlsx)
- ✅ Cálculo automático do mês anterior
- ✅ Click no botão "Acesso Por Certificado Digital"
- ✅ Seleção de certificado por nome da empresa (com fallback pyautogui)
- ✅ Preenche datas, clica Pesquisar
- ✅ Clica "Baixar todos os arquivos" → "somente documentos" → Confirmar
- ⏳ Aguarda download (precisa implementar wait + verificação do .zip)
- ⏳ POST do ZIP no endpoint /api/v1/documentos/upload-em-massa do PAC
- ⏳ Logs estruturados (JSON) ao invés de texto
- ⏳ Lidar com Cloudflare Turnstile (vai aparecer em algum momento)
- ⏳ Migrar pra Playwright (mais robusto que Selenium pra mTLS)

Setup:
    pip install selenium webdriver-manager pandas openpyxl pyautogui pygetwindow

Planilha empresas.xlsx esperada:
    | empresa                |
    |------------------------|
    | JOVELINO E ACILDA LTDA |
    | HC GESTAO              |
    | ...                    |
"""
import pandas as pd
import time
import os
import calendar
from datetime import date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CONFIGURAÇÕES — ajuste aqui
# ============================================================
PLANILHA = "empresas.xlsx"          # Nome da planilha
PASTA_DESTINO = r"C:\XMLs"          # Pasta raiz dos downloads
URL = "https://nfeweb.sefaz.go.gov.br/nfeweb/sites/nfe/consulta-publica/principal"
# ============================================================


def calcular_mes_anterior():
    hoje = date.today()
    primeiro_dia = date(hoje.year, hoje.month, 1) - timedelta(days=1)
    mes = primeiro_dia.month
    ano = primeiro_dia.year
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    data_ini = f"01/{mes:02d}/{ano}"
    data_fim = f"{ultimo_dia:02d}/{mes:02d}/{ano}"
    return data_ini, data_fim


def criar_pasta_empresa(nome_empresa):
    pasta = os.path.join(PASTA_DESTINO, nome_empresa)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def iniciar_browser(pasta_download):
    options = Options()
    options.add_experimental_option("prefs", {
        "download.default_directory": pasta_download,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    options.add_argument("--start-maximized")
    # Mantém o perfil do Chrome com os certificados instalados
    options.add_argument(r"--user-data-dir=C:\Users\SEU_USUARIO\AppData\Local\Google\Chrome\User Data")
    options.add_argument("--profile-directory=Default")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver


def selecionar_certificado(driver, nome_empresa):
    """
    Aguarda a janela de seleção de certificado do Chrome
    e clica na linha que contém o nome da empresa
    """
    wait = WebDriverWait(driver, 15)

    # Aguarda o dialog de certificado aparecer
    time.sleep(2)

    try:
        # Tenta localizar as linhas da tabela de certificados
        linhas = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "cr-certificate-list .list-item, "
                              "#certificateList .list-item, "
                              "div[role='option'], "
                              "li.certificate-item")
        ))

        for linha in linhas:
            if nome_empresa.upper() in linha.text.upper():
                linha.click()
                time.sleep(0.5)
                # Clica em OK
                btn_ok = driver.find_element(
                    By.XPATH, "//button[contains(text(),'OK') or @id='ok']"
                )
                btn_ok.click()
                print(f"  ✅ Certificado selecionado: {nome_empresa}")
                return True

    except Exception:
        pass

    # Fallback: usa pyautogui para interagir com a janela nativa
    try:
        import pyautogui
        import pygetwindow as gw

        time.sleep(2)

        # Procura a janela de certificado na tela
        janelas = gw.getWindowsWithTitle("Selecione um certificado")
        if not janelas:
            janelas = gw.getWindowsWithTitle("Select a certificate")

        if janelas:
            janelas[0].activate()
            time.sleep(0.5)

        # Procura o nome na tela usando reconhecimento visual
        pos = pyautogui.locateOnScreen(
            nome_empresa[:10],  # Busca pelos primeiros 10 chars
            confidence=0.7
        )
        if pos:
            pyautogui.click(pos)
            time.sleep(0.3)
            pyautogui.press('enter')  # Confirma OK
            print(f"  ✅ Certificado selecionado via screen: {nome_empresa}")
            return True

    except Exception as e:
        print(f"  ⚠️  Fallback pyautogui falhou: {e}")

    # Último recurso: seleciona o primeiro certificado da lista
    print(f"  ⚠️  Não encontrou '{nome_empresa}' — selecionando primeiro da lista")
    import pyautogui
    pyautogui.press('enter')
    return False


def processar_empresa(driver, nome_empresa, data_ini, data_fim, pasta_download):
    wait = WebDriverWait(driver, 30)
    print(f"\n{'='*50}")
    print(f"Processando: {nome_empresa}")
    print(f"Período: {data_ini} a {data_fim}")
    print(f"Destino: {pasta_download}")

    try:
        # 1. Acessa a página
        driver.get(URL)
        time.sleep(2)

        # 2. Clica em "Acesso Por Certificado Digital"
        btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(text(),'Acesso Por Certificado Digital')]")
        ))
        btn.click()
        print("  → Clicou em Acesso Por Certificado Digital")

        # 3. Seleciona o certificado
        selecionar_certificado(driver, nome_empresa)
        time.sleep(3)

        # 4. Aguarda carregar o formulário
        campo_inicio = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//input[@placeholder='Data inicial']")
        ))

        # 5. Preenche data inicial
        campo_inicio.triple_click() if hasattr(campo_inicio, 'triple_click') else (
            campo_inicio.click(),
            campo_inicio.send_keys("a")  # Ctrl+A
        )
        campo_inicio.clear()
        campo_inicio.send_keys(data_ini)
        print(f"  → Data inicial: {data_ini}")

        # 6. Preenche data final
        campo_fim = driver.find_element(
            By.XPATH, "//input[@placeholder='Data final']"
        )
        campo_fim.clear()
        campo_fim.send_keys(data_fim)
        print(f"  → Data final: {data_fim}")

        # 7. Clica em Pesquisar
        btn_pesquisar = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(text(),'Pesquisar')]")
        ))
        btn_pesquisar.click()
        print("  → Pesquisando...")
        time.sleep(4)

        # 8. Verifica se encontrou resultados
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//button[contains(text(),'Baixar todos os arquivos')]")
            ))
        except Exception:
            print(f"  ⚠️  Nenhum documento encontrado para {nome_empresa}")
            return False

        # 9. Clica em "Baixar todos os arquivos"
        btn_baixar = driver.find_element(
            By.XPATH, "//button[contains(text(),'Baixar todos os arquivos')]"
        )
        btn_baixar.click()
        print("  → Clicou em Baixar todos os arquivos")
        time.sleep(2)

        # 10. Seleciona "Baixar somente documentos"
        radio = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//input[@type='radio' and "
                       "(following-sibling::*[contains(text(),'somente documentos')] or "
                       "@value='1' or @value='documentos')]")
        ))
        if not radio.is_selected():
            radio.click()
        print("  → Selecionou 'Baixar somente documentos'")
        time.sleep(1)

        # 11. Clica em Baixar (confirmar)
        btn_confirmar = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//div[contains(@class,'modal') or contains(@class,'dialog')]"
                       "//button[contains(text(),'Baixar') and not(contains(text(),'todos'))]")
        ))
        btn_confirmar.click()
        print(f"  ✅ Download solicitado com sucesso!")
        time.sleep(3)
        return True

    except Exception as e:
        print(f"  ❌ ERRO: {e}")
        return False


def gerar_log(resultados):
    log_path = os.path.join(PASTA_DESTINO, "log_execucao.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Log de execução — {date.today().strftime('%d/%m/%Y')}\n")
        f.write("="*50 + "\n\n")
        for r in resultados:
            status = "✅ OK" if r["sucesso"] else "❌ ERRO"
            f.write(f"{status} | {r['empresa']} | {r['periodo']}\n")
            if r.get("erro"):
                f.write(f"       Detalhe: {r['erro']}\n")
    print(f"\n📄 Log salvo em: {log_path}")


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================
def main():
    # Lê a planilha
    # Formato esperado: coluna "empresa" com o nome igual ao certificado
    df = pd.read_excel(PLANILHA)

    # Valida coluna obrigatória
    if "empresa" not in df.columns:
        raise ValueError("A planilha precisa ter uma coluna chamada 'empresa'")

    # Calcula o período do mês anterior automaticamente
    data_ini, data_fim = calcular_mes_anterior()
    print(f"Período: {data_ini} a {data_fim}")
    print(f"Total de empresas: {len(df)}")

    resultados = []

    for _, row in df.iterrows():
        nome_empresa = str(row["empresa"]).strip()

        # Cria pasta de destino para esta empresa
        pasta_empresa = criar_pasta_empresa(nome_empresa)

        # Inicia um browser novo para cada empresa
        # (garante que o certificado seja selecionado corretamente)
        driver = iniciar_browser(pasta_empresa)

        try:
            sucesso = processar_empresa(
                driver, nome_empresa, data_ini, data_fim, pasta_empresa
            )
            resultados.append({
                "empresa": nome_empresa,
                "periodo": f"{data_ini} a {data_fim}",
                "sucesso": sucesso
            })
        except Exception as e:
            resultados.append({
                "empresa": nome_empresa,
                "periodo": f"{data_ini} a {data_fim}",
                "sucesso": False,
                "erro": str(e)
            })
        finally:
            time.sleep(2)
            driver.quit()

    # Gera log final
    gerar_log(resultados)

    # Resumo
    total = len(resultados)
    ok = sum(1 for r in resultados if r["sucesso"])
    print(f"\n{'='*50}")
    print(f"CONCLUÍDO: {ok}/{total} empresas processadas com sucesso")


if __name__ == "__main__":
    main()
