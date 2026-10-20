# Decisões técnicas

## Servidor no PC reserva (a confirmar no teste de rede)

- O PC reserva da sala roda o Hub e mostra a TV. Os analistas abrem o app pelo navegador, sem instalar nada.
- **Falta confirmar:** se o Firewall do Windows deixa outros PCs abrirem a porta 8800 sem administrador (`tools/net_test.py`).
- **Se bloquear:** pedir à TI uma regra de entrada para a porta 8800. Se a TI recusar, o plano B é uma pasta compartilhada (como no Pombo), o que muda a arquitetura.

## SQLite em vez de CSV

Aqui várias pessoas escrevem ao mesmo tempo, mas só um programa (o servidor) acessa o arquivo. Um banco SQLite em modo WAL é simples, vem com o Python e aguenta escritas simultâneas com segurança.

## Regras do dia calculadas, não agendadas

"Concluído hoje", "Fora da empresa" depois da meia-noite e "atrasada" são calculados a partir das datas toda vez que a tela é montada. Não existe tarefa de meia-noite que possa falhar porque o PC estava desligado.

## Sem senha na versão 1 (substituído pelo PIN na fase 2)

Equipe pequena, rede interna, nada sigiloso fora das demandas reservadas (que não aparecem na TV). A pessoa escolhe o próprio nome uma vez, e o navegador lembra. Todo movimento fica no histórico com o nome de quem fez.

## Tema claro/escuro guardado no navegador (fase 1)

A preferência de tema é de cada pessoa e de cada PC, não do Hub. Por isso fica no `localStorage` do navegador, sem tabela nova, sem migração e sem depender de login (que só chega na fase 2). Se o navegador não deixar guardar, o app fica no automático e segue o Windows. Três opções (automático, claro, escuro) num botão só, que alterna a cada clique, para não ocupar espaço no cabeçalho.

A TV fica de fora de propósito: ela tem o próprio tema escuro, pensado para ler de longe, e não pode mudar porque alguém escolheu o claro no PC dele.

Ao revisar as cores, o texto branco dos botões de presença marcados no modo escuro tinha pouco contraste (cerca de 2:1 sobre o verde e o amarelo). Agora o texto acompanha o tema (`--sobre-cor`): branco no claro, escuro no escuro, acima de 4,5:1 nos dois.

## PIN de 4 a 6 números, não senha (fase 2)

Para gestor e banco de horas, escolher o nome não basta. Um PIN curto é rápido de digitar várias vezes ao dia e suficiente numa rede interna, porque quem tenta pelo app esbarra no bloqueio: 5 erros seguidos travam aquele nome por 5 minutos. No banco fica só o resumo PBKDF2-SHA256 (200 mil rodadas, sal diferente por pessoa), da biblioteca padrão do Python: nenhuma dependência nova.

- **Sessão até a meia-noite:** cobre o dia de trabalho sem pedir o PIN a cada página, e ninguém fica logado no PC de outra pessoa de um dia para o outro.
- **Esqueceu o PIN:** um administrador apaga o PIN (não vê nem define), e a pessoa cria outro no próximo acesso.
- **Primeiro administrador:** o código não pode trazer nomes reais (o repositório é público). Por isso, enquanto não há administrador, quem cria o primeiro PIN vira administrador. Na atualização, o Kayo entra primeiro e depois marca o gestor.
- **Sempre um administrador:** o Hub recusa tirar a marcação ou desativar o último, para ninguém ficar sem conseguir gerenciar.
- **Risco aceito:** até cada pessoa criar o próprio PIN, outra pessoa poderia criá-lo no lugar dela. O roteiro da fase pede que todos criem o PIN no primeiro dia; se acontecer, o administrador redefine.

## Migração do banco versionada (fase 2)

O `PRAGMA user_version` guarda qual foi a última mudança aplicada. Ao iniciar, o Hub faz uma cópia do banco e aplica só o que falta, cada mudança dentro de uma transação. Assim a atualização continua sendo extrair o ZIP e rodar `instalar.bat`, sem passo manual e sem perder dados.

## Quem vê o título de uma demanda reservada (fase 3)

Decisão do Kayo: veem o título **o gestor, os administradores, o dono da demanda e quem a criou** (inclusive quando alguém cria uma demanda reservada para outra pessoa). Para todos os outros, o app mostra a demanda como a TV mostra: "Demanda reservada", a cor e as iniciais do dono e o prazo, sem link e sem botões. Abrir, mover ou excluir pelo endereço direto também é recusado. Na v1, qualquer analista via tudo no app.

Para saber quem criou, a migração 2 acrescenta `created_by` às demandas e preenche as antigas a partir do histórico (o evento "demanda_criada" já guardava quem fez).

## A visão do gestor também abre para administradores (fase 3)

O plano dizia "só para gestor". Os administradores já gerenciam pessoas, papéis e PINs e veem as reservadas, então também abrem a visão do gestor. Analistas não abrem.
