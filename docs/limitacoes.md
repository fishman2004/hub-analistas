# Limitações conhecidas

- **O Hub só abre depois que alguém entra no Windows do PC reserva.** "Abrir com o Windows" usa a pasta Inicializar, que roda no login. Depois de uma reinicialização (por exemplo, atualização do Windows durante a noite) numa conta com senha, alguém precisa entrar no PC para o Hub e a TV voltarem.
- **Bloqueio de tela da empresa:** o Hub impede a suspensão e o descanso de tela, mas uma política de bloqueio definida pela TI pode bloquear a tela mesmo assim. Confira no primeiro uso.
- **Depende do PC reserva ligado.** Ele abre o Hub com o Windows e impede a suspensão e o descanso de tela. Se ele desligar, o app dos analistas para e a TV mostra "sem atualização".
- **Firewall:** os outros PCs precisam alcançar a porta 8800 do PC reserva. Se o Windows exigir administrador, a TI precisa criar uma regra (ver [primeiro-uso.md](primeiro-uso.md)).
- **PIN curto:** protege contra alguém agir no nome de outra pessoa pelo app, não contra quem tiver acesso ao arquivo do banco no PC reserva. Até cada pessoa criar o próprio PIN, outra pessoa poderia criá-lo no lugar dela (o administrador redefine se acontecer).
- **A sessão acaba à meia-noite:** quem deixa o app aberto de um dia para o outro precisa digitar o PIN de novo.
- **Atualização a cada 5 s na TV e 10 s no app**, não instantânea.
- **Mover cartões é por botões** (Começar, Concluir, Voltar). Arrastar e soltar fica para quando a equipe pedir.
- **Uma TV só.** Funciona em mais de uma (basta abrir `/tv`), mas foi pensada para a sala.
- **Painéis:** os dias de venda são de segunda a sábado, sem descontar feriados (a meta do dia e o "esperado" ficam um pouco abaixo do real num mês com feriado), e o sábado conta como um dia inteiro. Uma planilha de vendas em `.xlsx` muito grande demora mais para ler que em `.csv`; a TV continua com os dados anteriores enquanto isso.
- **Banco de horas:** não desconta feriados (num feriado é só não lançar o dia, que não conta) e não substitui o RH: vale o saldo que o RH mandar na próxima importação. O gestor não corrige o lançamento de ninguém; quem lançou corrige.
- **Rotinas: só as de hoje são calculadas.** Uma rotina de ontem em que ninguém mexeu some hoje sem deixar rastro (não fica atrasada); só o cartão que virou demanda (alguém moveu, editou ou marcou pasta) continua no quadro, atrasado pela data. O prazo vale dentro do mesmo dia (não passa da meia-noite) e feriados não são descontados: a rotina aparece e dá para dispensar o cartão do dia.
- **Pastas das rotinas:** qualquer pessoa marca qualquer pasta, porque o Hub não sabe de quem é cada pasta. O histórico guarda quem marcou.
- **O som da TV depende do navegador.** O Hub abre o Edge com a opção que libera o som, mas se o Edge já estava aberto antes ela pode não valer; aí é preciso liberar o site uma vez nas configurações do Edge (ver o [roteiro da fase 7](roteiros/fase-7-rotinas.md#som-na-tv)). O som também depende do volume da TV e da saída de áudio do PC. Se a TV estiver desligada no horário e ligar mais de 10 minutos depois, aquele aviso não toca.
- **Ainda não tem:** prioridades do mês e integração com o Pombo. Tudo está no [roadmap](roadmap.md).
