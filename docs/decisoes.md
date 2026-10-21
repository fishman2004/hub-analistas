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

## Rotinas: calculadas, não agendadas (fase 7)

Segue a regra da v1. Uma rotina não cria nada sozinha: toda vez que o quadro é montado, o Hub vê quais rotinas valem hoje (dia da semana, ativa e horário já chegou) e desenha o cartão delas em "A fazer" do responsável. Não existe tarefa das 14:50 que possa falhar porque o PC estava desligado ou travado.

- **Vira demanda quando alguém mexe:** mover, editar, dispensar ou marcar uma pasta. Até lá o cartão é só cálculo, e o app aponta para ele por `rotina-<número>-<dia>`. A demanda nasce dentro da mesma gravação da ação: se a ação for recusada (por exemplo, "Aguardando"), nada fica criado pela metade.
- **Uma por rotina e por dia:** o banco tem um índice único em (rotina, dia). Dois PCs mexendo no mesmo cartão ao mesmo tempo dão na mesma demanda.
- **Dispensar** (excluir o cartão do dia) vale só para hoje: amanhã a rotina aparece de novo.
- **Mudar o cadastro** vale para os próximos cálculos. Um cartão que já virou demanda guarda o título e o dono dele; o horário, o prazo e as pastas seguem o cadastro.
- **Só o gestor e os administradores** cadastram e mudam rotinas, como na visão do gestor. Todo mundo vê a lista. Cada mudança vai para o histórico.
- Mudança no banco: migração 5 (tabelas `routines` e `routine_folders`, e `routine_id`/`routine_day` nas demandas). O número 4 é da fase 6 (banco de horas), feita em paralelo.

**Prazo (pedido do Kayo):** cada rotina pode ter um "até HH:MM". O cartão aparece no horário da rotina e, se não estiver concluído depois do prazo, fica atrasado como qualquer demanda atrasada (borda vermelha, entra no aviso "N demandas atrasadas" da TV e no filtro de atrasadas do gestor). No dia seguinte, um cartão que virou demanda e ficou aberto continua atrasado pela data.

**Pastas:** uma rotina pode ter pastas que marcam (as transferências usam B, C e F). Cada pasta marca a sua no app; a primeira marcada leva o cartão para Fazendo, com todas marcadas ele vai sozinho para Concluído hoje e desmarcar uma reabre em Fazendo. Enquanto falta pasta, o botão Concluir não aparece e o servidor recusa concluir à mão, para "liberada depois de" significar "todas as pastas marcaram".

**Liberada depois de:** a rotina só começa (nem marca pasta) quando as rotinas que ela espera estão concluídas no dia. Só conta a espera de hoje e só de rotinas que valem hoje: uma rotina que não roda naquele dia da semana, ou que foi dispensada, não segura ninguém.

**Aviso sonoro na TV:** o `/api/tv` manda as rotinas de hoje com o horário. A TV toca o som uma vez quando o horário chega e mostra uma faixa por cima de qualquer tela por 20 segundos. As rotinas já tocadas ficam guardadas no navegador (memória e `localStorage`), então recarregar a página não toca de novo; se a TV ligar mais de 10 minutos depois do horário, ela não toca atrasado. O som (`static/aviso.wav`, ~60 KB, três notas de sino) é gerado por `tools/gerar_som.py` só com a biblioteca padrão: nenhuma dependência nova e nada baixado da internet.

**Ver e testar o aviso (1.1.0, pedido do Kayo):** o aviso só acontecia na TV, então no app não dava para saber se havia algum programado nem testar sem criar uma rotina de mentira. A página **Rotinas** ganhou o quadro **Avisos de hoje na TV** (os mesmos avisos que o `/api/tv` manda, com o que já passou e o próximo) e o botão **Testar aviso na TV agora**, só para o gestor e os administradores, porque o som toca para a sala toda. O botão grava o horário do clique na tabela `settings` (sem migração) e, por 2 minutos, o `/api/tv` manda também um aviso "Teste do aviso" com aquele horário; a TV toca na próxima busca, em até 5 s, pelo mesmo caminho dos avisos de verdade. A chave do teste termina com a data, como as das rotinas, então recarregar a TV não toca de novo. O clique fica no histórico.

