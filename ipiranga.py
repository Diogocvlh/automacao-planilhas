import re
import time
from dataclasses import dataclass
from datetime import datetime

from config import (
    carregar_ambiente, variavel_obrigatoria, credencial_google, validar_google,
    desconto_por_litro, confirmar_execucao,
)

import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =========================================================
# CONFIGURAÇÕES
# =========================================================
URL_HOME = "https://www.redeipiranga.com.br/wps/myportal/redeipiranga/homeoutros/"


INTERVALO_LEITURA = "A1:U1000"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# TESTE COM UMA BASE SÓ
@dataclass
class BaseConfig:
    nome_base: str
    cnpj: str
    uf_cidade: str
    ponto_entrega: str
    titulo_bloco_planilha: str
    opcao_dropdown_base: str

BASE_TESTE = None


# =========================================================
# SELENIUM
# =========================================================
def iniciar_driver():
    options = Options()
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


def wait(driver, timeout=20):
    return WebDriverWait(driver, timeout)


def aguardar_login_manual(driver):
    driver.get(URL_HOME)
    print("Faça o login manual no portal da Ipiranga.\nDepois que entrar e estiver na home, volte no terminal e aperte ENTER.")
    input()


def abrir_popup_cliente(driver):
    w = wait(driver, 20)

    def localizar_campo_busca():
        xpaths_input = [
            "//input[contains(@placeholder,'Razão Social') or contains(@placeholder,'CNPJ')]",
            "//input[contains(@placeholder,'Razao Social') or contains(@placeholder,'CNPJ')]",
            "//input[contains(@placeholder,'Buscar') and (contains(@placeholder,'CNPJ') or contains(@placeholder,'Raz'))]",
        ]
        for xp in xpaths_input:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        return None

    tentativas = [
        (By.XPATH, "//button[contains(@title, 'Troca de Razão Social') or contains(@aria-label, 'Troca de Razão Social') or contains(., 'Troca de Razão Social')]"),
        (By.XPATH, "//*[contains(., 'Troca de Razão Social')]/ancestor::*[self::button or self::div][1]"),
        (By.XPATH, "//*[contains(., 'CNPJ:')]/ancestor::*[self::div or self::button][1]"),
        (By.XPATH, "//button[.//*[name()='svg'] and (contains(@title, 'Troca') or contains(@aria-label, 'Troca'))]"),
    ]

    for by, xp in tentativas:
        try:
            candidatos = driver.find_elements(by, xp)
            if not candidatos:
                continue

            for el in candidatos:
                try:
                    if not el.is_displayed():
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(1.5)
                    if localizar_campo_busca() is not None:
                        return
                except Exception:
                    continue
        except Exception:
            continue

    print("Não consegui abrir automaticamente o seletor de Razão Social.")
    print("No site, clique no botão/ícone 'Troca de Razão Social' e aguarde abrir o popup.")
    input("Depois de abrir o popup com o campo de busca, pressione ENTER para continuar...")

    try:
        w.until(lambda d: localizar_campo_busca() is not None)
        return
    except Exception:
        raise RuntimeError("Popup de seleção de cliente não abriu (campo de CNPJ não encontrado).")


def escolher_cnpj(driver, base: BaseConfig):
    abrir_popup_cliente(driver)

    w = wait(driver, 20)

    def localizar_campo_busca():
        xpaths_input = [
            "//input[contains(@placeholder,'Razão Social') or contains(@placeholder,'CNPJ')]",
            "//input[contains(@placeholder,'Razao Social') or contains(@placeholder,'CNPJ')]",
            "//input[contains(@placeholder,'Buscar') and (contains(@placeholder,'CNPJ') or contains(@placeholder,'Raz'))]",
        ]
        for xp in xpaths_input:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        return None

    w.until(lambda d: localizar_campo_busca() is not None)
    campo = localizar_campo_busca()

    if campo is None:
        raise RuntimeError("Campo de CNPJ/Razão Social não está visível para interação.")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
    campo.click()

    try:
        campo.clear()
        campo.send_keys(base.cnpj)
    except Exception:
        # Fallback para inputs controlados por framework que ignoram clear/send_keys.
        driver.execute_script(
            """
            const el = arguments[0];
            const value = arguments[1];
            el.value = '';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            """,
            campo,
            base.cnpj,
        )

    time.sleep(2)

    xpath_cards = [
        f"//*[contains(., '{base.cnpj}') and contains(., '{base.uf_cidade}') and contains(., '{base.ponto_entrega}')]",
        f"//*[contains(., '{base.cnpj}') and contains(., '{base.ponto_entrega}')]",
        f"//*[contains(., '{base.cnpj}') and contains(., '{base.uf_cidade}') ]",
        f"//*[contains(., '{base.cnpj}')]",
    ]

    card = None
    for xp in xpath_cards:
        try:
            card = w.until(EC.visibility_of_element_located((By.XPATH, xp)))
            if card is not None:
                break
        except Exception:
            continue

    if card is None:
        raise RuntimeError(f"Card da base não encontrado para o CNPJ {base.cnpj}.")

    botoes_trocar = card.find_elements(By.XPATH, ".//button[contains(., 'Trocar') or contains(., 'Selecionar')]")
    if not botoes_trocar:
        raise RuntimeError(f"Botão de troca não encontrado no card do CNPJ {base.cnpj}.")

    driver.execute_script("arguments[0].click();", botoes_trocar[0])
    time.sleep(4)


