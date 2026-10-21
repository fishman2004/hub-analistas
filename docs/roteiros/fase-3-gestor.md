# Roteiro de teste · Fase 3 · Visão do gestor

Leva uns 10 minutos. Precisa da fase 2 já em uso (cada um com PIN, o gestor marcado como Gestor).

## Visão do gestor
1. Entre como **gestor**. No menu aparece **Gestor**. Abra.
2. No topo, os números do dia: quantos estão na sala, fazendo, a fazer, concluídas hoje e atrasadas (em vermelho quando houver).
3. Em **A equipe hoje**, cada pessoa com onde está e desde quando, e as contagens. Clique num número: a lista de baixo filtra aquela pessoa e coluna.
4. Em **Todas as demandas**, teste os filtros: uma pessoa, a coluna "Fazendo", o prazo "Vence hoje" e "Só atrasadas". **Limpar** volta tudo.
5. **Histórico completo** abre o histórico desde o primeiro registro.
6. Entre como **administrador** (você): o menu também tem **Gestor**.
7. Entre como um **analista**: o menu não tem Gestor, e abrir `/gestor` direto mostra "Sem permissão".

## Demanda reservada
8. Como analista A, crie uma demanda **reservada** para o analista B.
9. Como analista **C**, abra o quadro em **Ver todas**: ela aparece como "Demanda reservada", sem título e sem botões. No **Histórico**, também aparece como "Demanda reservada".
10. Como **A** (quem criou), **B** (o dono), o **gestor** e um **administrador**: o título aparece no quadro, no histórico e na visão do gestor (com a etiqueta "Reservada").
11. Na TV, nada muda: continua "Demanda reservada" para todos.
12. Demandas reservadas criadas **antes** desta atualização: quem criou continua vendo, porque o Hub busca isso no histórico.
