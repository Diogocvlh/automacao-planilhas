import time
import re
from config import (
    carregar_ambiente, variavel_obrigatoria, credencial_google, validar_google,
    carregar_bases_vibra, confirmar_execucao,
)

import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURAÇÕES ---
# A planilha e as credenciais são configuradas apenas no ambiente local.


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BASES_VIBRA = {}

def aceitar_todos_cookies_vibra(driver):
    """Limpa informativos, banners de cookies e modais da Vibra."""
    # Termos comuns em botões de fechar/aceitar
    termos = ["Aceitar", "Entendi", "OK", "Fechar", "Prosseguir", "Concordo"]

    # 1. Tenta fechar o botão específico de informativo da Vibra
    try:
        elementos_f = driver.find_elements(By.CSS_SELECTOR, ".btn-fecha-informativo, .close, [data-dismiss='modal']")
        for el in elementos_f:
            if el.is_displayed():
                driver.execute_script("arguments[0].click();", el)
    except: pass

    # 2. Busca por textos comuns em botões
    for texto in termos:
        try:
            botoes = driver.find_elements(By.XPATH, f"//button[contains(text(), '{texto}')] | //a[contains(text(), '{texto}')]")
            for btn in botoes:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
        except: continue

def obter_aba_planilha(nome_aba):
    creds = Credentials.from_service_account_file(credencial_google(), scopes=SCOPES)
    client = gspread.authorize(creds)
    print('Credencial Google carregada localmente.')
    print('Abrindo a planilha configurada no ambiente local.')

    try:
        planilha = client.open_by_key(variavel_obrigatoria("GOOGLE_SPREADSHEET_ID"))
    except gspread.exceptions.SpreadsheetNotFound as e:
        raise RuntimeError(
            "Planilha não encontrada ou sem acesso para esta conta de serviço. "
            f"Confira o acesso da conta de serviço configurada."
        ) from e

    try:
        return planilha.worksheet(nome_aba)
    except gspread.exceptions.WorksheetNotFound:
        # Se não achar a de hoje, tenta duplicar a última aba existente
        abas = planilha.worksheets()
        return planilha.duplicate_sheet(abas[-1].id, new_sheet_name=nome_aba)

def extrair_apenas_numeros(texto):
    if not texto: return ""
    return re.sub(r'[^0-9,]', '', texto.replace('.', ','))

def salvar_no_google_direto(celula, valor, nome_aba):
    if not celula or not valor: return
    try:
        aba = obter_aba_planilha(nome_aba)
        aba.update_acell(celula, extrair_apenas_numeros(valor))
        print(f"📊 Salvo na {celula}: {valor}")
    except Exception as e:
        raise RuntimeError(f"Falha ao salvar uma célula ({type(e).__name__}).") from e

def rodar_coleta(base_id, nome_aba):
    conf = BASES_VIBRA[base_id]
    print(f"\n--- 🛰️  INICIANDO: {base_id} ---")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.maximize_window()
    wait = WebDriverWait(driver, 25)

    try:
        driver.get("https://cn.vibraenergia.com.br/login")

        # 1. LOGIN
        aceitar_todos_cookies_vibra(driver)
        wait.until(EC.element_to_be_clickable((By.ID, "usuario"))).send_keys(conf['usuario'])
        driver.find_element(By.ID, "senha").send_keys(conf['senha'])
        driver.find_element(By.ID, "btn-acessar").click()

        # 2. PÓS-LOGIN (Limpeza de avisos)
        time.sleep(6)
        aceitar_todos_cookies_vibra(driver)

        # 3. NAVEGAÇÃO PARA PREÇOS
        print("🖱️ Clicando em CRIAR...")
        btn_criar = wait.until(EC.presence_of_element_located((By.LINK_TEXT, "CRIAR")))
        driver.execute_script("arguments[0].click();", btn_criar)

        time.sleep(8)
        aceitar_todos_cookies_vibra(driver) # Pode aparecer aviso na central de pedidos

        print("🛒 Abrindo Carrinho de Preços...")
        carrinho_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "i.icone-carrinho, .icone-carrinho")))
        driver.execute_script("arguments[0].click();", carrinho_btn)

        # 4. CAPTURA DE VALORES
        print(f"⏳ Aguardando lista de preços de {base_id}...")
        time.sleep(10)
        aceitar_todos_cookies_vibra(driver) # Limpa se algo abrir sobre a lista

        driver.execute_script("window.scrollBy(0, 400);")

        itens = driver.find_elements(By.CLASS_NAME, "accordion-item")
        if not itens:
            itens = driver.find_elements(By.CSS_SELECTOR, "div.item-produto")

        count_s10 = 0
        count_s500 = 0
        count_gasolina = 0
        gravacoes = 0

        for item in itens:
            try:
                celula = None
                # Localiza o valor dentro do item
                valor_el = item.find_element(By.XPATH, ".//span[@class='valor-unidade']/strong[contains(text(), ',')]")
                texto_item = item.text.upper()
                valor_texto = valor_el.text

                if "S10" in texto_item:
                    count_s10 += 1
                    celula = conf.get(f"celula_s10_{count_s10}", conf.get("celula_s10") if count_s10 == 1 else None)

                elif "S500" in texto_item:
                    count_s500 += 1
                    celula = conf.get(f"celula_s500_{count_s500}", conf.get("celula_s500") if count_s500 == 1 else None)

                elif "GASOLINA" in texto_item:
                    count_gasolina += 1
                    celula = conf.get(f"celula_gasolina_{count_gasolina}", conf.get("celula_gasolina") if count_gasolina == 1 else None)
            except Exception:
                continue

            # Falhas de gravação interrompem a base; não são falhas de parsing.
            if celula:
                salvar_no_google_direto(celula, valor_texto, nome_aba)
                gravacoes += 1

        if gravacoes == 0:
            raise RuntimeError("Nenhum preço foi gravado nas células configuradas.")

    except Exception as e:
        raise RuntimeError(f"Falha ao processar base ({type(e).__name__}).") from e
    finally:
        driver.quit()

if __name__ == "__main__":
    argumentos = confirmar_execucao(
        "Coleta de preços com escrita em planilha autorizada.", permitir_aba=True,
    )
    carregar_ambiente()
    validar_google()
    BASES_VIBRA = carregar_bases_vibra()
    nome_aba = argumentos.aba or datetime.now().strftime("Preço %d-%m")
    for b in BASES_VIBRA.keys():
        rodar_coleta(b, nome_aba)
    print(f"\n🚀 PROCESSO VIBRA FINALIZADO!")
