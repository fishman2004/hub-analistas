# Roteiro de teste · Fase 22 · Base 8081 automática do Google Drive

Leva uns 20 minutos, a primeira vez. Precisa da conta Google que abre o arquivo da 8081 (a do gestor, ou a sua se o arquivo estiver compartilhado com você) e de um administrador do Hub.

## Antes de começar
- Extraia o ZIP por cima, rode `instalar.bat` e reinicie o PC da sala, como sempre. Nada muda no banco.
- No PC da sala, abra o navegador e entre em `https://script.google.com`. Se não abrir, o PC da sala não chega à internet: fale com a TI antes de continuar.
- Confira no Drive que o arquivo da 8081 **não** está como "Qualquer pessoa com o link" (Compartilhar → Acesso geral → **Restrito**). Com a ponte, ninguém mais precisa do link público.

## Fazer a ponte
1. Siga os passos 1 a 6 de [`docs/drive-8081.md`](../drive-8081.md#passo-a-passo-uma-vez-só): projeto novo no Apps Script, colar `tools/drive/ponte-8081.gs`, propriedade `ARQUIVO_ID`, implantar como App da Web ("Eu" e "Qualquer pessoa") e copiar o endereço `/exec`.
2. Cole o endereço `/exec` numa aba anônima do navegador (Ctrl+Shift+N). Tem de aparecer só `{"ok":false,"erro":"chave"}`. **Isso prova que, sem a chave, ninguém baixa as vendas.**

## Ligar no Hub
3. Entre no Hub como administrador → **Configurações → Base 8081 do Google Drive**. Cole o endereço, deixe **Gerar chave nova** marcado e **Salvar**.
4. A mensagem verde mostra a chave **uma vez**. Copie e cole na propriedade `CHAVE_HUB` da ponte. Recarregue Configurações: a chave não aparece mais (só "Guardada").
5. Tente salvar com um endereço que não seja do Google (ex.: `https://exemplo.com`): o Hub recusa.

## Baixar
6. Abra **Painéis**. O quadro **Base 8081 do Google Drive** diz "ligado". Clique em **Baixar agora**: aparece "Arquivo novo baixado" e a linha **Vendas (8081)** fica **Lida**, com a hora em que a automação gerou o arquivo no Drive.
7. Clique em **Baixar agora** de novo: "O arquivo do Drive não mudou" (nada é baixado).
8. Abra a TV: as telas de metas mostram "atualizado às" com a hora do arquivo do Drive.
9. Espere a automação do gestor rodar de novo (ou abra o arquivo no Drive e mude algo). Em até 10 minutos a página Painéis mostra o "Último arquivo novo baixado" novo, sem ninguém clicar.

## Quando dá errado (deve avisar, sem estragar a TV)
10. Na ponte, mude a `CHAVE_HUB` (apague uma letra) e clique em **Baixar agora** no Hub: aparece "A ponte recusou a chave". A TV continua com os dados anteriores. Volte a chave certa.
11. Tire o cabo de rede (ou desligue o Wi-Fi) do PC da sala por um instante e clique em **Baixar agora**: "Sem conexão com o Google". Ligue de volta.

## Desligar (se precisar)
12. Em Configurações, apague o endereço e salve: o download para e a chave é apagada. A 8081 continua podendo ser salva na pasta ou enviada pela página Painéis.
