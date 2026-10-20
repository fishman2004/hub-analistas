# Painéis de dados (fase 5)

A TV mostra as metas de venda e de positivação do mês, por pasta (A a G) e no total, **só com gráficos e porcentagens**. Valores em reais, quantidades e nomes de vendedores, clientes ou supervisores nunca saem do PC da sala: o Hub lê as planilhas, calcula e manda para a TV apenas o percentual de cada pasta. (Regra do gestor: muita gente passa pela sala.)

## A pasta dos painéis

As planilhas ficam numa pasta só delas. Sem configurar nada, é a pasta **`Painéis`** ao lado do banco do Hub (`%LOCALAPPDATA%\Hub\Painéis`). Um administrador pode trocar por outra pasta, inclusive da rede, em **Configurações → Painéis de dados**.

Há dois jeitos de colocar os arquivos lá:

1. **Salvar ou exportar direto na pasta**, com os nomes abaixo (é o jeito para atualizar com frequência).
2. **Enviar pelo app**, na página **Painéis** (só administradores). O Hub grava com o nome certo, seja qual for o nome do arquivo enviado.

A página **Painéis** mostra a pasta, se cada planilha foi lida (e quantas linhas), quando foi atualizada e o motivo de qualquer erro. Quando um arquivo muda, a TV atualiza em poucos segundos.

## Os 5 arquivos

Cada arquivo pode ser `.xlsx`, `.xlsm` ou `.csv`. O Hub usa a **primeira aba** e a **primeira linha com conteúdo** como cabeçalho. Os nomes das colunas não precisam ter acento nem maiúsculas iguais ("META POSITIVAÇÃO" = "Meta positivacao"), e colunas a mais são ignoradas (e nem são guardadas). Exemplos com dados fictícios estão em [`tools/exemplos/`](../tools/exemplos).

| Nome do arquivo (sem a extensão) | Colunas que o Hub usa |
|---|---|
| `(BASE) - Metas Polybalas - Financeiro e Positivações` | `ID VENDEDOR`, `ID FORN`, `META FINANCEIRA`, `META POSITIVAÇÃO` |
| `(BASE) - Produtos Focos (KPI's)` | `ID PRODUTO`, `PRODUTO FOCO` |
| `(BASE) - Fornecedores Polybalas` | `ID FORNECEDOR`, `FORNECEDOR`, `FORNECEDOR II`, `PASTA` |
| `(BASE) - Metas Polybalas - KPI's e Produtos Focos` | `ID` (do vendedor), `PRODUTO FOCO`, `CLASSIFICACAO`, `META`, `META II` |
| `(DADOS) - 8081 - Vendas` | `ID RCA`, `POSICAO PED`, `DATA PEDIDO`, `ID CLIENTE`, `ID PRODUTO`, `ID FORNECEDOR`, `VALOR` |

**Formatos aceitos:**
- CSV separado por `;` (o padrão do Excel em português), `,` ou tabulação; em UTF-8 ou no padrão do Windows.
- Números como o Excel brasileiro escreve (`1.234,56`) ou como ele guarda (`1234.56`). Célula vazia vale 0.
- Datas `dd/mm/aaaa` (com ou sem hora) ou data de verdade do Excel.

## Como o Hub calcula

- **Mês:** o mês da venda mais recente do arquivo 8081. Vendas de outros meses que estiverem no arquivo não contam.
- **Pedido cancelado** (`POSICAO PED` = `C`) não conta. As outras posições contam.
- **Pasta:** cada venda e cada meta vai para a pasta do seu fornecedor, pela planilha de fornecedores (`ID FORNECEDOR` → `PASTA`). Fornecedor que não está nessa planilha fica de fora, e a página Painéis avisa quantos são.
- **Financeiro:** soma de `VALOR` dividida pela soma de `META FINANCEIRA`, por pasta e no total (T).
- **Positivação:** cada cliente que comprou de um fornecedor conta **uma vez por vendedor e por fornecedor** no mês. Divisões unificadas (mesmo `FORNECEDOR II`) contam como um fornecedor só. Dividido pela soma de `META POSITIVAÇÃO`.
- **Dias úteis:** segunda a sexta (feriados não são descontados). A meta do dia é a meta do mês dividida pelos dias úteis do mês.
- **Esperado até hoje:** a parte do mês já passada em dias úteis, até o último dia com venda. Ex.: 13 de 22 dias úteis = 59%.
- **Produtos foco:** clientes que compraram algum produto do foco (`ID PRODUTO` → `PRODUTO FOCO`), um por vendedor, divididos pela soma de `META` daquele foco. `META II` aparece como uma marca na mesma barra.

### As cores (sempre junto da porcentagem escrita)

| Cor | Faixa |
|---|---|
| Verde | 100% ou mais |
| Amarelo | 80 a 99% |
| Laranja | 70 a 79% |
| Vermelho | abaixo de 70% |

- **No dia**, a faixa é o realizado sobre a meta do dia.
- **No mês e nos produtos foco**, a faixa é o **ritmo**: o realizado comparado com o esperado até hoje. Fazer 54% da meta quando o esperado era 59% dá 92% do ritmo, amarelo. Assim o meio do mês não fica todo vermelho só porque o mês não acabou.

## As telas da TV

| Tela | O que mostra | Entra na rotação quando |
|---|---|---|
| **Metas do mês** | Evolução do financeiro total dia a dia (barras = realizado acumulado; linha pontilhada = onde precisava estar para fechar em 100%) e um cartão por pasta, de financeiro e de positivações, com a marca do esperado. | metas, fornecedores e vendas lidas |
| **Metas do dia** | Barras de financeiro e positivações do último dia com venda, por pasta, com a linha dos 100%. | as mesmas, e o último dia com venda é dia útil |
| **Produtos foco** | Uma barra por produto foco, do melhor para o pior, com o esperado e a META II. Se não couber, passa as páginas com fade. | produtos foco, metas dos produtos foco e vendas lidas |

Todas mostram "atualizado às HH:MM" (pela data do arquivo) e o aviso **Dados desatualizados** quando a planilha não muda há mais horas do que o limite de Configurações (padrão 24).

**Arquivo ausente ou com erro:** só as telas que dependem dele saem da rotação; o motivo aparece na página Painéis e vai para o `hub.log`. Nada derruba a TV.

## Leitura com cache

O Hub só relê um arquivo quando a data de modificação ou o tamanho mudam. A leitura roda em segundo plano: enquanto um arquivo grande é lido, a TV continua com os dados anteriores.

## A confirmar com o Kayo

As regras acima são o ponto de partida desta fase. Se alguma estiver diferente do que o time usa, muda num lugar só (`hub/paineis.py`):

1. Positivação conta cliente por vendedor e por fornecedor (como acima), ou cliente único na pasta?
2. Quais posições de pedido contam? Hoje só o cancelado (`C`) fica de fora.
3. Dias úteis: segunda a sexta, ou sábado também tem meta?
4. Meta dos produtos foco é em clientes positivados (como acima) ou em caixas vendidas? E a `META II`?
5. A linha **PB** do painel do Excel (Financeiro - Dia) é o quê?
