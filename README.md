# Automação de planilhas de preços

[![Verificações offline](https://github.com/Diogocvlh/automacao-planilhas/actions/workflows/checks.yml/badge.svg?branch=main)](https://github.com/Diogocvlh/automacao-planilhas/actions/workflows/checks.yml)

Projeto Python que organiza abas diárias no Google Sheets e reúne coletores Selenium para portais de fornecedores. O código demonstra integração de serviços, identificação de blocos de planilha e transformação de dados tabulares.

**Estado: protótipo de integração.** Não há demonstração conectada, credenciais incluídas ou garantia de compatibilidade com o layout atual dos portais. Os exemplos de configuração são fictícios. Este repositório não representa vínculo ou endosso das empresas citadas pelos conectores.

## O que existe

| Arquivo | Responsabilidade |
| --- | --- |
| `rodar_tudo.py` | Duplica uma aba anterior, atualiza datas e valores de blocos FOB e inicia o coletor Vibra. |
| `vibra.py` | Coleta preços por base e grava nas células configuradas. |
| `ipiranga.py` | Usa login manual, seleciona uma base e escreve os preços capturados. |
| `config.py` | Valida variáveis de ambiente, arquivos locais e mapeamento de células. |
| `config/bases-vibra.example.json` | Exemplo fictício de mapeamento; as credenciais são referenciadas pelo nome de variáveis. |
| `tests/` | Testes offline da configuração. |

## Pré-requisitos

- Python 3.10 ou superior e ambiente virtual.
- Google Chrome, acesso autorizado aos portais e uma planilha exclusiva para testes.
- Conta de serviço Google com as APIs Sheets e Drive habilitadas e acesso limitado à planilha utilizada.
- Permissão para instalar o driver do Chrome utilizado pelo Selenium.

Os seletores e os formatos de planilha precisam ser revisados para cada instalação. Não execute contra planilhas operacionais antes de validar uma cópia.

## Preparar o ambiente no PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config/bases-vibra.example.json config/bases-vibra.json
```

Preencha apenas o `.env` local. As variáveis já definidas no processo têm precedência sobre esse arquivo.

| Variável | Uso |
| --- | --- |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho do JSON real da conta de serviço, preferencialmente em `secrets/`. |
| `GOOGLE_SPREADSHEET_ID` | Identificador de uma planilha de testes sob seu controle. |
| `VIBRA_BASES_FILE` | Caminho do arquivo local com aliases, variáveis de acesso e células. |
| `VIBRA_BASE_DEMO_USER` / `VIBRA_BASE_DEMO_PASSWORD` | Usuário e senha da base fictícia do exemplo; substitua localmente por acessos autorizados. |
| `IPIRANGA_BASE_*` | Dados da base escolhida para o fluxo com login manual. |
| `IPIRANGA_DESCONTO_POR_LITRO` | Ajuste decimal não negativo aplicado à coleta; o padrão é `0`. |

O arquivo `dados-google-example.json` é apenas ilustrativo e não autentica. Gere e armazene sua credencial real fora dos arquivos versionados. Para novas bases, adicione um alias ao JSON local e crie variáveis próprias de usuário e senha, mantendo `usuario_env` e `senha_env` como nomes dessas variáveis.

## Executar conscientemente

Todos os scripts exigem `--executar`. Sem esse argumento, encerram antes das chamadas aos serviços. **Não existe modo de simulação de escrita**: quando executados com configuração válida, os scripts alteram a planilha.

```powershell
# Prepara uma aba diária e, em seguida, inicia a coleta Vibra.
.\.venv\Scripts\python.exe rodar_tudo.py --executar

# Alternativa: executar somente o coletor Vibra.
.\.venv\Scripts\python.exe vibra.py --executar

# Coleta com login manual; aguarda instruções no terminal.
.\.venv\Scripts\python.exe ipiranga.py --executar
```

Não rode o segundo comando automaticamente após o primeiro: ele repetiria a coleta. O preparador também remove validações de dados na nova aba; revise esse comportamento e o intervalo configurado antes do uso.

O preparador mantém a regra existente: se a aba de hoje já estiver presente, seleciona o próximo dia útil; nos fins de semana, também avança até um dia útil. O nome da aba preparada é repassado ao Vibra com `--aba`, para que a coleta escreva nesse mesmo destino. Dias úteis aqui significam segunda a sexta, sem calendário de feriados. Executado isoladamente, o Vibra usa a data atual; também aceita um destino explícito, como `vibra.py --executar --aba "Preço 28-10"`.

Falhas ao abrir ou preparar a planilha interrompem o encadeamento. Falhas de gravação ou ausência de preços para as células configuradas fazem o coletor falhar, sem anunciar conclusão bem-sucedida. Não há rollback: gravações anteriores à falha podem já ter ocorrido.

## Verificações offline

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q config.py rodar_tudo.py vibra.py ipiranga.py tests
```

Os testes usam dados e arquivos temporários fictícios. Os testes de encadeamento substituem as bibliotecas externas e verificam destino da aba, propagação de erros e encerramento do navegador por meio de mocks. Não fazem login, não abrem navegadores e não acessam Google Sheets. Essas verificações não comprovam que uma credencial funciona ou que o coletor acompanha o layout atual de um portal.

## Segurança e limites conhecidos

- Segredos são fornecidos localmente; `.env`, credenciais, configurações privadas, perfis de navegador e capturas estão no `.gitignore`.
- A integração escreve preços e altera abas. Células fixas e seletores podem deixar de corresponder ao destino após mudanças de layout.
- Ainda faltam modo de simulação, testes de integração isolados, política de repetição de falhas e garantia de transação entre as alterações.
- As dependências estão declaradas em `requirements.txt`, mas ainda não há um lockfile reproduzível nem validação do ambiente completo neste saneamento.
- Dados de clientes, bases, IDs de planilhas e regras comerciais foram retirados dos exemplos versionados.
- Este repositório público começa com uma versão saneada e histórico novo, contendo somente código e exemplos sem credenciais reais. Arquivos de ambiente e configurações locais permanecem fora do Git. Credenciais expostas anteriormente em outras cópias precisam ser revogadas ou trocadas nos serviços correspondentes.

## Próximos passos

- Introduzir interfaces para leitura e escrita, permitindo testes dos coletores sem serviços reais.
- Extrair as transformações de planilha para funções puras com exemplos fictícios.
- Adicionar modo de simulação que exporte as alterações propostas antes de gravar.
- Criar ambiente de integração com uma planilha de testes e tratamento de falhas por etapa.

## Licença

Ainda não há licença de código aberto definida. Avalie o direito de compartilhar o código e escolha uma licença antes de distribuir o projeto publicamente.
