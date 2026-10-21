# Roteiro de teste · Fase 13 · Calendário

Leva uns 20 minutos, com a TV da sala ligada e o app aberto no seu PC. Use pelo menos duas pessoas (uma delas o gestor).

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. Esta fase muda o banco (migração 9): o Hub faz uma cópia antes, na pasta `copias`.
- No menu do app aparece **Calendário**, entre Prioridades e Painéis.

## Feriados
1. Abra **Calendário → Feriados**. Aparecem os nacionais do ano, calculados sozinhos: Sexta-feira Santa ligada, Carnaval e Corpus Christi **desligados** (ponto facultativo).
2. Como gestor ou administrador, acrescente um feriado da cidade (por exemplo, 30/11, "Aniversário da cidade"). Ele aparece na lista e no mês do calendário, com o fundo do dia avermelhado.
3. Desligue e ligue de novo um feriado. Como analista, os botões não aparecem.
4. No **Histórico**: "(nome) acrescentou o feriado 30/11/2026 Aniversário da cidade".

## O que o feriado muda
5. **Painéis:** num mês com feriado, abra **Metas do mês** na TV e compare o "esperado" com o Excel, contando os dias de venda **sem** o feriado. Desligue o feriado e veja o esperado mudar em até 1 minuto.
6. **Rotinas:** em **Rotinas**, edite uma rotina e veja a opção **roda também em feriado**. No dia de um feriado ligado, só as marcadas aparecem no Quadro (para testar sem esperar, crie um feriado da cidade para hoje e recarregue o Quadro; depois remova).
7. **Banco de horas:** o feriado não aparece em "dias sem lançamento". Quem trabalhou no feriado lança normalmente, e as horas viram saldo positivo.

## Compromissos
8. Clique em **+ Compromisso** (ou no número de um dia). Crie "Reunião de fechamento", amanhã às 15:00, local "Sala 3", com uma descrição e dois participantes. Ela aparece no mês com o horário e as iniciais.
9. Crie um compromisso **Só eu** ("Dentista"). Entre com outra pessoa: ele não aparece para ela, nem no histórico.
10. Crie um compromisso da equipe **Reservado**, sem a outra pessoa como participante. Para ela aparece "Compromisso reservado", sem abrir. O gestor abre normalmente.
11. Crie um compromisso que **repete toda semana**. Ele aparece em todas as semanas a partir da primeira data. Apague: somem todas as datas.
12. Troque para **Semana** e **Lista**: as anotações (tipo, local, "só eu") aparecem por extenso. Use ◀ ▶ e **Hoje**.
13. Nos filtros, ligue **Rotinas** e desligue **Prazos das demandas**: o calendário mostra e esconde na hora.

## Ausências
14. No fim da página do calendário, marque **minha ausência** de hoje até daqui a 3 dias, com o motivo "Férias". Ela aparece em cada dia e na lista "Ausências da equipe".
15. Entre com outra pessoa (não o gestor): ela vê a ausência, **sem** o motivo. O gestor vê o motivo e pode marcar ausência de qualquer um.
16. Na TV, na faixa de presença, a pessoa aparece como **Ausente · até dd/mm**. Se ela marcar "Na sala" no app, vale a presença.

## TV · tela Agenda
17. Com compromissos ou ausências entre hoje e os próximos dias úteis, a TV passa a mostrar a tela **Agenda** na rotação: um grupo por dia (Hoje, Amanhã, ...), com horário, título, tipo e iniciais.
18. Confira que **nunca** aparecem: a descrição, o local, os compromissos "só eu", o título de um reservado e o motivo da ausência.
19. Em **Configurações**, a tela Agenda tem o tempo próprio e pode ser desligada. Sem nada nos próximos dias, ela sai da rotação sozinha.