**Som sem clique:** navegadores bloqueiam som de página que ninguém clicou, e na TV ninguém clica. O Hub abre o Edge com `--autoplay-policy=no-user-gesture-required`, que não precisa de administrador. Se o Edge já estava aberto antes (o Edge costuma ficar rodando em segundo plano), essa opção pode não valer; aí basta liberar o site uma vez em `edge://settings/content/mediaAutoplay` (passo a passo no [roteiro](roteiros/fase-7-rotinas.md#som-na-tv)). Se o som estiver bloqueado, a faixa aparece igual, com o aviso "Som bloqueado pelo navegador".

**Reservada:** rotina não tem a opção reservada no cadastro. Se alguém marcar o cartão de hoje como reservado, a TV recebe só "Demanda reservada" (sem horário, pastas nem espera) e o aviso sonoro daquela rotina não vai para a TV.

### Em aberto (o Kayo confirma)

Padrões escolhidos sem resposta do Kayo; todos mudam pela página Rotinas ou com um ajuste pequeno no código:

1. **PHD só de segunda a sexta.** O Kayo disse "diária"; se for também no sábado, é marcar "sáb" na rotina.
2. **Comparativo de rotas às 10:00** nas terças e quintas: o horário não foi informado.
3. **Responsável das rotinas sugeridas** é quem clica em "Criar rotinas sugeridas". Trocar em Editar para o responsável de verdade de cada uma.
4. **Qualquer pessoa marca qualquer pasta** (o Hub não sabe de quem é cada pasta). O histórico guarda quem marcou. Se cada um só puder marcar a própria pasta, é preciso cadastrar a pasta de cada pessoa.
5. **Rotina com pastas só conclui quando todas marcarem** (o Concluir à mão é recusado) e a primeira pasta marcada leva o cartão para Fazendo.
6. **Um aviso só, no horário em que o cartão aparece**, com a faixa por 20 s. Não há um segundo aviso no prazo; se ajudar, dá para tocar de novo no "até HH:MM".
7. **Feriado:** desde a fase 13, a rotina não aparece em feriado ligado no calendário, salvo se marcar "roda também em feriado".

## Prioridades do mês (fase 8)

Uma lista por mês, guardada pelo mês da data (`2026-10`). Nada é agendado: no dia 1º a lista nova começa vazia e a do mês anterior fica só para consulta (dá para abrir pelos links no topo da página, sem botões). Assim o histórico de cada mês continua igual ao que foi.

- **Lista padrão do Kayo**, criada com um clique em "Criar lista padrão do mês": lançar a meta no sistema e confirmar o recebimento da meta com o gerente (sem prazo), entregar as comissões (até o dia 10) e entregar as campanhas (até o dia 15). O botão só aparece com o mês vazio, e o servidor confere de novo antes de criar: dois cliques (ou dois PCs) não criam duas listas. Qualquer outro item entra pelo "Acrescentar item", com pasta e prazo opcionais.
- **Prazo é um dia do mês** ("até dia 10"). No dia 10 ainda está no prazo; a partir do dia 11, se continuar em aberto, aparece como **atrasada**, no app e na TV (com o mesmo destaque vermelho das demandas atrasadas do Quadro). Como "Concluído hoje", isso é calculado na hora, não agendado.
- **Qualquer pessoa marca como feita** (confirmado pelo Kayo: não há dono por item) e qualquer pessoa desfaz. Fica guardado quem fez e quando, e tudo vai para o histórico. Se dois PCs marcam ao mesmo tempo, vale quem marcou primeiro.
- **Remover:** quem acrescentou o item ou um administrador. O item não é apagado do banco (só marcado), como as demandas.
- **Na TV**, a tela "Prioridades do mês" (15 s, mudável em Configurações) mostra o mês, "N de M feitas" com uma barra, e a lista: atrasadas primeiro, depois as outras em aberto, em destaque, e por fim as feitas, apagadas, com o check e as iniciais de quem fez na cor da pessoa. A letra da pasta usa as cores das pastas dos painéis. Quando tudo estiver feito (ou o mês não tiver lista), a tela sai da rotação sozinha. O servidor manda só o que a tela desenha: nada de nomes, horários ou quem criou.
- **Sem editar o texto** de um item: para corrigir, remova e acrescente de novo. Fica mais simples e o histórico mostra as duas coisas.
- Com mais uma tela, os nomes no indicador da rotação não cabiam lado a lado numa TV de 1366 px e se sobrepunham. Agora os nomes das outras telas encurtam com "…" e o da tela no ar fica inteiro. No app, o menu ganhou o link Prioridades e ficou um pouco mais justo para continuar numa linha só.

### Em aberto (confirmar com o Kayo)

Escolhas padrão desta fase, fáceis de mudar se ele preferir outra coisa:

1. **O que ficou em aberto no mês passado não passa para o mês novo.** Hoje a lista do mês anterior só fica para consulta. Alternativa: levar os pendentes para o mês novo ao criar a lista.
2. **A lista padrão é criada por um clique**, não sozinha no dia 1º. Alternativa: aparecer sozinha no primeiro dia útil, como as rotinas da fase 7.
3. **Quem pode remover:** quem acrescentou o item ou um administrador. Criar a lista padrão e acrescentar itens: qualquer pessoa.
4. **Prazo em dia corrido:** "até dia 10" não muda se o dia 10 cair num sábado, domingo ou feriado.
5. **Tempo da tela na TV:** 15 segundos, como as outras telas extras.

## Envios do Pombo: o Hub lê o histórico como o próprio Pombo (fase 9)

O Pombo já grava tudo o que envia num CSV por analista, numa pasta que pode ser da rede. O Hub só lê essa pasta: não precisa de servidor, banco ou mudança no Pombo, e não escreve nada lá (o histórico é o "estado" do Pombo, e mexer nele poderia causar reenvio). A pasta é uma configuração de administrador (**Configurações → Pombo**), guardada na tabela `settings`: sem migração. Em branco, a integração fica desligada.

**Mesma interpretação do Pombo.** A leitura das linhas, o que é linha estragada, como reconhecer cada destinatário e a ordem das situações copiam `pombo/history.py` e `pombo/engine.py`, para a TV nunca dizer uma coisa e a tela Hoje do Pombo outra. O Hub não usa a leitura de planilhas da fase 5 aqui: ela acha as colunas pelo nome e aceitaria uma linha que o Pombo ignora (por exemplo, um arquivo salvo pelo Excel com `;`). Da fase 5 vêm o jeito de configurar a pasta, o cache por data e tamanho do arquivo, a leitura em segundo plano e a página com a situação de cada arquivo.

**O que o Hub não sabe.** O Pombo conhece a agenda e a lista de destinatários de cada envio; o Hub só vê o histórico. Por isso um envio que ainda não chegou na hora não aparece, e "N de M enviados" conta os destinatários que já aparecem no histórico daquela rodada.

**"Em andamento" além do que o Pombo mostra.** Na tela Hoje do Pombo, uma falha aparece na hora, mesmo que ele vá tentar de novo em 5 minutos. Na TV isso assustaria à toa, então o Hub mostra "↻ tentando de novo" enquanto o Pombo ainda tem tentativas (menos de 4) e a última falha tem menos de 10 minutos. Depois disso, sem nova tentativa, vira falha: o Pombo daquele PC provavelmente está fechado. Também ficam "em andamento" a espera pelo arquivo e a espera pelo canal (WhatsApp desconectado). "Não atualizado" (o Pombo desistiu depois de 1 hora) e "perdido" (o Pombo estava fechado no horário) contam como falha, porque o relatório não saiu.

**Só rodadas com horário de hoje.** Uma rodada é do dia pelo horário dela (`horario_agendado`), não pela hora da linha: uma nova tentativa depois da meia-noite de uma rodada de ontem não aparece hoje.

**A TV nunca espera a pasta da rede.** Na fase 5, a TV ainda confere data e tamanho dos arquivos na hora da busca. Para a pasta do Pombo, que fica sempre na rede, até listar a pasta acontece na linha separada: a TV recebe a última leitura pronta. Se um arquivo não abrir (aberto no Excel) ou a pasta cair, a TV continua com a última leitura boa e mostra o aviso, em vez de sumir com a tela num soluço da rede.

**Na TV, só o necessário.** Horário, nome do envio, analista, canal e situação, com a contagem de destinatários (a regra "sem números" é só para vendas). Destinatários, motivo das falhas e nomes de arquivo ficam na página Envios, que pede login: o motivo de uma falha pode trazer um endereço de e-mail ou o nome de um grupo. O analista aparece com o nome, as iniciais e a cor do cadastro do Hub quando o nome que o Pombo grava (ou a pasta que ele cria com esse nome) bate com alguém da equipe.

**Indicador da rotação com mais telas.** Com a sétima tela, os nomes no topo da TV se sobrepunham. Agora o indicador ficou um pouco mais compacto e, se ainda faltar espaço (as fases 6 a 8 trazem telas novas), os nomes das outras telas encurtam com "…"; o da tela atual sempre aparece inteiro.

## Pausa da TV (fase 10)

Pedido do gestor: pausar a TV numa tela para analisar algo, tanto na própria TV quanto pelos PCs. São três jeitos, porque "analisar no nosso PC" pode querer dizer duas coisas:

- **Na própria TV:** um clique em qualquer lugar ou a tecla Espaço. As setas ← → trocam de tela e ↑ ↓ passam as páginas do Quadro. Essa pausa fica só na memória da página (recarregar volta à rotação).
- **A TV da sala pelo app:** a página **TV da sala** pausa numa tela, troca para a anterior ou a próxima, passa a página do Quadro e retoma. Qualquer pessoa com PIN, e tudo vai para o histórico (é reversível e fica registrado quem fez). Ela vence a pausa feita na TV; quem está na frente da TV vê o selo "Pausada por KI" piscar se clicar, e quem retoma é o app ou o prazo.
- **Ver uma tela no meu PC:** "Abrir no meu PC" abre `/tv?tela=<id>&fixa=1`, uma TV só daquela aba, parada, que não mexe na sala e não toca o aviso das rotinas.

**Toda pausa tem prazo** (15 minutos por padrão; pelo app, de 5 a 60 minutos ou até o fim do dia), para a TV nunca ficar esquecida parada. O prazo é calculado a cada busca, sem tarefa agendada. Durante a pausa os dados continuam atualizando, a presença e o relógio seguem e o **aviso das rotinas toca normalmente**.

**Qual tela está na TV agora:** a rotação acontece no navegador da TV, então o servidor não sabia. A TV passa a contar na busca que já faz a cada 5 s, e o servidor guarda só na memória (reiniciar o Hub esquece, e em 5 s a TV conta de novo). Sem notícia há mais de 30 s, a página diz que a TV não está conectada.

**Sem lugar a mais no topo:** com a TV pausada, o selo "⏸ Pausada" ocupa o lugar do indicador da rotação, que não teria o que mostrar.

Escolhas padrão aprovadas pelo Kayo (21/10/2026, perguntas 10.1 a 10.4 do [plano da v3](plano-v3.md)): 15 minutos, um clique, qualquer pessoa com PIN e aviso sonoro tocando com a TV pausada.

## Demandas com detalhes e anexos (fase 11)

Pedido do gestor: anexar arquivos (Excel, PDF) às demandas, para o responsável (inclusive quem criou) mexer depois. Editar a demanda já existia; faltavam a **descrição** (o Kayo pediu depois: para pedidos extensos, quem vê clica no cartão e lê) e os **arquivos**. No banco o campo continua `details`; na tela, "Descrição", e o cartão do quadro abre o texto com um clique (📝).

- **"Mexer depois" num arquivo** é baixar, editar no Excel e usar **Enviar nova versão**. O Hub não edita planilha no navegador (precisaria de um programa a mais e de internet). A versão de antes continua guardada e baixável em "versões anteriores", então ninguém perde o arquivo anterior.
- **Arquivo fora do banco e fora do repositório:** na pasta Anexos, com nome aleatório. O banco continua pequeno (a cópia diária segue rápida) e nenhum nome de arquivo estranho (`..\`, acento, nome repetido) chega ao disco.
- **Tipos aceitos:** `.xlsx`, `.xls`, `.xlsb`, `.csv`, `.pdf`, `.docx`, `.doc`, `.pptx`, `.txt`, `.png`, `.jpg`. Ficam de fora executáveis, scripts, `.zip`, `.html` e planilhas com macro (`.xlsm`), e o começo do arquivo precisa bater com a extensão (um `.exe` renomeado para `.pdf` é recusado). O Hub nunca abre nem executa o arquivo: entrega como download.
- **Limites:** 25 MB por arquivo (a 8081 tem ~23 MB), 20 arquivos por demanda e nada recebido com menos de 2 GB livres no disco (Configurações mostra o espaço usado e o livre).
- **Quem pode:** quem vê a demanda edita, anexa e baixa, como era com a edição; remove um arquivo quem anexou, o dono, o gestor e os administradores. Reservada segue a regra de sempre (só o dono, quem criou, o gestor e os administradores).
- **Lixeira de 30 dias:** remover tira o arquivo (e as versões dele) da lista; um administrador restaura em Configurações. Depois de 30 dias, a limpeza diária apaga do disco.
- **Achar demandas antigas:** "Concluído hoje" some no dia seguinte, e com ele o caminho para os arquivos. A página **Demandas** busca todas, por texto (título e detalhes), pessoa, pasta, situação, período e "só com arquivos".
- **Ao concluir pelo quadro**, aparece "Anexar o arquivo final?" (opcional), com o link para a demanda.
- **Na TV, nada muda:** nem os detalhes nem o 📎. Um teste rastreia o SQL do `/api/tv` e confere que a tabela `attachments` nunca é lida.

Escolhas padrão aprovadas pelo Kayo (21/10/2026, perguntas 11.1 a 11.6 do [plano da v3](plano-v3.md)).

## Bloco de notas pessoal (fase 12)

Pedido do gestor: um bloco de notas pessoal que também guarde arquivos.

- **Só a dona vê.** Nem o gestor, nem os administradores, como no banco de horas (onde o administrador também fica de fora). A rota responde "Nota não encontrada" igual para uma nota de outra pessoa e para uma que não existe, para nem contar que ela existe.
- **Fora do histórico:** o Histórico é lido por toda a equipe, e até o título de uma nota pode ser pessoal. Por isso criar, editar, anexar e excluir notas não gravam nada lá. A TV nunca consulta a tabela (um teste rastreia o SQL do `/api/tv`).
- **Grava sozinha** uns segundos depois da última tecla, e avisa "Não salvo… tentando de novo" se a rede cair. O botão Salvar continua lá (e funciona sem JavaScript).
- **Os arquivos** são os mesmos das demandas (tipos, 25 MB, 20 por nota, nova versão), na mesma pasta Anexos.
- **Fixar, arquivar, buscar** (a busca também acha as arquivadas) e **lixeira de 30 dias**: depois disso a nota é apagada de vez, com o texto.
- **Transformar em demanda** cria uma demanda da própria pessoa com o título e o texto da nota (os detalhes vão até 4.000 caracteres) e, se marcar, copia os arquivos. A nota continua como estava.
- **Baixar minhas notas:** um ZIP com cada nota em `.txt` (com BOM, para o Bloco de Notas do Windows ler os acentos) e os arquivos numa pasta ao lado.
- **Quem saiu da equipe:** as notas ficam guardadas e ninguém vê. Na página Pessoas, o administrador vê só quantas notas uma pessoa desativada deixou e pode apagá-las de vez, sem abrir nenhuma.
- **Privacidade de verdade tem limite:** o banco e a pasta Anexos não são cifrados. A página avisa para não guardar senhas.

Escolhas padrão aprovadas pelo Kayo (21/10/2026, perguntas 12.1 a 12.4 do [plano da v3](plano-v3.md)): só pessoais, ninguém mais vê, notas de quem saiu ficam guardadas e os mesmos limites dos anexos.

## Calendário (fase 13)

Pedido do gestor: "calendário". O Hub já sabia muita coisa com data (prazos, prioridades, rotinas); o calendário junta isso e acrescenta compromissos, feriados e ausências.

- **Três visões:** mês, semana e lista (30 dias), com filtros por tipo. As rotinas começam desligadas no filtro, porque lotariam o mês.
- **Compromisso:** reunião, entrega, treinamento ou evento, com dia (ou vários dias), horário ou dia todo, local, descrição e participantes. **Equipe** (todos veem) ou **só eu** (só quem criou; nem o histórico registra). Um da equipe pode ser **reservado**: quem não participa vê "Compromisso reservado", como a demanda reservada. Muda e apaga quem criou, o gestor e os administradores ("só eu": só quem criou).
- **Repetição simples,** calculada na hora: toda semana, todo mês ou todo ano. Mudar ou apagar vale para a série inteira.
- **Feriados:** os nacionais são calculados todo ano (inclusive Sexta-feira Santa); Carnaval e Corpus Christi são ponto facultativo e começam desligados. O gestor e os administradores ligam e desligam qualquer feriado e acrescentam os da cidade.
- **O que o feriado muda:** não conta como dia de venda na meta do dia e no "esperado" dos painéis, a rotina não aparece (salvo "roda também em feriado") e o banco de horas não pede lançamento. Os prazos das prioridades continuam em dia corrido.
- **Ausências:** cada pessoa marca a sua; o gestor marca a de qualquer um. O motivo é opcional e só a pessoa e o gestor veem; o histórico grava só as datas.
- **Na TV:** a tela **Agenda** (hoje e os próximos dias úteis) com compromissos da equipe, feriados e quem está ausente, sem descrição nem local; sai da rotação quando não há nada. Na faixa de presença, quem está ausente aparece como "Ausente até dd/mm", nunca o motivo; se a pessoa marcar presença no dia, vale a presença.
- **Sem Outlook:** o calendário é só do Hub (exportar `.ics` fica como ideia futura). Aniversários não entram sozinhos (dado pessoal); dá para criar como compromisso anual.

Escolhas padrão aprovadas pelo Kayo (21/10/2026, perguntas 13.1 a 13.5 do [plano da v3](plano-v3.md)).

## Modos da TV (fase 14)

Pedido do gestor: um "modo" para dias como Início de mês (mais demandas que números) e Fim de mês (mais números que demandas), um brainstorm de modos úteis e uma forma de criar modos.

- **Um modo é uma receita da rotação:** quais telas, em que ordem, quanto tempo cada uma, o tempo das páginas, o som do aviso e se os títulos aparecem. O que estava em Configurações virou o modo **Padrão**, sem mudar nada para quem não mexer.
- **Calculado, não agendado:** a cada busca da TV, o Hub vê qual modo vale: a escolha feita à mão (até o prazo), depois o primeiro da lista com regra ligada que vale agora, senão o Padrão. A ordem da lista desempata.
- **Início de mês e Fim de mês ligam sozinhos:** do dia 1º até o 5º dia útil, e dos 5 últimos dias úteis até o fim do mês. Dia útil aqui é de segunda a sexta, sem os feriados do calendário. No Fim de mês, o Quadro continua, com 15 s.
- **Brainstorm, pronto e sem ligar sozinho:** Fechamento do dia, Hora das transferências, Sábado, Campanha / Produtos foco, Reunião na sala (60 s por tela e sem som), Apresentação dos painéis, Visita (títulos escondidos) e Só o quadro. Os prontos não se apagam (só se desliga a regra); os criados pela equipe, sim.
- **Quem pode:** trocar o modo da TV da sala, qualquer pessoa com PIN (fica no histórico). Criar, editar, duplicar, apagar e mexer nas regras: gestor e administradores. Pré-visualizar no próprio PC: qualquer pessoa.
- **A TV nunca fica vazia:** se nenhuma tela do modo tiver o que mostrar, o Quadro aparece.
- **Títulos escondidos de verdade:** no modo Visita, o servidor nem manda os títulos (como na demanda reservada); não é só a tela que esconde.
- **Ninguém fica perdido:** o nome do modo aparece discreto no topo da TV, e a página TV da sala diz qual modo vale e por quê ("automático (nos 5 últimos dias úteis do mês)" ou "escolhido por Ana até 18:00").

Escolhas padrão aprovadas pelo Kayo (21/10/2026, perguntas 14.1 a 14.6 do [plano da v3](plano-v3.md)).

## Exportar a TV em PDF (fase 15)

Pedido do gestor: exportar uma das telas da TV em PDF, para mandar a alguém.

- **Sem gerar PDF no servidor e sem instalar nada:** a página de exportação desenha a TV numa folha do tamanho de uma TV Full HD e abre a janela de impressão do navegador, onde a pessoa escolhe **Salvar como PDF**. Os gráficos são SVG e saem nítidos.
- **Uma tela, a que está na TV agora ou todas** (um "retrato do dia", uma folha por tela). As telas que passam páginas (Quadro, Prioridades, Produtos foco, Envios) saem com todas as páginas, para não faltar nada.
- **A mesma regra da TV, sempre:** o PDF usa os mesmos dados do `/api/tv`. Painéis só em porcentagem, reservadas mascaradas, e nada de banco de horas, anexos, notas, descrição de compromisso ou motivo de ausência. Como um PDF pode ir para qualquer pessoa, isso protege igual ou mais que a TV. Um PDF com valores, só para o gestor, fica para outra fase.
- **Escuro, igual à TV,** com a opção **versão clara para imprimir** (gasta menos tinta).
- **Rodapé** com o nome da tela, a data e a hora e as **iniciais** de quem exportou (não o nome completo). O nome sugerido do arquivo é `Hub - (tela) - AAAA-MM-DD HHhMM`.
- **Quem pode:** qualquer pessoa com PIN, e fica no histórico (quem exportou qual tela e quando), porque o PDF sai da sala.
- **Sem imagem PNG** nesta fase: o PDF abre no celular.

Escolhas padrão aprovadas pelo Kayo (21/10/2026, perguntas 15.1 a 15.4 do [plano da v3](plano-v3.md)).

## Prioridades por pasta e o papel Assistente (fase 16)

Pedido do Kayo: cada pessoa confirma que fez as prioridades do mês **nas suas pastas**, e a lista mostra quem de cada pasta já fez. E um papel novo, **Assistente**, para os jovens aprendizes de meio período, que pegam demandas mais simples, sem responsabilidade direta por uma pasta, e não fazem as prioridades.

- **Cada pessoa é ligada às suas pastas** na página **Pessoas** (só administrador). Uma pessoa pode ter várias pastas, e uma pasta pode ter mais de uma pessoa: aí **qualquer uma delas** marca pela pasta (uma marca por pasta, com quem marcou).
- **Quais pastas cada item pede:** as pastas que têm alguém ligado. Item com pasta escolhida pede só aquela pasta. O item fica feito quando todas as pastas marcaram, e a TV continua até tudo estar feito.
- **Marcar:** "Marcar como feita" marca todas as pastas da pessoa naquele item de uma vez; cada pasta também tem o seu botão. O **gestor e os administradores** marcam (e desfazem) qualquer pasta, para cobrir uma falta ou férias.
- **Enquanto ninguém estiver ligado a uma pasta,** a lista funciona como antes (uma marcação para o item todo), para a atualização não mudar nada até o administrador escolher as pastas. Um item marcado antes da mudança continua feito para todas as pastas.
- **Na TV:** cada item mostra as letras das pastas; a que fez fica acesa com as iniciais de quem marcou, a que falta fica apagada e tracejada (em vermelho, se atrasada). Sem nomes, como sempre.
- **Assistente:** sem pasta e fora das prioridades (vê a lista, mas não cria, marca nem remove). Pode ser responsável por demandas e por rotinas, aparece na presença da TV e usa o banco de horas com a **jornada dos assistentes** (padrão 6h de segunda a sexta, sábado sem jornada; o gestor muda no Banco de horas da equipe). Não vê a visão do gestor.

Escolhas padrão, o Kayo confirma (21/10/2026): jornada do assistente (6h), assistente responsável por rotinas e o gestor/administradores cobrindo qualquer pasta.
