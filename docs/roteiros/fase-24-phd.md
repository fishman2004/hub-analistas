# Roteiro de teste · Fase 24 · PHD automático

Leva uns 15 minutos. Precisa de um administrador do Hub, da 8081 lida em Painéis e, para a parte do Pombo,
do Pombo atualizado (com "Print da planilha") no PC de um analista.

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. Nada muda no banco.

## Gerar
1. Abra **Painéis**. O quadro **PHD automático** já mostra "Gerado em ..." com um arquivo por pasta (o Hub
   gera sozinho em até 1 minuto depois que a 8081 muda).
2. **Configurar**: escolha a pasta de rede, escreva as áreas (`B-BJ = CAMPINA GRANDE`, uma por linha) e
   **Salvar e gerar**. Os arquivos aparecem na pasta.
3. Baixe o `PHD - Pasta B.xlsx` pelo link e abra no Excel: linha 15 com ÁREA, ID, VENDEDOR, SUPERVISOR e o
   total de cada dia; um vendedor por linha; cores verde, laranja e rosa.

## Conferir com o PHD de hoje (uma vez)
4. Escolha 3 vendedores e 2 dias e compare com a sua planilha do PHD: os números de positivação têm de bater.
   Se não baterem, anote o vendedor, o dia e os dois números e mande para ajustar a regra.
5. Compare a coluna **MÉDIA**: aqui é a média por dia de venda do mês até ontem. Se a sua planilha usa outra
   conta, anote qual.

## Ligar no Pombo
6. No Pombo: Envios › Novo envio › **Preencher com o modelo do PHD**, Planilha = o PHD da sua pasta na rede,
   o grupo, seg a sex, 08:45. Salve e clique em **Pré-visualizar o print**: um print por supervisor.
7. **Enviar teste só para mim**: chegam as fotos com a legenda no seu WhatsApp.

## Quando dá errado (deve avisar)
8. Abra um `PHD - Pasta X.xlsx` no Excel no PC da sala e clique em **Gerar agora**: aparece o aviso de que não
   conseguiu gravar (o Excel trava o arquivo). Feche o Excel e gere de novo.
9. Se a 8081 parar de chegar, o PHD fica com a hora da última 8081 e o Pombo não envia (espera e avisa).
