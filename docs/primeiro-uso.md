# Primeiro uso na empresa (roteiro)

## 1. Teste de rede (5 minutos, antes de tudo)

A pergunta é: outros computadores conseguem abrir uma página servida pelo PC reserva? O Firewall do Windows pode bloquear.

1. No PC reserva, com o Python instalado, abra o Prompt de Comando na pasta do Hub e rode:
   ```bat
   python tools\net_test.py
   ```
2. Ele mostra um endereço, por exemplo `http://PC-SALA:8800`. **Anote o nome do PC.**
3. Se o Windows mostrar um aviso do **Firewall**, anote o que ele pede. Se pedir senha de administrador, você não consegue liberar sozinho.
4. Em **outro PC**, abra o endereço. Esperado: "Hub: conexão OK".

| Resultado | O que fazer |
|---|---|
| Abriu | Siga para a instalação. |
| Não abriu, e o firewall pediu admin | Peça à TI **uma regra de entrada para a porta TCP 8800** no PC reserva. É a única coisa que o Hub precisa da TI. |
| A TI não libera | Pare aqui e reveja a arquitetura: o plano B é uma pasta compartilhada (ver [decisoes.md](decisoes.md)). |

## 2. Instalação

Siga [instalacao.md](instalacao.md) e cadastre a equipe em **Pessoas**.

## 3. Teste com a equipe

1. Dois analistas, em PCs diferentes, lançam e movem demandas ao mesmo tempo. A TV mostra em até 5 segundos.
2. Lance uma demanda **reservada** e confira que a TV mostra só "Demanda reservada".
3. Reinicie o PC reserva. O Hub e a TV voltam sozinhos.

## 4. Apresentar ao gestor

O README e a TV funcionando são a apresentação.

## Zerar o histórico dos testes (antes do uso oficial)

Em **Configurações › Zerar o histórico** (só administrador): escolha o que apagar, digite o seu PIN e a palavra **APAGAR**. Apaga o que aconteceu nos testes (demandas, histórico, marcas das rotinas do mês e da trilha, prioridades, compromissos e ausências, entradas do banco de horas e, se marcar, as notas pessoais) e mantém pessoas, PINs, rotinas, trilhas, modos da TV, feriados e configurações. Antes, o Hub guarda uma cópia inteira do banco em `%LOCALAPPDATA%\Hub\copias\antes-de-zerar-AAAA-MM-DD-HHMM.db`; os arquivos dos anexos apagados vão para a pasta `Anexos apagados AAAA-MM-DD HHMM`.