def acessar_menu_registrar_pedido(driver):
    print("-> Navegando pelo menu lateral até 'Registrar pedido'...")
    w = wait(driver, 15)

    try:
        # Como o portal Ipiranga mantém a sessão pelo CNPJ, forçar a URL da tela de pedidos
        # costuma ser a forma mais rápida e à prova de falhas (evita menus travados).
        url_pedidos = "https://redeipiranga.com.br/wps/myportal/redeipiranga/pedidos/combustivel/registrarpedido/"
        driver.get(url_pedidos)
        time.sleep(5)
    except Exception as e:
        raise RuntimeError(f"Falha ao acessar a tela de Registrar Pedido: {e}")

def selecionar_base_no_pedido(driver, base: BaseConfig):
    print(f"-> Selecionando a base '{base.opcao_dropdown_base}' no formulário...")
    w = wait(driver, 15)

    try:
        # Procura a caixinha de Base (dropdown) e clica nela
        dropdown_base = w.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Base')]/following::*[contains(@class, 'select') or contains(@class, 'dropdown') or self::input][1]")))
        driver.execute_script("arguments[0].click();", dropdown_base)
        time.sleep(2)

        # Clica na opção com o nome da base
        opcao = w.until(EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{base.opcao_dropdown_base}')]")))
        driver.execute_script("arguments[0].click();", opcao)

        # Aguarda 5 segundos para a tabela de preços carregar na tela
        print("-> Base selecionada. Aguardando tabela de preços carregar...")
        time.sleep(5)
    except Exception as e:
        print(f"-> Não foi possível selecionar a base no dropdown. Erro: {e}")
        # Tira print caso dê erro no dropdown
        # Capturas não são salvas automaticamente para evitar dados de sessão em arquivos.

def capturar_precos_com_desconto(driver):
    print("-> Capturando preços com o ajuste configurado localmente...")

    produtos_alvo = {
        "Diesel S10 Bb": "S10",
        "Diesel S500 Bb": "S500",
        "Gasolina Comum Bb": "GASOLINA",
    }

    resultados = {"S10": None, "S500": None, "GASOLINA": None}

    for nome_tela, chave in produtos_alvo.items():
        try:
            # Encontra a linha do produto na tabela
            el_produto = driver.find_element(By.XPATH, f"//*[contains(., '{nome_tela}')]")
            linha = el_produto.find_element(By.XPATH, "./ancestor::div[contains(@class, 'row') or @role='row' or ancestor::tr][1]")
            texto = " ".join(linha.text.split())

            # Acha todos os números com vírgula na linha (Ex: 6,7438 e 6,1681)
            precos = re.findall(r"\d+,\d+", texto)

            if len(precos) >= 2:
                # O preço RETIRA é o segundo da linha
                retira_str = precos[1]

                # Converte para matemática (ex: "6,1681" vira 6.1681)
                valor_float = float(retira_str.replace(",", "."))

                # Aplica somente o ajuste informado no ambiente local (padrão: zero).
                valor_com_desconto = valor_float - desconto_por_litro()

                # Guarda o valor arredondado para 4 casas decimais (O gspread aceita float direto)
                resultados[chave] = round(valor_com_desconto, 4)

                print(f"   [OK] {chave}: LIDO = R$ {retira_str} | COM DESCONTO = R$ {resultados[chave]}")
            else:
                print(f"   [AVISO] Não achei 2 preços na linha do {chave}.")
        except Exception:
            print(f"   [FALHA] Produto '{nome_tela}' não encontrado na tabela.")

    return resultados

# =========================================================
# GOOGLE SHEETS
# =========================================================
def conectar_planilha_mes():
    creds = Credentials.from_service_account_file(
        credencial_google(),
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    print("Abrindo a planilha configurada no ambiente local.")
    return client.open_by_key(variavel_obrigatoria("GOOGLE_SPREADSHEET_ID"))


def achar_aba_do_dia(ss):
    nome_aba = datetime.now().strftime("Preço %d-%m")
    try:
        return ss.worksheet(nome_aba)
    except Exception:
        raise RuntimeError(f"Aba do dia não encontrada: {nome_aba}")


def encontrar_bloco_e_linha_ipiranga(valores, titulo_bloco):
    linha_titulo = None

    for i, linha in enumerate(valores):
        for cel in linha:
            if str(cel).strip().upper() == titulo_bloco.upper():
                linha_titulo = i
                break
        if linha_titulo is not None:
            break

    if linha_titulo is None:
        raise RuntimeError(f"Bloco não encontrado: {titulo_bloco}")

    linha_companhia = None
    col_empresa = None

    for r in range(linha_titulo, min(linha_titulo + 8, len(valores))):
        for c, cel in enumerate(valores[r]):
            if str(cel).strip().lower() == "companhia":
                linha_companhia = r
                col_empresa = c
                break
        if linha_companhia is not None:
            break

    if linha_companhia is None:
        raise RuntimeError(f"'Companhia' não encontrada no bloco: {titulo_bloco}")

    linha_ipiranga = None
    for r in range(linha_companhia + 1, min(linha_companhia + 20, len(valores))):
        if col_empresa < len(valores[r]) and str(valores[r][col_empresa]).strip().upper() == "IPIRANGA":
            linha_ipiranga = r
            break

    if linha_ipiranga is None:
        raise RuntimeError(f"Linha IPIRANGA não encontrada no bloco: {titulo_bloco}")

    return linha_titulo, linha_companhia, col_empresa, linha_ipiranga


def encontrar_colunas_dia_novo(valores, linha_titulo):
    padrao_data = re.compile(r"^\d{2}/\d{2}/\d{4}$")

    for r in range(linha_titulo, min(linha_titulo + 8, len(valores))):
        linha = [str(x).strip() for x in valores[r]]
        grupos = []

        for j in range(len(linha) - 2):
            if (
                padrao_data.match(linha[j])
                and padrao_data.match(linha[j + 1])
                and "Dif" in linha[j + 2]
            ):
                grupos.append((j, j + 1, j + 2))

        if len(grupos) >= 3:
            return {
                "S10": grupos[0][1],
                "S500": grupos[1][1],
                "GASOLINA": grupos[2][1],
            }

    raise RuntimeError("Colunas do dia novo não encontradas no bloco.")


def escrever_precos_ipiranga(ss, base: BaseConfig, precos):
    aba = achar_aba_do_dia(ss)
    valores = aba.get(INTERVALO_LEITURA, value_render_option="FORMATTED_VALUE")

    linha_titulo, linha_companhia, col_empresa, linha_ipiranga = encontrar_bloco_e_linha_ipiranga(
        valores,
        base.titulo_bloco_planilha
    )

    colunas = encontrar_colunas_dia_novo(valores, linha_titulo)

    updates = []

    for produto, valor in precos.items():
        if valor:
            col = colunas[produto]
            a1 = gspread.utils.rowcol_to_a1(linha_ipiranga + 1, col + 1)
            print(f"Gravando {produto} = {valor} em {a1}")
            updates.append({
                "range": a1,
                "values": [[valor]]
            })

    if not updates:
        raise RuntimeError("Nenhum preço foi capturado para gravar.")

    aba.batch_update(updates, value_input_option="USER_ENTERED")
    print("✅ Preços gravados na planilha com sucesso.")


# =========================================================
# FLUXO PRINCIPAL
# =========================================================
# Encontre a função main() no seu código e deixe-a assim:
def main():
    global BASE_TESTE
    confirmar_execucao("Coleta com login manual e escrita em planilha autorizada.")
    carregar_ambiente()
    validar_google()
    desconto_por_litro()
    BASE_TESTE = BaseConfig(
        nome_base=variavel_obrigatoria("IPIRANGA_BASE_NOME"),
        cnpj=variavel_obrigatoria("IPIRANGA_BASE_CNPJ"),
        uf_cidade=variavel_obrigatoria("IPIRANGA_BASE_LOCALIDADE"),
        ponto_entrega=variavel_obrigatoria("IPIRANGA_BASE_PONTO_ENTREGA"),
        titulo_bloco_planilha=variavel_obrigatoria("IPIRANGA_BASE_TITULO_BLOCO"),
        opcao_dropdown_base=variavel_obrigatoria("IPIRANGA_BASE_OPCAO_DROPDOWN"),
    )
    driver = iniciar_driver()

    try:
        ss = conectar_planilha_mes()

        aguardar_login_manual(driver)

        print(f"\nProcessando base: {BASE_TESTE.nome_base}")
        escolher_cnpj(driver, BASE_TESTE)

        # NOVOS PASSOS AQUI:
        acessar_menu_registrar_pedido(driver)
        selecionar_base_no_pedido(driver, BASE_TESTE)

        # CAPTURA COM DESCONTO
        precos = capturar_precos_com_desconto(driver)
        print("\nPreços finais a gravar na planilha:", precos)

        escrever_precos_ipiranga(ss, BASE_TESTE, precos)

        print("✅ Teste finalizado com sucesso.")

    finally:
        input("Pressione ENTER para fechar o navegador...")
        driver.quit()

if __name__ == "__main__":
    main()
