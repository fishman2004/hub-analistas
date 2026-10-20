# Roteiro de teste · Fase 5 · Painéis de dados

Leva uns 20 minutos, com o app aberto num PC e olhando para a TV.

## Antes de começar
- Depois de extrair o ZIP por cima, rode `instalar.bat` de novo: esta fase traz uma peça nova (o leitor de `.xlsx`).
- Tenha à mão as 6 planilhas do mês, com os nomes exatos (veja [paineis.md](../paineis.md#os-6-arquivos)).

## Pasta dos painéis
1. Entre no app como administrador e abra **Painéis** no menu. A página mostra a pasta (padrão: `%LOCALAPPDATA%\Hub\Painéis`) e as 6 planilhas como "Arquivo não encontrado na pasta" (a de metas por fornecedor é opcional).
2. Na TV, nada mudou: sem planilhas, as telas de metas não entram na rotação.
3. Envie a planilha **Fornecedores e pastas** pelo botão **Enviar** da página (pode ser com outro nome, como `Fornecedor_pasta.xlsx`). A linha fica verde, "Lida (N linhas)". Confira na pasta: o arquivo foi salvo como `(BASE) - Fornecedores Polybalas.xlsx`.
4. Copie as outras planilhas direto para a pasta, com os nomes certos (a 8081 pode continuar em `.csv`). Recarregue a página: todas "Lida".

## TV
5. Em até uns 10 segundos, entram na rotação **Metas do mês**, **Metas do dia** (se o último dia com venda não for domingo) e **Produtos foco**.
6. **Metas do mês:** o topo diz o mês, "vendas até" o último dia com venda e "atualizado às" a hora do arquivo. O gráfico mostra uma barra por dia (quanto o dia fez da meta do dia; a linha tracejada é 100%) e uma linha branca com o mês acumulado comparado ao esperado, terminando em "mês X%". Abaixo, um cartão por pasta (A a G e T) para financeiro e positivações, com a marca branca do esperado.
7. Confira 2 ou 3 porcentagens com o painel do Excel. Se alguma não bater, anote qual (pasta, financeiro ou positivação) para ajustar a regra em [paineis.md](../paineis.md#como-o-hub-calcula).
8. **Metas do dia:** barras de financeiro e positivações do último dia, com a linha dos 100%.
9. **Produtos foco:** para cada produto foco, uma barra de positivação (META) e uma de financeiro (META II), do melhor para o pior. Foco sem META II mostra "—" no financeiro. Com muitos focos, a tela passa as páginas sozinha (o número da página aparece no título).
10. **Em nenhuma tela aparece valor em reais, quantidade ou nome de vendedor ou cliente**: só porcentagens, letras das pastas e nomes dos produtos foco.

## Atualizar os dados
11. Exporte a 8081 de novo por cima do arquivo da pasta. Em poucos segundos a hora de "atualizado às" muda e as porcentagens acompanham.
12. Abra uma planilha da pasta no Excel e salve com uma coluna renomeada (por exemplo, `PASTA` → `PASTAS`). A página Painéis mostra em vermelho "Faltam as colunas: PASTA." e as telas de metas saem da TV; Produtos foco continua. Desfaça e salve: as telas voltam.
13. Em **Configurações → Painéis de dados**, mude "Avisar que os dados estão velhos" para 1 hora. Se a 8081 tiver mais de 1 hora, a TV mostra **Dados desatualizados** no topo das telas de metas. Volte para 24.

## Permissões
14. Como analista, a página Painéis abre, mas sem os botões de envio. `Configurações` não aparece.
15. No **Histórico**, aparece "enviou a planilha … dos painéis" com quem enviou.

## Regras de sempre
16. A TV nunca rola, em nenhuma tela, e continua alternando se o servidor cair (aviso "Sem atualização desde HH:MM").
