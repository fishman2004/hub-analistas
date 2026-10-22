# Roteiro de teste · Fase 17 · Entrar pelo nome e pedido de cadastro

Leva uns 10 minutos, no seu PC. Para o passo do pedido, peça ajuda a um colega (ou use uma janela anônima do navegador como se fosse outra pessoa).

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. O banco ganha uma tabela nova, a dos pedidos de cadastro (a cópia de antes fica na pasta de backups).
- Ninguém perde o PIN: quem já entrava continua entrando com o mesmo PIN.

## Entrar
1. Abra o Hub. A tela **Entrar** agora tem só **Seu nome** e **PIN**, sem a lista de botões com os nomes.
2. Digite o seu nome sem acento e em minúsculas (por exemplo, "kayo") e o seu PIN. Você entra no Quadro.
3. Clique em **Sair**. Digite o seu nome e um PIN errado: aparece "PIN errado. Mais 4 tentativas antes de bloquear", e o nome continua preenchido. Entre com o PIN certo.
4. Digite um nome que não existe (por exemplo, "Fulano de Tal"): aparece "Não achei ninguém com esse nome no Hub" e o link **Ainda não tenho cadastro**.

## Quem foi cadastrado pelo administrador
5. Como administrador, cadastre uma pessoa em **Pessoas** (por exemplo, "Teste Um"). Saia.
6. Na tela Entrar, digite só "teste um" e clique em **Entrar**: o Hub abre a tela **Primeiro acesso: crie o seu PIN**. Crie o PIN e entre.

## Pedido de cadastro
7. Numa janela anônima (ou no PC de um colega), abra o Hub e clique em **Ainda não tenho cadastro**.
8. Preencha o nome ("Teste Dois"), deixe as iniciais em branco e crie o PIN duas vezes. Clique em **Pedir cadastro**: aparece "Pedido enviado".
9. Tente entrar como "Teste Dois" com esse PIN: aparece "Seu pedido de cadastro ainda está esperando um administrador aprovar".
10. Como administrador, olhe o menu: **Pessoas** mostra uma bolinha com o número **1**. Abra Pessoas: no topo está **Pedidos de cadastro (1)**, com o nome e a hora do pedido.
11. Escolha **Analista** (ou **Assistente**) e clique em **Aprovar**: aparece "Teste Dois entrou na equipe como Analista". A pessoa aparece na lista e a bolinha do menu some.
12. Na janela anônima, entre como "Teste Dois" com o PIN escolhido no pedido: entra.
13. Faça outro pedido ("Teste Três") e, em Pessoas, clique em **Recusar**: o pedido some e ninguém foi criado.
14. No **Histórico**: "Teste Dois pediu cadastro no Hub", "(você) aprovou o cadastro de Teste Dois (Analista)" e "(você) recusou o pedido de cadastro de Teste Três".

## Proteções
15. Tente pedir cadastro com o seu próprio nome: aparece "Você já tem cadastro".
16. No mesmo aparelho, erre o PIN 10 vezes (pode ser em nomes diferentes): aparece "Muitas tentativas erradas neste aparelho. Tente de novo daqui a N minutos", até com o PIN certo. Os outros PCs continuam entrando normalmente. Espere os minutos indicados (ou reinicie o Hub) para liberar.

## Para terminar
17. Em **Pessoas**, desative as pessoas de teste.
18. Avise a equipe: para entrar, é só digitar o nome e o PIN. Quem é novo clica em **Ainda não tenho cadastro** e espera você ou o gestor aprovarem.
