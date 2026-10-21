# Roteiro de teste · Fase 11 · Demandas com detalhes e anexos

Leva uns 15 minutos, com o app aberto em dois PCs (ou duas pessoas). Tenha à mão uma planilha `.xlsx` e um PDF **sem dados sigilosos**.

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala. Ao abrir, o Hub copia o banco para `%LOCALAPPDATA%\Hub\copias` e acrescenta os detalhes e os anexos sozinho, sem mexer nos dados.

## Detalhes
1. Abra uma demanda sua. Abaixo de "Prazo" aparece **Detalhes**. Escreva duas linhas e clique em **Salvar**.
2. Abra de novo: o texto está lá, com as quebras de linha. No fim da página, a **Linha do tempo** mostra "(você) editou “…”: detalhes".
3. Mude o prazo e o dono e salve. No **Histórico** aparece "editou “…”: dono X → Y, prazo dd/mm → dd/mm".

## Arquivos
4. Na seção **Arquivos** da demanda, escolha a planilha e o PDF de uma vez e clique em **Anexar**. Os dois aparecem com o tamanho, quem anexou e quando. No quadro, o cartão ganha um **📎 2**.
5. Clique em **Baixar** na planilha: o navegador baixa com o nome original. Abra no Excel, mude algo e salve.
6. Clique em **Enviar nova versão** ao lado dela e escolha o arquivo salvo. A lista continua com um arquivo só e aparece "1 versão anterior"; abrindo, dá para baixar a de antes.
7. Tente anexar um arquivo `.zip` ou `.xlsm`: aparece "esse tipo de arquivo não é aceito". Um arquivo de mais de 25 MB: "grande demais".
8. Em **+ Nova demanda**, preencha e escolha um arquivo no campo **Arquivos** antes de salvar: a demanda nasce com o anexo.

## Quem pode
9. No outro PC (outra pessoa), abra a mesma demanda: ela consegue baixar e anexar, mas **Remover** só aparece nos arquivos que ela anexou. O dono da demanda, o gestor e os administradores veem **Remover** em todos.
10. Crie uma demanda **reservada** com um anexo. Outra pessoa (que não é dona, não criou e não é gestor nem administrador) não abre a demanda, e no Histórico vê "anexou um arquivo em “Demanda reservada”".

## Remover e lixeira
11. Remova um arquivo (pede confirmação). Ele some da lista.
12. Como administrador, abra **Configurações → Anexos das demandas**: o arquivo está na **Lixeira**. Clique em **Restaurar**: ele volta para a demanda. A mesma seção mostra o espaço usado e o livre no disco.

## Concluir e achar depois
13. No quadro, conclua uma demanda: aparece "“…” concluída. **Anexar o arquivo final?**", com o link para a demanda.
14. Abra **Demandas** no menu. Estão todas, inclusive as concluídas em outros dias. Busque por uma palavra dos detalhes, filtre por pessoa e marque **Só com arquivos**.

## TV
15. Na TV, nada mudou: sem detalhes, sem 📎, sem nomes de arquivo.
