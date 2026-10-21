# Roteiro de teste · Fase 7 · Rotinas com horário e aviso sonoro

Leva uns 25 minutos, com o app aberto num PC e olhando (e ouvindo) a TV. Para não esperar até as 14:50, os passos usam uma **rotina de teste** com horário daqui a 2 ou 3 minutos; no fim, ela é desativada.

## Antes de começar
- Depois de extrair o ZIP por cima, rode `instalar.bat` e reinicie o Hub (feche o `iniciar.bat` e abra de novo). Esta fase não traz dependência nova; a mudança no banco roda sozinha, com cópia antes.
- Confira que o som do PC da sala sai pela TV (ícone de som do Windows) e que a TV não está no mudo.

## Som na TV
O navegador só toca som numa página que alguém clicou, e na TV ninguém clica. O Hub abre o Edge com uma opção que libera isso, mas se o Edge **já estava aberto** (ele costuma ficar rodando em segundo plano) a opção pode não valer. Faça isto uma vez no PC da sala, sem precisar de administrador:

1. No Edge do PC da sala, abra uma aba nova e digite `edge://settings/content/mediaAutoplay`.
2. Em **Permitir**, clique em **Adicionar** e digite `http://127.0.0.1:8800`. Adicione também `http://localhost:8800`.
   - Se a sua versão do Edge não mostrar a lista, escolha **Permitir** na opção "Controlar se áudio e vídeo são reproduzidos automaticamente" (vale para o Edge todo deste PC, que é só da TV).
3. Feche o Edge e abra o Hub de novo pelo `iniciar.bat`.
4. Plano B, se nada disso der certo: depois que a TV abrir, **clique uma vez na tela da TV** com o mouse do PC da sala. O som fica liberado até a página recarregar.

Se o som estiver bloqueado, a faixa do aviso aparece igual, com a frase "Som bloqueado pelo navegador".

## Cadastro (gestor ou administrador)
5. No app, abra **Rotinas** no menu. A lista está vazia.
6. Clique em **Criar rotinas sugeridas**. Aparecem 6 rotinas, todas com você como responsável:
   - PHD · positivação diária: seg a sex, 08:00, até 09:00;
   - Transferência de pedidos: seg a sex, 14:50, até 15:00, pastas B, C e F;
   - Atualização de positivações no grupo de gestão comercial: seg a sex, 15:00, liberada depois da transferência das 14:50;
   - Transferência de pedidos: seg a sex, 16:50, até 17:00, pastas B, C e F;
   - Atualização de positivações no grupo de gestão comercial: seg a sex, 17:00, liberada depois da transferência das 16:50;
   - Comparativo de rotas no grupo de gestão comercial: ter e qui, 10:00.
7. Clique de novo em **Criar rotinas sugeridas**: "As rotinas sugeridas já existem" (não duplica).
8. Em cada uma, clique em **Editar** e escolha o **responsável** de verdade. Confira os padrões [em aberto](../decisoes.md#em-aberto-o-kayo-confirma) (dias da PHD, horário do comparativo) e ajuste se precisar.

## Rotina de teste: o cartão aparece no horário
9. No formulário **Nova rotina**: nome "Teste do Hub", **Aparece às** daqui a 2 minutos, **Prazo** daqui a 4 minutos, o dia de hoje marcado, pastas **B** e **C**. Salve.
10. Antes do horário, nada muda no quadro nem na TV.
11. No horário: a TV **toca o aviso uma vez** e mostra a faixa "Hora da rotina · HH:MM Teste do Hub · até HH:MM" por cima da tela, por uns 20 segundos.
12. Em até 5 segundos, o cartão "Teste do Hub" aparece em **A fazer** do responsável, no app e na TV, com o relógio "rotina HH:MM · até HH:MM" e as letras **B** e **C** apagadas (0/2).
13. Recarregue a TV (F5 no PC da sala, ou feche e abra o `iniciar.bat`): o aviso **não** toca de novo.

## Pastas
14. Num PC de outra pessoa (não o responsável), abra o app: no topo aparece **Pastas para marcar** com o "Teste do Hub". Clique na letra **B**: ela fica verde, e o cartão vai para **Fazendo**. Na TV, a letra B fica cheia, com a cor da pasta (1/2).
15. Clique em **C**: com todas marcadas, o cartão vai sozinho para **Concluído hoje**.
16. Clique de novo em **C** (desmarcar): o cartão volta para **Fazendo**. Marque C de novo.
17. No **Histórico** aparece "… marcou a pasta B em “Teste do Hub”", com o nome de quem marcou.

## Liberada depois de e prazo
18. Crie uma segunda rotina "Teste depois", horário daqui a 1 minuto, sem prazo, **Liberada depois de: Teste do Hub HH:MM**. Desmarque uma pasta do "Teste do Hub" para ele não estar concluído.
19. Quando "Teste depois" aparecer, o cartão mostra "Aguardando: Teste do Hub HH:MM" e não tem o botão **Começar**.
20. Marque a pasta que faltava no "Teste do Hub": o "Aguardando" some e o **Começar** aparece.
21. Deixe um cartão com prazo sem concluir até passar do prazo: ele fica com a borda vermelha e "atrasada · até HH:MM", e o topo da TV conta mais uma em "demandas atrasadas". Conclua: o aviso diminui.

## Permissões
22. Como analista, a página **Rotinas** abre só para ver: sem formulário, sem **Editar** e sem **Criar rotinas sugeridas**. O analista continua conseguindo marcar pastas no quadro.
23. No **Histórico** aparecem "cadastrou a rotina …", "editou a rotina …" e "desativou a rotina …", com quem fez.

## Limpeza
24. Em **Rotinas**, clique em **Desativar** nas duas rotinas de teste. Os cartões de hoje que já viraram demanda continuam no quadro (dá para excluir); amanhã elas não aparecem mais.

## Regras de sempre
25. A TV nunca rola, em nenhuma tela, mesmo com os cartões de rotina (as colunas passam as páginas sozinhas).
26. Feche o Hub no PC da sala: a TV continua com a última tela e avisa "Sem atualização desde HH:MM".
