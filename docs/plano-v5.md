# Plano do Hub dos Analistas · v5 (calendário de rotinas, trilha do dia e animações)

> Pedido do Kayo em 22/10/2026, com duas sugestões do gestor: um **calendário de rotinas** que também passe na TV e uma **trilha de rotinas** de cada analista ao longo do dia. Junto, o pedido de deixar o Hub inteiro mais vivo (animações) e com uma experiência de uso melhor.
> **Situação:** em execução. As escolhas sem resposta do Kayo estão marcadas com **Padrão:** e anotadas em `decisoes.md` como "Em aberto (o Kayo confirma)".

## Ponto de partida

O `main` está na **1.10.0** (v4), com a migração **12**. Já existem e serão aproveitados:

- **Rotinas com horário (fase 7):** um cartão em "A fazer" no horário, aviso na TV e atraso depois do prazo.
- **Calendário (fase 13):** mês, semana e lista, com compromissos, feriados (nacionais calculados e os da cidade), ausências, prazos, prioridades e rotinas. Na TV, a tela **Agenda**.
- **Modos da TV (fase 14):** uma tela nova entra sozinha no fim de cada modo, ligada só no Padrão.
- **Pastas de cada pessoa (fase 16)** e as cores padrão das pastas.
- **TV com telas plugáveis** (`hub/telas.py` + `static/tv-telas/`), paginação com fade e exportar em PDF (fase 15).

## Os modelos do gestor

1. **"Rotinas mensais" (rotinas macro):** um calendário do mês, de segunda a sexta largas e sábado e domingo estreitos, em que cada dia lista as rotinas na forma **CATEGORIA: descrição**, com uma cor por categoria (Acompanhamentos e Gestão de equipe em azul claro; Metas, Fechamento, Abertura, Validações e Comissionamento em amarelo; APEX em azul-marinho; as críticas em vermelho) e o feriado pintado de verde. Há dois tipos de rotina: as **da semana** (toda segunda, toda terça e quinta...) e as **do mês** (o 1º dia útil, o 3º dia útil, os últimos dias úteis).
2. **"Rotinas semanais" (rotinas micro):** a trilha de um dia de uma analista (a foto da analista, a pasta e o dia da semana), com blocos de horário (08:00 às 09:00, 09:01 às 09:30...), cada um com um ícone num círculo colorido, o nome e o que fazer (Acompanhamento da pasta, Black-list, PHD, Devolutivas, Campanhas, Intervalo, Insights, Transferência de pedidos...). A segunda e a terça mudam alguns blocos.

## Brainstorm

### Calendário de rotinas (rotinas macro)

- **Não é compromisso nem rotina com horário.** Compromisso (fase 13) é um evento com data e hora; rotina (fase 7) gera um cartão e um aviso. A rotina do mês é um **plano**: o que a equipe acompanha em cada dia, sem horário. Se virasse cartão, o quadro lotaria (5 a 8 itens todo dia). Por isso ganha um cadastro próprio, que **calcula** os dias (como o resto do Hub), em vez de gravar um item por dia.
- **Regras de repetição** que cobrem o modelo inteiro: dias da semana; o **N-ésimo dia útil** do mês; o **N-ésimo dia útil antes do fim** (1 = último); um **dia fixo** do mês (cai no fim de semana ou feriado: vai para o próximo dia útil); e uma **data única**. Dia útil = segunda a sexta sem os feriados ligados no Calendário, então o 1º de maio (feriado) empurra tudo como no modelo.
- **Categorias com cor**, editáveis, já com as do modelo. O texto sobre a cor (claro ou escuro) é calculado pelo contraste. **Destaque** pinta a rotina de vermelho, como as críticas do modelo.
- **Responsável opcional:** quando os analistas mandarem as demandas, cada uma pode ter dono (as iniciais aparecem na TV).
- **Feito no dia:** qualquer pessoa marca uma rotina do mês como feita naquele dia, e fica guardado quem e quando. Assim o "zoom no dia" da TV mostra o que já foi feito e o que falta, em vez de só repetir o plano.
- **Na TV (o pedido do Kayo):** a tela **Rotinas do mês** mostra o mês inteiro, como o modelo, e, depois de um tempo, **dá um zoom no dia de hoje** (o quadradinho do dia cresce até ocupar a tela) e abre a lista do dia, grande, com as cores, os donos, o que já foi feito e o próximo dia útil ao lado. Com a TV pausada, ↑ ↓ alternam entre o mês e o dia. No PDF, viram duas folhas (o mês e o dia).
- **No app:** uma visão nova no Calendário, **Rotinas do mês**, igual ao modelo (com o feriado em verde e hoje destacado) e com o botão de marcar feito no dia de hoje. O cadastro (rotinas e categorias) fica numa página própria, para o gestor e os administradores. Um botão **Criar as rotinas do modelo** cria as do print do gestor (sem nomes de pessoas), para começar e ajustar depois; as que os analistas mandarem entram pelo formulário.
- **No calendário do mês e da semana:** um filtro "Rotinas do mês", desligado por padrão (lotaria o mês).

