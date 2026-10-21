# Roteiro de teste · Fase 11 · Demandas com descrição e anexos

Leva uns 15 minutos, com o app aberto em dois PCs (ou duas pessoas). Tenha à mão uma planilha `.xlsx` e um PDF **sem dados sigilosos**.

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala. Ao abrir, o Hub copia o banco para `%LOCALAPPDATA%\Hub\copias` e acrescenta os detalhes e os anexos sozinho, sem mexer nos dados.

## Descrição
1. Abra uma demanda sua. Abaixo de "Prazo" aparece **Descrição**. Escreva duas linhas e clique em **Salvar**.
2. No Quadro, o cartão mostra **📝 Descrição**: clique e o texto abre ali mesmo, com as quebras de linha. Clique de novo para fechar.
3. Abra a demanda de novo: no fim da página, a **Linha do tempo** mostra "(você) editou “…”: descrição".
4. Mude o prazo e o dono e salve. No **Histórico** aparece "editou “…”: dono X → Y, prazo dd/mm → dd/mm".

## Arquivos
5. Na seção **Arquivos** da demanda, escolha a planilha e o PDF de uma vez e clique em **Anexar**. Os dois aparecem com o tamanho, quem anexou e quando. No quadro, o cartão ganha um **📎 2**.
6. Clique em **Baixar** na planilha: o navegador baixa com o nome original. Abra no Excel, mude algo e salve.
7. Clique em **Enviar nova versão** ao lado dela e escolha o arquivo salvo. A lista continua com um arquivo só e aparece "1 versão anterior"; abrindo, dá para baixar a de antes.
8. Tente anexar um arquivo `.zip` ou `.xlsm`: aparece "esse tipo de arquivo não é aceito". Um arquivo de mais de 25 MB: "grande demais".
9. Em **+ Nova demanda**, preencha e escolha um arquivo no campo **Arquivos** antes de salvar: a demanda nasce com o anexo.

## Quem pode
10. No outro PC (outra pessoa), abra a mesma demanda: ela consegue baixar e anexar, mas **Remover** só aparece nos arquivos que ela anexou. O dono da demanda, o gestor e os administradores veem **Remover** em todos.
11. Crie uma demanda **reservada** com um anexo. Outra pessoa (que não é dona, não criou e não é gestor nem administrador) não abre a demanda, e no Histórico vê "anexou um arquivo em “Demanda reservada”".

## Remover e lixeira
12. Remova um arquivo (pede confirmação). Ele some da lista.
13. Como administrador, abra **Configurações → Anexos das demandas**: o arquivo está na **Lixeira**. Clique em **Restaurar**: ele volta para a demanda. A mesma seção mostra o espaço usado e o livre no disco.

## Concluir e achar depois
14. No quadro, conclua uma demanda: aparece "“…” concluída. **Anexar o arquivo final?**", com o link para a demanda.
15. Abra **Demandas** no menu. Estão todas, inclusive as concluídas em outros dias. Busque por uma palavra da descrição, filtre por pessoa e marque **Só com arquivos**.

## TV
16. Na TV, nada mudou: sem descrição, sem 📎, sem nomes de arquivo.
