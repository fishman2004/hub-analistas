# Roadmap

O Hub é a versão 1 do projeto **API (Analistas da Polybalas Integrados)**. A v1 está em produção desde 20/10/2026. A partir dela, o Hub cresce **uma fase por vez**, cada uma num branch próprio, com testes, documentação e um roteiro de teste manual na empresa.

```mermaid
flowchart LR
    V1[v1 · Quadro e presença<br><b>em produção</b>] --> F1[1 · Tema claro/escuro]
    F1 --> F2[2 · Papéis e PIN]
    F2 --> F3[3 · Visão do gestor]
    F2 --> F4[4 · TV em rotação]
    F4 --> F5[5 · Painéis de dados]
    F2 --> F6[6 · Banco de horas]
    F4 --> F7[7 · Rotinas com aviso]
    F4 --> F8[8 · Prioridades do mês]
    F5 --> F9[9 · Pombo na TV]
```

| Fase | Entrega | Estado |
|---|---|---|
| v1 | Quadro de demandas (A fazer, Fazendo, Concluído hoje), presença e demanda reservada | Em produção |
| 1 | **Tema claro/escuro** no app dos analistas (claro, escuro ou automático, salvo no navegador de cada um). A TV mantém o tema próprio. | Pronto ([roteiro de teste](roteiros/fase-1-tema.md)) |
| 2 | **Papéis e PIN:** analista e gestor, mais a marcação de administrador; entrar com nome + PIN de 4 a 6 dígitos. A TV continua sem login. | Pronto ([roteiro de teste](roteiros/fase-2-pin.md)) |
| 3 | **Visão do gestor:** todas as demandas com filtros, resumo do dia e histórico completo. Abre para o gestor e os administradores. O título de demanda reservada fica só com o gestor, os administradores, o dono e quem criou. | Pronto ([roteiro de teste](roteiros/fase-3-gestor.md)) |
| 4 | **TV em rotação:** a TV alterna entre telas (o Quadro sempre está nela), com tempos configuráveis e telas "plugáveis". Junto vem a **paginação das colunas** (ideia do Kayo): quando uma coluna tem mais demandas do que cabem, ela passa as páginas sozinha com um fade, de tempos em tempos, em vez de esconder o resto em "+ N demandas". A TV continua sem rolar. Primeira tela extra: **Prazos da semana**. | Pronto ([roteiro de teste](roteiros/fase-4-tv.md)) |
| 5 | **Painéis de dados na TV:** as planilhas do time (metas por pasta, fornecedores, produtos foco e a 8081 de vendas) ficam numa pasta só delas e o Hub calcula meta x realizado por pasta. Quatro telas: **Metas do mês**, **Metas do dia**, **Produtos foco** e **Fornecedores das pastas**, só com gráficos e porcentagens (regra do gestor). | Pronto ([roteiro de teste](roteiros/fase-5-paineis.md), [regras](paineis.md)) |
| 6 | **Banco de horas:** o gestor importa o saldo atual que o RH envia e cada analista lança a entrada e a saída do dia (pelo comprovante do ponto) para saber se está com horas extras ou negativas. Só a própria pessoa e o gestor veem; nunca na TV. Não substitui o RH. | Pronto ([roteiro de teste](roteiros/fase-6-banco-de-horas.md)) |
| 7 | **Rotinas com horário e aviso sonoro:** página **Rotinas** (nome, dias, horário, prazo, responsável, pastas e "liberada depois de"). No horário, o cartão aparece sozinho em A fazer do responsável (por cálculo, sem tarefa agendada) e a TV toca um aviso; depois do prazo, fica atrasado. Rotinas sugeridas, as do Kayo: PHD, transferência de pedidos às 14:50 e 16:50 (pastas B, C e F marcam a sua), atualização de positivações no grupo de gestão comercial depois de cada transferência e comparativo de rotas às terças e quintas. | Pronto ([roteiro de teste](roteiros/fase-7-rotinas.md); padrões [em aberto](decisoes.md#em-aberto-o-kayo-confirma)) |
| 8 | **Prioridades do início do mês:** a lista do mês (lançar a meta, confirmar a meta com o gerente, entregar as comissões até o dia 10 e as campanhas até o dia 15, mais o que a equipe acrescentar, com pasta e prazo opcionais), numa tela da rotação que só sai quando tudo estiver feito. Qualquer pessoa marca como feita e fica guardado quem fez; passou do prazo, aparece como atrasada. | Pronto ([roteiro de teste](roteiros/fase-8-prioridades.md), [decisões](decisoes.md#prioridades-do-mês-fase-8)) |
| 9 | **Integração com o [Pombo](https://github.com/fishman2004/pombo):** os envios do dia como uma tela da rotação, lidos do histórico CSV que o Pombo grava na pasta de rede. | A fazer |

## Regras que valem para todas as fases

- Nada que exija administrador do Windows; atualizar continua sendo extrair o ZIP por cima e rodar `instalar.bat`.
- Mudança no banco é sempre uma migração automática, com cópia antes, que nunca apaga dados.
- A TV nunca rola, mantém a última tela se o servidor cair, não depende de internet e nunca mostra o título de uma demanda reservada.
