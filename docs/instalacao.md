# Instalação no PC reserva

## 1. Python "só para mim"

1. Baixe o Python 3.12 ou mais novo em [python.org/downloads](https://www.python.org/downloads/).
2. No instalador: **desmarque** "Use admin privileges when installing py.exe", **marque** "Add python.exe to PATH" e clique em **Install Now**.

## 2. Baixar e instalar

1. No GitHub: **Code › Download ZIP**. Extraia numa pasta fixa, por exemplo `Documentos\Hub`.
2. Dois cliques em **`instalar.bat`**: cria o ambiente, baixa as bibliotecas e faz o Hub **abrir junto com o Windows**.

## 3. Abrir

Dois cliques em **`iniciar.bat`**. O servidor sobe sem janela, e a TV abre no Edge em **tela cheia (modo quiosque)**.

- Para sair do modo quiosque: **Alt+F4**.
- Abrir de novo não cria outra cópia: só reabre a TV.
- A TV toca um aviso no horário de cada rotina. Se ela não tocar, libere o som do site uma vez no Edge ([passo a passo](roteiros/fase-7-rotinas.md#som-na-tv)) e confira se o som do PC sai pela TV.

## 4. Primeira configuração

1. De qualquer PC da sala, abra `http://NOME-DO-PC-RESERVA:8800`. O nome do PC aparece no teste de rede ([primeiro-uso.md](primeiro-uso.md)).
2. Em **Pessoas**, cadastre a equipe. Iniciais e cor são escolhidas sozinhas e podem ser trocadas.
3. Cada analista abre o mesmo endereço no próprio PC, escolhe o próprio nome, cria o PIN e salva o endereço nos favoritos.

## Desligar o "abrir com o Windows"

Apague o arquivo `Hub.cmd` em `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

## Onde ficam os dados

`%LOCALAPPDATA%\Hub`: `hub.db` (o banco), `copias\` (as cópias diárias dos últimos 14 dias) e `hub.log`.
Para restaurar uma cópia:

1. Feche o Hub. Ele roda sem janela: no **Gerenciador de Tarefas**, encerre o processo **pythonw.exe** do Hub.
2. Em `%LOCALAPPDATA%\Hub`, **apague `hub.db-wal` e `hub.db-shm`**, se existirem. Sem isso, o SQLite reaplica alterações antigas por cima da cópia restaurada e pode estragar o banco.
3. Copie `copias\hub-AAAA-MM-DD.db` por cima de `hub.db` e abra o Hub de novo (`iniciar.bat`).

## Atualizar para uma versão nova

Extraia o ZIP novo por cima da pasta e rode `instalar.bat` de novo. Os dados ficam em `%LOCALAPPDATA%\Hub` e não são apagados.
