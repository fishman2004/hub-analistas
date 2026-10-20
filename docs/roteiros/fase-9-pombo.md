# Roteiro de teste · Fase 9 · Integração com o Pombo

Leva uns 20 minutos, com o app aberto num PC, o Pombo aberto no PC de um analista e olhando para a TV.

## Antes de começar
- Extraia o ZIP por cima e rode `instalar.bat`, como sempre. Esta fase não traz peça nova.
- Descubra a pasta do histórico do Pombo: no Pombo de um analista, **Configurações › Pasta do histórico** (por exemplo `Y:\Pombo\historico`). Todos os analistas precisam usar a **mesma** pasta.
- No PC da sala, abra essa pasta no Explorador de Arquivos. Dentro dela deve haver uma pasta para cada analista (`ana-souza`, `carla-dias`...) com arquivos como `2026-10.csv`. Se o PC da sala não abrir a pasta, o Hub também não vai conseguir.

## Ligar a integração
1. Entre no app como analista e abra **Envios** no menu. A página diz que a integração está desligada. Na TV, nada mudou.
2. Entre como administrador e abra **Configurações → Pombo**. Digite um caminho que não existe e salve: aparece "Não encontrei a pasta". Cole a pasta certa (pode ser com aspas, como o Windows copia) e salve: "Salvo".
3. Abra **Envios**. Em **Pasta do histórico** aparecem o caminho, "Lida às" e uma linha por analista com "Lido (N linhas no mês)" e a hora do arquivo. Analista sem envio no mês aparece como "Nenhum envio neste mês ainda".
4. Se você escolheu sem querer a pasta de um analista só, a página avisa para escolher a pasta de cima.

## Envios do dia
5. Em **Hoje**, cada linha é um envio num horário: horário, envio, analista, canal, situação e "N de M enviados". Envio com problema mostra embaixo cada destinatário e o motivo (por exemplo "falhou, 4 tentativas — WhatsApp: tempo esgotado").
6. Compare com a tela **Hoje** do Pombo de 1 ou 2 analistas: os mesmos envios (os que já tiveram algum registro hoje) e a mesma situação. Diferenças esperadas:
   - um envio que ainda não chegou na hora não aparece no Hub (o Pombo mostra "agendado");
   - logo depois de uma falha, o Hub mostra "↻ tentando de novo" por até 10 minutos, enquanto o Pombo tenta de novo sozinho.
7. Na TV, em até uns 10 segundos, entra a tela **Envios do dia** na rotação. O topo diz "atualizado às HH:MM" e quantos envios estão ✓ enviados, ⚠ com falha e ⏳ em andamento. Cada linha tem a cor e as iniciais do analista, como na faixa de presença.
8. **Na TV não aparecem destinatários, mensagens de erro nem nomes de arquivo**: só horário, envio, analista, canal e situação.
9. Com muitos envios, a tela passa as páginas sozinha, com um fade (o número da página aparece em "Situação").
10. Quando o Pombo de alguém enviar algo novo, em poucos segundos a linha aparece (ou muda de situação) na página e na TV.

## Falhas, com uma cópia da pasta
Para não mexer no histórico de verdade (o Pombo usa ele para saber o que já enviou), faça estes testes numa cópia.

11. Copie a pasta do histórico inteira para `Documentos\teste-pombo` e aponte o Hub para a cópia em **Configurações → Pombo**.
12. Abra o CSV de hoje de um analista da cópia no **Bloco de Notas** (não no Excel), troque `enviado` por `falhou` numa linha de hoje com mais de 10 minutos e salve. Em poucos segundos, a TV mostra **⚠ 1 falha** naquele envio, e a página mostra o destinatário que falhou.
13. No mesmo arquivo, acrescente no fim uma linha só com `lixo` e salve. A página diz "1 linha(s) estragada(s) ignorada(s), como o Pombo faz", e o resto continua igual.
14. Abra esse CSV no **Excel** e deixe aberto. A página mostra em vermelho "Não consegui ler o arquivo (está aberto no Excel?)" (ou continua lendo normalmente, depende de como o Excel abriu), e a TV continua com os envios, com o aviso "Histórico de … travado". Feche o Excel sem salvar: tudo volta ao normal.
15. Renomeie a pasta `teste-pombo` (simula a rede fora do ar). A TV continua mostrando os últimos envios, com o aviso **Pasta do Pombo fora do ar**, e a página mostra o erro em vermelho. Volte o nome: em poucos segundos, o aviso some.
16. Aponte o Hub de volta para a pasta de verdade e apague a cópia.

## Permissões e histórico
17. Como analista, a página Envios abre (com os detalhes das falhas), mas `Configurações` não aparece.
18. No **Histórico**, aparece "mudou a pasta do histórico do Pombo" com quem mudou.
19. Em **Configurações → Pombo**, deixe a pasta em branco e salve: a tela Envios do dia sai da TV e a página Envios diz que a integração está desligada. Volte a pasta.

## Regras de sempre
20. Em **Configurações → Telas da TV**, a tela **Envios do dia** tem o próprio tempo e pode ser desligada.
21. A TV nunca rola, em nenhuma tela, e continua alternando se o servidor cair (aviso "Sem atualização desde HH:MM"). No topo da TV, o nome da tela atual sempre aparece inteiro.
