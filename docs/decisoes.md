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

## TV em rotação no navegador (fase 4)

A rotação acontece no JavaScript da TV, sem recarregar a página: o servidor só diz quais telas entram e por quanto tempo, e os dados continuam chegando a cada 5 s. Se o servidor cair, a rotação segue com o último estado e o aviso "sem atualização". Tempos padrão do plano: Quadro 30 s e as demais 15 s, mudáveis por um administrador em **Configurações** (de 5 a 300 s). As configurações ficam numa tabela `settings` (migração 3), guardando só o que mudou do padrão.

**Presença e relógio ficam fixos** em todas as telas: são o motivo da TV existir ("quem está na sala"), então não saem de vista na rotação.

**Primeira tela extra: Prazos da semana.** Para a rotação ser útil já nesta fase (e provar que uma tela "pluga" sem mexer nas outras), entrou uma tela com as atrasadas e o que vence hoje, amanhã e nos próximos dias. Ela usa os mesmos dados públicos do Quadro (reservada continua mascarada) e só aparece quando há prazo na semana.

## Paginação das colunas em vez de "+ N" (fase 4, ideia do Kayo)

Com muitas demandas, "+ N demandas" escondia justamente o que a sala precisava ver. Agora cada coluna do Quadro se divide em páginas que cabem na tela e passa de uma para outra com um fade (padrão 10 s por página, configurável). O número da página aparece no título da coluna ("2/3"). Ao voltar para o Quadro na rotação, as colunas recomeçam da primeira página. A TV continua sem rolar.

## Painéis de dados: o Hub calcula, a TV só recebe porcentagens (fase 5)

O plano dizia "o Hub não calcula, só exibe". Na hora de fazer, o Kayo pediu o contrário: guardar as planilhas que o time já usa (metas por pasta e por fornecedor, fornecedores, produtos foco e a 8081 de vendas) numa pasta própria e deixar o Hub montar o painel que hoje é feito no Excel. Assim ninguém precisa preparar um arquivo extra só para a TV. As regras do cálculo estão em [paineis.md](paineis.md), num arquivo só do código (`hub/paineis.py`).

**Cores das pastas** seguem o padrão da empresa (a cor da marca mais forte de cada pasta) e aparecem só na letra da pasta. As barras continuam com as cores de faixa (verde a vermelho), para a cor da pasta nunca ser confundida com o resultado.

**Só porcentagens na TV**, por decisão do gestor (gerentes, vendedores e executivos passam pela sala). Isso é garantido no servidor: o `/api/tv` só recebe percentuais, as letras das pastas e textos fixos, e um teste confere que nenhum valor, quantidade ou nome das planilhas aparece na resposta.

**Cor pelo ritmo no mês.** Comparar o realizado do mês com a meta cheia deixaria tudo vermelho até o fim do mês. A cor do mês compara com o esperado até o último dia com venda (dias de venda já passados, de segunda a sábado); a cor do dia compara com a meta do dia.

**O mês é o da venda mais recente do arquivo**, não o do relógio: assim a TV continua certa no dia 1º, antes da primeira exportação do mês novo, e com arquivos de teste.

**Leitura em segundo plano.** A 8081 tem ~23 MB; a TV não pode esperar a leitura (ela desiste em 4 s e mostraria "sem atualização"). O Hub relê o arquivo numa linha separada e, enquanto isso, a TV segue com os dados anteriores.

**Pasta e envio.** A pasta padrão fica ao lado do banco (`%LOCALAPPDATA%\Hub\Painéis`) e um administrador pode apontar para outra (por exemplo, na rede). Para quem não quer mexer em pastas, a página Painéis aceita o envio do arquivo pelo navegador e grava com o nome certo, trocando o antigo de uma vez (a TV nunca lê um arquivo pela metade).

## Dependência nova: openpyxl (fase 5)

As planilhas de metas, fornecedores e produtos foco são `.xlsx`. Pedir ao time para salvar tudo em CSV seria um passo manual a mais a cada exportação. O **openpyxl** lê `.xlsx` e é Python puro (ele e a única dependência dele, `et-xmlfile`): instala com o `instalar.bat` de sempre, sem compilar nada e sem administrador. Ele só é carregado quando há uma planilha `.xlsx` para ler.

## Banco de horas: saldo calculado, só a pessoa e o gestor (fase 6)

Pedido do Kayo: o RH envia o saldo atual de cada um, o gestor importa, e daí em diante cada analista lança a entrada e a saída do dia pelo comprovante do ponto. **Não substitui o RH**: serve para cada um saber se está com horas extras ou negativas.

- **O saldo não é guardado, é calculado:** saldo base + a diferença de cada dia lançado depois da data do saldo base. Corrigir um dia, mudar a jornada ou importar um saldo novo do RH recalcula tudo sem "acertos" manuais. Os dias até a data do saldo base não podem ser lançados (já estão no saldo do RH).
- **Jornada = horário inteiro, com o almoço dentro:** a equipe não bate ponto no almoço, então a jornada padrão é das 8h às 18h (10:00) de segunda a sexta. A diferença do dia é (saída − entrada) − jornada. O gestor muda a jornada (e pode dar jornada ao sábado) na página da equipe.
- **Dia sem lançamento não conta** (nem como falta): ele aparece em "Faltam lançar" para a pessoa completar. Assim um esquecimento não vira saldo negativo.
- **Quem vê:** só a própria pessoa e o **gestor** (papel). Administrador sozinho não vê: ser administrador é cuidar do Hub, não das horas de ninguém. Cada um lança só o próprio; o gestor vê, importa, ajusta o saldo base e exporta, mas não lança no lugar de ninguém.
- **Correção fica no histórico** (antes → depois), visível só para a pessoa e o gestor.
- **A planilha do RH não fica guardada:** é lida na hora (colunas `NOME`, `SALDO` e, se tiver, `DATA`) e descartada. Os nomes precisam bater com o cadastro do Hub; os que não batem são listados.
- **Exportar:** saldos e dias lançados em Excel (`openpyxl`, que já era dependência) ou CSV com `;`.
