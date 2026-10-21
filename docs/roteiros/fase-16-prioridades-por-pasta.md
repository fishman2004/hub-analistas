# Roteiro de teste · Fase 16 · Prioridades por pasta e o papel Assistente

Leva uns 15 minutos, no seu PC, com a TV da sala ligada.

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. O banco ganha duas tabelas novas (a cópia de antes fica na pasta de backups).
- Logo depois da atualização, as Prioridades funcionam como antes: nada muda até alguém ser ligado a uma pasta.

## Ligar as pessoas às pastas
1. Como administrador, abra **Pessoas**. Cada pessoa tem a linha **Pastas: A B C D E F G**. Marque as pastas de cada analista e clique em **Salvar pastas**. Uma pasta pode ficar com duas pessoas.
2. No **Histórico**: "(você) mudou as pastas de (nome): B, C".

## Marcar por pasta
3. Abra **Prioridades**. Abaixo da barra aparece o resumo por pasta ("A 0 de 4", "B 0 de 4"...). Cada item mostra as pastas, cada uma com "falta · (quem cuida dela)".
4. Entre como um analista com duas pastas (por exemplo, B e C) e clique em **Marcar como feita (B, C)**: as duas pastas ficam com "✓ (nome) · dd/mm hh:mm". O item continua em aberto enquanto faltar alguma pasta.
5. Com o mesmo analista, tente marcar uma pasta que não é dele: não aparece o botão. Clique em **Desfazer** numa pasta sua: ela volta para "falta".
6. Entre como o gestor (ou um administrador): todas as pastas têm o botão **Marcar**, para cobrir quem faltou. Marque as que faltam: o item fica "feita por todas as pastas" e a contagem sobe ("1 de 4 feitas").
7. Acrescente um item com a **pasta D**: ele pede só a pasta D.
8. Na **TV** (ou em TV da sala → ver Prioridades no meu PC): cada item mostra as letras das pastas. A que fez fica acesa com as iniciais de quem marcou, a que falta fica apagada e tracejada (vermelha, se atrasada). Quando tudo estiver feito, a tela sai da rotação.
9. No **Histórico**: "(nome) marcou “Entregar as comissões” como feita nas pastas B e C".

## Assistente
10. Em **Pessoas**, mude o papel de alguém para **Assistente** e clique em **Salvar acesso**: a linha das pastas some ("Assistente: sem pasta própria e fora das prioridades do mês"), e a pessoa sai das pastas que tinha.
11. Entre como o assistente e abra **Prioridades**: aparece "Assistente não faz as prioridades do mês", sem botões e sem "Acrescentar item".
12. O assistente continua no **Quadro** (pode ser responsável por demandas) e na presença da TV.
13. Como gestor, abra **Banco de horas → equipe**: há o quadro **Jornada dos assistentes** (padrão 06:00). Lance um dia do assistente das 8:00 às 14:30: o saldo do dia fica +00:30.
