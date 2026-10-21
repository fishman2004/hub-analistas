# Roteiro de teste · Fase 15 · Exportar a TV em PDF

Leva uns 10 minutos, no seu PC, com a TV da sala ligada. Use o Edge (ou o Chrome).

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. Esta fase não muda o banco.

## Uma tela
1. No app, abra **TV da sala**. Em **Ver uma tela no meu PC**, cada tela tem **Exportar PDF**. Clique no de **Metas do mês**.
2. Abre uma aba com a tela igual à TV, com o nome da tela no topo e um rodapé: "Hub dos Analistas · Metas do mês · gerado em dd/mm/aaaa às HH:MM por (suas iniciais)". A janela de impressão abre sozinha.
3. Na janela, em **Destino**, escolha **Salvar como PDF** e clique em **Salvar**. O nome sugerido é "Hub - Metas do mês - AAAA-MM-DD HHhMM". Se a janela não abrir, clique em **Salvar em PDF** no topo da aba.
4. Abra o PDF: uma folha em paisagem, com as cores da TV e os gráficos nítidos. Só porcentagens, nenhum valor em reais nem quantidade.

## Todas as telas
5. Em **Exportar em PDF**, clique em **Exportar todas as telas da rotação**. O PDF sai com uma folha por tela. Se o Quadro tiver colunas com mais de uma página ("1/2"), ele sai em mais de uma folha, e o rodapé diz "página 1 de 2". Uma coluna que acabou aparece como "Fim da coluna".
6. Clique em **Todas, versão clara para imprimir**: o mesmo PDF, com fundo branco, para imprimir no papel.
7. Clique em **Exportar a tela que está na TV agora**: sai a tela que a TV da sala está mostrando. Com a TV desligada, aparece "A TV da sala não está conectada agora".

## Regras
8. Crie uma demanda **reservada** e exporte o Quadro: no PDF aparece só "Demanda reservada".
9. Ponha a TV no modo **Visita** e exporte: os cartões saem só como "Demanda".
10. No **Histórico**: "(nome) exportou em PDF a tela “Metas do mês” da TV".