### Trilha do dia (rotinas micro)

- **Cada analista tem a sua trilha**, por dia da semana. Um bloco tem início, fim, nome, o que fazer (uma linha por item), ícone, cor e o tipo (**tarefa** ou **pausa**, como o Intervalo, que nunca fica "não feito"). O mesmo bloco pode valer em vários dias da semana, para não repetir o cadastro.
- **A luz, como o Kayo imaginou:**
  - bloco que ainda não chegou: apagado;
  - **agora:** a luz pulsa no bloco e um ponto de luz anda pela trilha na hora certa;
  - **feito no horário:** luz forte (verde);
  - **feito depois do fim:** luz média (âmbar);
  - **não feito** depois do fim: **luz negativa** (vermelha, pulsando devagar).
  - Toda vez que a tela aparece, uma luz **varre a trilha** do começo do dia até agora, acendendo cada bloco no passo dela: é a "luz passando em cada horário".
- **Como marca feito:** no app, um botão ✓ no bloco (a própria pessoa, o gestor e os administradores), na página **Trilha** e numa faixa **Minha trilha de hoje** em cima do Quadro, onde a pessoa já trabalha. **Bloco ligado a uma rotina** (fase 7): quando o cartão da rotina é concluído, o bloco acende sozinho.
- **Na TV:** a tela **Trilhas do dia**, uma linha por analista (quem está ausente no Calendário fica de fora), com o tempo de verdade no eixo (das 08:00 às 18:00), o ponto de luz no "agora", o bloco atual por extenso à direita ("Agora · 10:01 às 11:00 · Devolutivas: retornos pendentes, atendimento extra...") e quantos já fez. Com mais de 4 analistas, passa as páginas com fade.
- **Cadastro rápido:** **Criar a trilha do modelo** (os blocos dos prints do gestor) e **Copiar a trilha de outra pessoa**, para montar a equipe em minutos.
- **Para o gestor:** na página Trilha, quanto cada um fez no horário nos últimos 5 dias úteis.

### Animações e UI/UX (o Hub inteiro)

O app hoje quase não tem movimento, e a TV só troca de tela com um fade. A ideia é dar vida sem cansar ninguém, sempre com `transform` e `opacity` (leves para o PC da sala) e respeitando quem pede "menos movimento" no Windows.

**App:**

- **Menu agrupado:** com 15 links numa linha, o menu já cansa. Viram 5 grupos (Dia a dia, Planejamento, Dados, TV, Gestão) com submenus, sem JavaScript (`<details>`), e o ☰ continua no celular.
- **"Ir para…" (Ctrl+K):** uma caixinha para pular para qualquer página digitando, para quem usa o teclado.
- **Transição entre páginas** (o navegador desliza de uma página para a outra) e entrada suave do conteúdo.
- **Mensagens de sucesso** viram um aviso que some sozinho, com uma barrinha de tempo e um ×.
- **Quadro vivo:** a cada atualização de 10 s, o cartão novo ou que mudou de coluna brilha um instante; ao concluir, um "✓" verde.
- **Números que contam** até o valor (resumo do gestor) e **barras que crescem** (prioridades, banco de horas).
- **Toque nos botões** (afundam ao clicar) e cartões que levantam ao passar o mouse.

**TV:**

- **Troca de tela** com fade e um leve zoom, e **entrada em cascata** dos cartões, linhas e barras de cada tela.
- **Barras dos painéis crescem do zero** e as **porcentagens contam** até o valor quando a tela aparece.
- **Demanda concluída comemora:** o cartão que acabou de chegar em "Concluído hoje" brilha em verde com um ✓.
- **Presença:** quem muda de status pisca suavemente.
- **Fundo com um degradê que se move bem devagar**, que também ajuda a TV a não marcar a imagem (tela parada o dia inteiro).

