# Decisões técnicas

## Servidor no PC reserva (a confirmar no teste de rede)

- O PC reserva da sala roda o Hub e mostra a TV. Os analistas abrem o app pelo navegador, sem instalar nada.
- **Falta confirmar:** se o Firewall do Windows deixa outros PCs abrirem a porta 8800 sem administrador (`tools/net_test.py`).
- **Se bloquear:** pedir à TI uma regra de entrada para a porta 8800. Se a TI recusar, o plano B é uma pasta compartilhada (como no Pombo), o que muda a arquitetura.

## SQLite em vez de CSV

Aqui várias pessoas escrevem ao mesmo tempo, mas só um programa (o servidor) acessa o arquivo. Um banco SQLite em modo WAL é simples, vem com o Python e aguenta escritas simultâneas com segurança.

## Regras do dia calculadas, não agendadas

"Concluído hoje", "Fora da empresa" depois da meia-noite e "atrasada" são calculados a partir das datas toda vez que a tela é montada. Não existe tarefa de meia-noite que possa falhar porque o PC estava desligado.

## Sem senha na versão 1

Equipe pequena, rede interna, nada sigiloso fora das demandas reservadas (que não aparecem na TV). A pessoa escolhe o próprio nome uma vez, e o navegador lembra. Todo movimento fica no histórico com o nome de quem fez.

## Tema claro/escuro guardado no navegador (fase 1)

A preferência de tema é de cada pessoa e de cada PC, não do Hub. Por isso fica no `localStorage` do navegador, sem tabela nova, sem migração e sem depender de login (que só chega na fase 2). Se o navegador não deixar guardar, o app fica no automático e segue o Windows. Três opções (automático, claro, escuro) num botão só, que alterna a cada clique, para não ocupar espaço no cabeçalho.

A TV fica de fora de propósito: ela tem o próprio tema escuro, pensado para ler de longe, e não pode mudar porque alguém escolheu o claro no PC dele.

Ao revisar as cores, o texto branco dos botões de presença marcados no modo escuro tinha pouco contraste (cerca de 2:1 sobre o verde e o amarelo). Agora o texto acompanha o tema (`--sobre-cor`): branco no claro, escuro no escuro, acima de 4,5:1 nos dois.
