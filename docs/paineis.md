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
| `(DADOS) - 8081 - Vendas` | `DATA PEDIDO`, `ID CLIENTE`, `ID PRODUTO`, `ID FORNECEDOR`, `VALOR` |

**Formatos aceitos:**
- CSV separado por `;` (o padrão do Excel em português), `,` ou tabulação; em UTF-8 ou no padrão do Windows.
- Números como o Excel brasileiro escreve (`1.234,56`) ou como ele guarda (`1234.56`). Célula vazia vale 0.
- Datas `dd/mm/aaaa` (com ou sem hora) ou data de verdade do Excel.

## Como o Hub calcula

- **Mês:** o mês da venda mais recente do arquivo 8081. Vendas de outros meses que estiverem no arquivo não contam.
- **Todas as posições de pedido contam** (L liberado, B bloqueado, M montado, F faturado). O pedido cancelado já não vem na extração do sistema.
- **Pasta:** cada venda e cada meta vai para a pasta do seu fornecedor, pela planilha de fornecedores (`ID FORNECEDOR` → `PASTA`). Fornecedor que não está nessa planilha fica de fora, e a página Painéis avisa quantos são.
- **Financeiro:** soma de `VALOR` dividida pela soma de `META FINANCEIRA`, por pasta e no total (T).
- **Positivação** é o atendimento único do mês, a mesma contagem distinta de `ID CLIENTE` do Excel: o cliente conta **uma vez no mês para cada fornecedor**, na primeira compra, não importa quantos pedidos nem quantos vendedores. Divisões unificadas (mesmo `FORNECEDOR II`) contam como um fornecedor só. A pasta e o total somam os fornecedores, do mesmo jeito que a meta (que vem por fornecedor), e são divididos pela soma de `META POSITIVAÇÃO`.
- **Positivação do dia:** clientes positivados pela primeira vez no mês naquele dia.
- **Dias de venda:** segunda a sábado (sábado é dia de venda até meio-dia); domingo não tem meta e feriados não são descontados. A meta do dia é a meta do mês dividida pelos dias de venda do mês.
- **Esperado até hoje:** a parte do mês já passada em dias de venda, até o último dia com venda. Ex.: 15 de 26 dias = 58%.
- **Total (T):** é a Polybalas inteira (o "PB" do painel do Excel).
- **Produtos foco:** `META` é a meta de positivação (clientes distintos que compraram algum produto do foco, `ID PRODUTO` → `PRODUTO FOCO`) e `META II` é a meta financeira (soma de `VALOR` dos produtos do foco). Foco sem `META II` mostra só a positivação.

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
| **Metas do dia** | Barras de financeiro e positivações do último dia com venda, por pasta, com a linha dos 100%. | as mesmas, e o último dia com venda não é domingo |
| **Produtos foco** | Para cada produto foco, uma barra de positivação (META) e uma de financeiro (META II), do melhor para o pior, com o esperado. Se não couber, passa as páginas com fade. | produtos foco, metas dos produtos foco e vendas lidas |

Todas mostram "atualizado às HH:MM" (pela data do arquivo) e o aviso **Dados desatualizados** quando a planilha não muda há mais horas do que o limite de Configurações (padrão 24).

**Arquivo ausente ou com erro:** só as telas que dependem dele saem da rotação; o motivo aparece na página Painéis e vai para o `hub.log`. Nada derruba a TV.

## Leitura com cache

O Hub só relê um arquivo quando a data de modificação ou o tamanho mudam. A leitura roda em segundo plano: enquanto um arquivo grande é lido, a TV continua com os dados anteriores.

## Respostas do Kayo (20/10/2026)

- Positivação é o atendimento único do mês, contado com contagem distinta de cliente.
- Todas as posições de pedido contam; cancelado não vem na extração.
- Sábado é dia de venda (até meio-dia).
- `META` dos produtos foco é positivação e `META II` é financeiro.
- "PB" é a Polybalas, ou seja, o total.