### Melhorias no que já existe (achadas estudando o código)

Entram nas fases abaixo:

- A troca do quadro a cada 10 s substitui o HTML inteiro: agora compara os cartões para animar só o que mudou (fase 21).
- As mensagens verdes ficam paradas na página para sempre (fase 21).
- O mês do Calendário corta em 5 itens por dia: a visão Rotinas do mês mostra todos (fase 19).
- A Agenda e as Rotinas do mês dividem o mesmo cálculo de dia útil e feriado do Calendário, sem regra duplicada (fase 19).
- O modo **Visita** esconde também os textos das telas novas (fases 19 e 20).

Ficam como ideia para depois (anotadas no roadmap):

- **Pombo acende a trilha:** quando o Pombo envia o PHD, o bloco do PHD acende sozinho (depende da outra frente, a do Pombo).
- **Importar as rotinas do mês de uma planilha**, se os analistas mandarem tudo num Excel.
- **Exportar o calendário em .ics** para o Outlook (já estava na lista).
- **Aviso no celular** quando um bloco da trilha começa (pede notificação no navegador; depende do HTTPS, que a rede interna não tem).

## Fases

A numeração continua (a v4 terminou na fase 18). Um branch e um PR por fase, empilhados na ordem, com o Kayo como autor.

| Fase | Entrega | Migração | Versão |
|---|---|---|---|
| 19 | **Rotinas do mês:** cadastro com categorias e regras, visão no Calendário, marcar feito no dia e a tela da TV com o mês e o zoom no dia | 13 | 1.11.0 |
| 20 | **Trilha do dia:** blocos por analista e dia da semana, marcar feito, faixa no Quadro, página Trilha e a tela da TV com a luz | 14 | 1.12.0 |
| 21 | **Animações e UI/UX:** menu agrupado, Ctrl+K, transições, avisos, quadro vivo e as animações da TV | nenhuma | 1.13.0 |

Regras de sempre: nada que exija administrador do Windows; migração automática com cópia antes, que só acrescenta; TV sem CDN, sem rolar e sem título de reservada; nenhum nome real no repositório; testes com pytest; roteiro manual em `docs/roteiros/`.

## Padrões escolhidos (o Kayo confirma)

**Rotinas do mês (fase 19)**

- Padrão: cadastram e mudam as rotinas do mês e as categorias **o gestor e os administradores**; **qualquer pessoa** marca feito no dia (fica guardado quem).
- Padrão: só dá para marcar feito **no dia de hoje** (e desfazer no mesmo dia).
- Padrão: **dia fixo** que cai no fim de semana ou feriado vai para o **próximo dia útil**.
- Padrão: as rotinas do modelo usam a semana do print (Desempenho e Acompanhamento do representante todo dia; Blacklist seg e qui; APEX e MSL seg, qua e sex; Campanhas e Gestão de equipe ter e qui) e os dias úteis do mês de maio de 2026 (por exemplo, "Input de metas no sistema" no 3º dia útil). As marcas do MSL ficam fora do repositório ("MSL das marcas foco").
- Padrão: a tela da TV mostra o mês por **40% do tempo** (no máximo 10 s) e depois dá o zoom; tempo padrão da tela, 25 s.

**Trilha do dia (fase 20)**

- Padrão: quem monta a trilha de uma pessoa: **ela mesma, o gestor e os administradores**. Quem marca feito: os mesmos.
- Padrão: marcar feito **só no dia de hoje**; "não feito" vale assim que o horário do bloco termina, e marcar depois deixa o bloco âmbar (feito com atraso).
- Padrão: a trilha não roda em feriado nem para quem está ausente no Calendário.
- Padrão: blocos da mesma pessoa **não podem se sobrepor** no mesmo dia da semana (quebraria a linha do tempo).
- Padrão: a trilha do modelo usa o print de segunda em **seg, qua e sex** e o de terça em **ter e qui** (só vimos esses dois dias).
- Padrão: na TV, **até 4 analistas por página**.

**Animações (fase 21)**

- Padrão: tudo com movimento curto (0,2 a 0,8 s, menos o zoom do calendário e a varredura da trilha), e **sem movimento nenhum** quando o Windows está com "Mostrar animações" desligado.
