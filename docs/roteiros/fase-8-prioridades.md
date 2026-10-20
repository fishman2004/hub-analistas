# Roteiro de teste · Fase 8 · Prioridades do mês

Leva uns 10 minutos, com o app aberto em dois PCs (ou duas pessoas) e olhando para a TV.

## Antes de começar
- Extraia o ZIP por cima e rode `instalar.bat`, como sempre. Esta fase não traz peça nova; ao abrir, o Hub copia o banco para `%LOCALAPPDATA%\Hub\copias` e prepara o lugar das prioridades sozinho, sem mexer nos dados.

## Lista do mês
1. Entre no app e abra **Prioridades** no menu. O título diz o mês ("Prioridades de outubro de 2026") e aparece o quadro **Lista padrão do mês** com os 4 itens: lançar a meta no sistema, confirmar o recebimento da meta com o gerente, entregar as comissões (até dia 10) e entregar as campanhas (até dia 15).
2. Na TV, nada mudou ainda: sem lista, a tela de prioridades não entra na rotação.
3. Clique em **Criar lista padrão do mês**. Os 4 itens aparecem com "0 de 4 feitas" e a barra vazia. O botão some (o mês já tem lista).
4. Se hoje já passou do dia 10, "Entregar as comissões" aparece em vermelho como **atrasada · até dia 10** (e as campanhas depois do dia 15). No dia do prazo ainda não fica vermelho.
5. Em **Acrescentar item**, crie "Novos acompanhamentos" com pasta B e prazo de um dia que já passou. Ele entra no fim da lista, atrasado. Tente acrescentar o mesmo item de novo: aparece "Esse item já está na lista do mês" e o que você digitou continua no formulário. Com prazo 40, o navegador avisa que o dia vai só até o último dia do mês.

## TV
6. Em até 5 segundos, **Prioridades do mês** entra na rotação (o nome aparece no topo). Na vez dela: o mês, "0 de 5 feitas" com uma barra verde e a lista. As atrasadas vêm primeiro, com borda vermelha e "atrasada · até dia N"; a pasta B aparece com a letra na cor da pasta.
7. No outro PC (outra pessoa), clique em **Marcar como feita** em "Lançar a meta no sistema". No app aparece "feita por (nome) em dd/mm às HH:MM". Na TV, o item vai para o fim, apagado, com o check verde e as iniciais de quem fez, na cor da pessoa; o contador vira "1 de 5 feitas".
8. Clique em **Desfazer**: o item volta a ficar em aberto, no app e na TV.

## Permissões
9. Como analista, nos itens que outra pessoa acrescentou não aparece **Remover**; nos que você acrescentou, aparece (pede confirmação). Um administrador vê **Remover** em todos.
10. **Marcar como feita** e **Desfazer** funcionam para qualquer pessoa.

## Tudo feito
11. Marque todos os itens como feitos. A página diz "tudo feito: a tela saiu da TV" e, em até 5 segundos, a tela de prioridades sai da rotação. Desfaça um: ela volta.

## Histórico e configurações
12. No **Histórico**: "criou a lista padrão de prioridades de …", "acrescentou … às prioridades do mês", "marcou como feita a prioridade …", "desmarcou …" e "removeu …", com quem fez.
13. Em **Configurações** (administrador), a tela **Prioridades do mês** aparece com 15 segundos. Dá para mudar o tempo ou desligar.

## Virada do mês (no dia 1º)
14. A lista do mês novo começa vazia e a TV não mostra mais a do mês anterior. No topo da página aparece o link do mês anterior: ele abre a lista antiga só para consulta (sem botões), com quem fez cada item.

## Regras de sempre
15. A TV nunca rola. Com muitos itens (uns 12 ou mais), a tela usa duas colunas e, se ainda não couber, passa as páginas sozinha com um fade ("1/2" ao lado do contador).

Algumas escolhas desta fase ainda esperam a confirmação do Kayo (pendentes do mês passado, criar a lista sozinha no dia 1º e outras): veja [decisoes.md](../decisoes.md#em-aberto-confirmar-com-o-kayo).
