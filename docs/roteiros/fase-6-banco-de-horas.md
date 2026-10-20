# Roteiro de teste · Fase 6 · Banco de horas

Leva uns 15 minutos. Precisa de duas pessoas (ou dois navegadores): o **gestor** e um **analista**.

## Antes de começar
- Confira em **Pessoas** que o gestor está com o papel **Gestor** (só ele vê o banco de horas da equipe).
- Tenha a planilha do saldo que o RH enviou, com as colunas `NOME` e `SALDO` (ex.: `12:30` ou `-03:15`) e, se tiver, `DATA` (até quando o saldo vale). O nome tem de ser igual ao cadastro do Hub.

## Gestor: saldo do RH
1. Entre como gestor e abra **Banco de horas**. Clique em **Ver o banco de horas da equipe**. A tabela mostra todo mundo, com "não lançado" no saldo base.
2. Em **Importar a planilha base**, envie a planilha do RH. Aparece "Saldo base importado de N pessoas". Se algum nome não bateu, ele aparece num aviso amarelo: corrija o nome na planilha (ou no cadastro) e importe de novo.
3. Confira 2 ou 3 saldos com a planilha. Sem a coluna `DATA`, o saldo vale até ontem.
4. Em **Ajustar o saldo base de uma pessoa**, mude o saldo de alguém para `-01:30` e salve. A tabela mostra o novo saldo base.
5. Em **Jornada**, confira `10:00` de segunda a sexta (das 8h às 18h, com o almoço dentro) e `00:00` no sábado.

## Analista: lançar o dia
6. Entre como analista e abra **Banco de horas**. Aparecem o saldo, o saldo base (do RH) e os dias sem lançamento.
7. Lance o dia de ontem com a entrada e a saída do comprovante do ponto (ex.: `07:52` e `18:10`). O dia entra na lista com **Horas no dia** `10:18` e **Diferença** `+00:18`, e o saldo muda na hora.
8. Tente lançar o mesmo dia de novo: aparece "já foi lançado. Para mudar, use Corrigir na lista."
9. Clique em **Corrigir** no dia e mude a saída. A diferença e o saldo acompanham.
10. Tente lançar um dia antes da data do saldo do RH: aparece "Esse dia já está no saldo base".
11. Tente uma saída antes da entrada: aparece "A saída tem de ser depois da entrada."
12. Em "Faltam lançar", clique num dia: o formulário já vem com ele.

## Quem vê
13. Ainda como analista, tente abrir `/horas/equipe` pelo endereço: aparece "O banco de horas da equipe é só do gestor."
14. Abra o **Histórico**: o analista vê só os próprios lançamentos e correções; outro analista não vê nada do banco de horas de ninguém.
15. Como gestor, clique no nome do analista na tabela da equipe: aparecem os dias lançados dele (sem botões de corrigir). No **Histórico**, o gestor vê a correção feita no passo 9, com o antes e o depois.
16. **A TV não mostra nada de banco de horas**, em nenhuma tela.

## Exportar
17. Na página da equipe, baixe **Saldos · Excel** e **Dias lançados** (Excel ou CSV). Os arquivos abrem no Excel com nome, saldo, saldo base e os dias.
