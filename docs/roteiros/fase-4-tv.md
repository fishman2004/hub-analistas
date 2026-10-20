# Roteiro de teste · Fase 4 · TV em rotação

Leva uns 10 minutos, olhando para a TV da sala.

## Rotação
1. Depois de atualizar, a TV abre como sempre, no Quadro. No topo, ao centro, aparecem os nomes das telas ("Quadro" e "Prazos da semana") com uma barrinha que enche enquanto a tela está no ar.
2. Se ninguém tiver demanda com prazo nesta semana, só o Quadro aparece e não há nomes no topo. Crie uma demanda com prazo para amanhã: em até 5 segundos, "Prazos da semana" entra na rotação.
3. Depois de 30 segundos no Quadro, a TV passa para **Prazos da semana** com um fade, sem recarregar. Lá aparecem as colunas Atrasadas, Hoje, Amanhã e Próximos dias (só as que têm algo). Depois de 15 segundos, volta ao Quadro.
4. Uma demanda reservada aparece como "Demanda reservada" também em Prazos da semana.

## Aviso de atrasadas
5. Com uma demanda atrasada, o topo mostra em vermelho "1 demanda atrasada", nas duas telas. Conclua a demanda: o aviso some.

## Paginação das colunas
6. Com muitas demandas em "A fazer" (umas 10 ou mais), o título da coluna mostra "1/2" (ou mais páginas). A cada 10 segundos a coluna troca de página com um fade. Nada fica escondido em "+ N".
7. Quando a TV volta da outra tela para o Quadro, as colunas recomeçam da página 1.

## Configurações (administrador)
8. No app, entre como administrador e abra **Configurações**. Mude o tempo do Quadro para 20, o de Prazos para 10 e o de cada página para 6. Salve.
9. Em até 5 segundos, a TV passa a usar os tempos novos.
10. Desmarque **Ligada** em Prazos da semana e salve: a TV fica só no Quadro. Marque de novo para voltar.
11. Como analista, o menu não tem Configurações, e abrir `/configuracoes` direto mostra "Sem permissão".

## Regras de sempre
12. A TV nunca rola, em nenhuma tela.
13. Feche o Hub no PC da sala (ou tire o cabo de rede): a TV continua mostrando a última tela, continua alternando e avisa "Sem atualização desde HH:MM". Ao voltar, o aviso some.
