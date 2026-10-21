# Roteiro de teste · Fase 2 · Papéis e PIN

Leva uns 15 minutos. **Faça logo depois de atualizar**, antes da equipe abrir o Hub, porque quem criar o primeiro PIN vira administrador.

## Antes
1. No PC da sala: extraia o ZIP por cima da pasta do Hub, rode `instalar.bat` e depois `iniciar.bat`.
2. Confira que apareceu um arquivo `antes-da-v1-....db` em `%LOCALAPPDATA%\Hub\copias`. É a cópia do banco de antes da atualização.

## Você (Kayo) entra primeiro
3. No seu PC, abra o Hub. Agora o app pede para escolher o nome. Clique no seu.
4. Aparece **Primeiro acesso: crie o seu PIN** e o aviso de que quem criar o primeiro PIN vira administrador. Crie o PIN e entre.
5. O quadro, as demandas e o histórico de antes continuam lá.
6. No menu aparece **Pessoas**. Abra: cada pessoa tem o papel (Analista ou Gestor), a caixa **Administrador** e "Ainda sem PIN" para quem não entrou.
7. No gestor, escolha **Gestor**, marque **Administrador** e clique em **Salvar acesso**.

## A equipe
8. Peça para cada pessoa abrir o Hub no próprio PC **hoje** e criar o PIN.
9. No PC de um analista: o menu **não** tem Pessoas, e abrir `/pessoas` direto mostra "Sem permissão".
10. Clique em **Sair** e tente entrar com um PIN errado 5 vezes. Na quinta, o nome fica bloqueado por 5 minutos (nem o PIN certo entra). Depois de 5 minutos, o PIN certo entra.
11. Clicando no próprio nome, no canto direito, dá para **trocar o PIN**.

## Esqueceu o PIN
12. Como administrador, em **Pessoas**, clique em **Redefinir PIN** de alguém. Essa pessoa sai do Hub e cria um PIN novo no próximo acesso.

## Proteções
13. Tente tirar a caixa **Administrador** de você mesmo enquanto for o único administrador: o Hub recusa. Com o gestor também administrador, funciona.
14. **A TV continua igual,** sem pedir PIN.
15. No **Histórico** aparecem as entradas, a criação de PINs e as mudanças de papel, com quem fez.

No dia seguinte, o app pede o PIN de novo: a entrada vale só até a meia-noite.
