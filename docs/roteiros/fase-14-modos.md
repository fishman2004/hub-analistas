# Roteiro de teste · Fase 14 · Modos da TV

Leva uns 15 minutos, com a TV da sala ligada e o app aberto no seu PC.

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. Esta fase muda o banco (migração 10), com cópia antes.
- Os tempos que estavam em **Configurações → Telas da TV** continuam iguais: eles viraram o modo **Padrão**.

## Os modos prontos
1. No app, abra **TV da sala** e clique em **Ver e pré-visualizar os modos** (ou vá direto em `/modos`). Aparecem Padrão, Início de mês, Fim de mês e os outros, com as telas e quando ligam sozinhos.
2. Em **Fim de mês**, clique em **Pré-visualizar**: abre uma aba com a TV já nesse modo, com "Pré-visualização · Fim de mês" no topo. As telas passam sozinhas. A TV da sala não muda.
3. Hoje vale o modo da linha marcada "na TV agora". Nos 5 primeiros dias úteis do mês vale **Início de mês**, e nos 5 últimos, **Fim de mês** (sem contar sábado, domingo e feriados do calendário).

## Trocar o modo da TV da sala
4. Na página **TV da sala**, em **Modo da TV**, escolha **Reunião na sala** e **Por 1 hora**, e clique em **Trocar o modo**. Em até 5 segundos a TV mostra "Reunião na sala" no topo e passa as telas mais devagar (60 s cada).
5. Com esse modo, um gestor clica em **Rotinas → Testar aviso na TV agora**: a faixa aparece, **sem som**.
6. Troque para **Visita**: os cartões aparecem só como "Demanda", com a cor e as iniciais. Os títulos não aparecem nem na Agenda.
7. Escolha **Voltar ao automático**: a TV volta ao modo que vale para hoje.
8. No **Histórico**: "(nome) pôs a TV da sala no modo “Visita”" e "(nome) fez a TV da sala voltar ao modo automático".

## Criar um modo (gestor ou administrador)
9. Em **Modos da TV**, clique em **+ Novo modo**. Dê o nome "Fechamento da pasta B", ligue **Metas do dia** e **Quadro**, use ↑ ↓ para pôr Metas do dia primeiro, e em **Liga sozinho** escolha "Dias do mês", do dia 28 ao 31, com a **Regra ligada**. Salve.
10. Clique em **Duplicar** num modo pronto: a cópia nasce com a regra desligada. Apague a cópia (os modos prontos não têm **Apagar**: só dá para desligar a regra).
11. Use ↑ ↓ na lista: com duas regras valendo no mesmo dia, vence a de cima.
12. Como analista, a página mostra os modos e **Pré-visualizar**, mas não **Editar** nem **+ Novo modo**.

## Sem nada para mostrar
13. Troque para **Apresentação dos painéis** com a pasta dos painéis vazia (ou sem as planilhas): a TV mostra o Quadro, em vez de ficar vazia.
