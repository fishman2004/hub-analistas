# Arquitetura

O Hub é **um servidor Python** no PC reserva da sala. Ele guarda tudo num SQLite e serve duas faces:

- **TV** (`/tv`): uma página que busca `/api/tv` a cada 5 segundos e desenha a tela com JavaScript puro.
- **App do analista** (`/`): páginas HTML com formulários, usadas pelo navegador de cada PC.

```mermaid
flowchart TB
    subgraph PC reserva
        W[hub/web/app.py<br>rotas da TV e do app] --> D[hub/demands.py<br>quadro e regras]
        W --> P[hub/presence.py<br>presença]
        W --> PE[hub/people.py<br>equipe]
        D --> R[hub/rotinas.py<br>rotinas e horários]
        D --> DB[(SQLite · hub/db.py<br>pessoas, demandas, presença, histórico)]
        R --> DB
        P --> DB
        PE --> DB
        B[hub/backup.py<br>cópia diária] --> DB
    end
    TV[TV · tv.js] -- GET /api/tv a cada 5 s --> W
    APP[App · navegador dos analistas] -- formulários --> W
```

## Decisões que moldam o código

- **Regras do dia calculadas, não agendadas.** Nenhuma tarefa roda à meia-noite:
  - "Concluído hoje" = concluídas com `done_at` na data de hoje;
  - presença marcada antes de hoje vale como "Fora da empresa" desde 00:00 (`presence.effective`);
  - "atrasada" = prazo antes de hoje e fora de Concluído (`demands.is_overdue`);
  - o cartão de cada rotina aparece quando chega o horário dela (`demands.board`, fase 7).
  Se o PC passou a noite desligado, nada fica para trás.
- **Demanda reservada é mascarada no servidor** (`demands.tv_card`): a resposta da TV não contém o título, a pasta nem quem pediu. Não é só a tela escondendo. No app, `demands.can_see` decide quem vê o título (o dono, quem criou, o gestor e os administradores); para os demais, o quadro, o histórico e as rotas da demanda mascaram ou recusam (403).
- **Histórico de tudo** (`db.log_event`): cada mudança grava quem, quando e o quê. Ele alimenta a tela de histórico e a visão do gestor e as próximas versões (banco de horas).
- **SQLite em modo WAL**, uma conexão por operação, com espera de até 5 s: dois PCs mexendo no mesmo cartão ao mesmo tempo não dão erro, e vale a última mudança (as duas ficam no histórico).
- **A TV nunca rola:** cada coluna do Quadro é dividida em páginas que cabem (medindo de verdade no navegador) e passa as páginas com um fade no tempo configurado. Nas outras telas, o que não cabe vira "+ N demandas". O tamanho das letras acompanha a largura da tela (`html { font-size: 100vw / 120 }`), então funciona em qualquer TV.
- **TV em rotação, com telas registráveis** (fase 4): `hub/telas.py` lista as telas (`SCREENS`), cada uma com um tempo padrão e uma função que monta os dados dela, ou devolve `None` quando não há o que mostrar (aí ela sai da rotação). O `/api/tv` manda as telas que entram agora, com o tempo de cada uma. No navegador, `tv.js` cuida do que é comum (busca a cada 5 s, presença, relógio, aviso de atrasadas, "sem atualização", rotação e indicador) e cada tela é um arquivo em `static/tv-telas/` que chama `HubTV.registrar(id, { desenhar, aoMostrar })`. As telas ficam empilhadas na mesma área; só a ativa aparece, com um fade, sem recarregar a página.

  **Para plugar uma tela nova:** (1) escreva a função de dados e registre em `SCREENS`; (2) crie `static/tv-telas/<id>.js`; (3) acrescente `<section class="tela" data-tela="<id>">` e o `<script>` em `tv.html`. O teste `test_every_registered_screen_has_a_drawing` confere que as três partes existem. Os tempos e o liga/desliga aparecem sozinhos em Configurações.
- **Rotinas calculadas** (fase 7, `hub/rotinas.py` e `demands.board`): o cadastro fica na tabela `routines` (dias da semana, horário, prazo, responsável, pastas e as rotinas que ela espera). A cada montagem do quadro, `demands.board` junta às demandas um cartão para cada rotina que vale hoje e cujo horário já chegou (`id` vazio, endereço `rotina-<número>-<dia>`), com o horário, o prazo, as pastas marcadas e a espera (`RoutineInfo`). Na primeira ação sobre o cartão (mover, editar, excluir ou marcar pasta), `demands._resolve` cria a demanda de verdade, com `routine_id` e `routine_day` (índice único: uma por rotina e por dia), dentro da mesma gravação da ação. As pastas marcadas ficam em `routine_folders`, com quem marcou. `move_demand` recusa começar ou concluir uma rotina que ainda espera outra, e concluir à mão com pasta faltando; `toggle_folder` leva o cartão para Fazendo e Concluído hoje sozinho. Passou do prazo de hoje, o cartão conta como atrasado (`is_overdue`).
- **Aviso sonoro na TV:** o `/api/tv` manda em `avisos` as rotinas de hoje (`rotinas.tv_alerts`: chave `rotina-<número>-<dia>`, horário, nome e prazo). O `tv.js` confere a cada segundo, com o relógio do servidor; quando um horário chega, toca `static/aviso.wav` uma vez e mostra a faixa `#aviso-rotina` por 20 s por cima de qualquer tela. As chaves já tocadas ficam na memória e no `localStorage` (com try/catch): recarregar não repete, e um horário que passou há mais de 10 min não toca. O Edge abre com `--autoplay-policy=no-user-gesture-required` (`winsys.open_tv`) para o som tocar sem clique.
- **Tema do app no navegador, não no servidor** (`static/tema.js`): cada pessoa escolhe automático, claro ou escuro, e a escolha fica no `localStorage` daquele navegador. As cores são variáveis CSS em `app.css`; `data-tema` no `<html>` força claro ou escuro, e sem ele vale o modo do Windows. O script carrega no `<head>` para a página já nascer no tema certo. A TV usa `tv.css` e não carrega esse script, então não muda com a escolha de ninguém.
- **Entrar com nome + PIN** (`hub/access.py`, fase 2): o PIN é guardado só como resumo PBKDF2 com sal próprio. Ao acertar, o servidor cria uma sessão (tabela `sessions`, com o resumo do token) que acaba à meia-noite; o cookie `hub_sessao` só carrega o token. Cinco PINs errados seguidos bloqueiam aquele nome por 5 minutos. A TV e o `/api/tv` continuam sem login e não leem nada disso.
- **Papéis:** cada pessoa é `analista` ou `gestor` (coluna `role`) e pode ter a marcação `is_admin`. Só administrador abre Pessoas, muda papéis e redefine PIN. Sempre sobra pelo menos um administrador; sem nenhum (instalação nova ou logo depois de atualizar da v1), quem cria o primeiro PIN vira administrador.
- **Migrações automáticas** (`db.MIGRATIONS`): cada mudança no banco depois da v1 tem um número, guardado no `PRAGMA user_version`. Ao iniciar, o Hub copia o banco para `copias/antes-da-vN-....db` e aplica as que faltam, cada uma inteira ou nada. Elas só acrescentam colunas e tabelas.
- **Painéis de dados** (fase 5, `hub/paineis.py` e `hub/planilhas.py`): o Hub lê as planilhas da pasta dos painéis (CSV ou XLSX), calcula meta x realizado por pasta e entrega à TV **só porcentagens**. Cada arquivo é relido apenas quando muda (data e tamanho), numa linha separada, para a TV nunca esperar a leitura da 8081. Arquivo ausente ou quebrado tira da rotação só as telas que dependem dele. Contratos e regras em [paineis.md](paineis.md).
- **Banco de horas** (fase 6, `hub/horas.py`): tabelas `hours_balance` (saldo base de cada pessoa, até uma data) e `hours_entries` (entrada e saída de cada dia, um dia por pessoa). O saldo é calculado, não guardado: saldo base + (horas do dia − jornada) de cada dia lançado depois da data do saldo base. Só a própria pessoa e o gestor veem (`horas.can_see`); as linhas do histórico sobre horas seguem a mesma regra. A TV não importa o módulo, e um teste confere que o `/api/tv` não executa nenhum comando nessas tabelas.
- Formulários vindos de outro site são recusados (mesma origem).

## Onde está cada coisa

| Arquivo | Responsabilidade |
|---|---|
| `hub/__main__.py` | Sobe o servidor (porta 8800, uma cópia só), cópia diária, abre a TV em quiosque |
| `hub/db.py` | Banco, esquema, migrações e histórico |
| `hub/access.py` | PIN, bloqueio, sessões do dia, papéis e administradores |
| `hub/gestor.py` | Visão do gestor: resumo do dia por pessoa e filtros das demandas |
| `hub/telas.py` | Telas da TV, rotação e as configurações (tempos) |
| `hub/paineis.py` | Painéis de dados: pasta, os arquivos, cálculo das metas, cache e o que vai para a TV |
| `hub/horas.py` | Banco de horas: saldo base, lançamentos, saldo calculado, importação da planilha do RH e exportação |
| `hub/planilhas.py` | Leitura de CSV e XLSX (cabeçalho sem acento, número e data em formato brasileiro) |
| `hub/people.py` | Equipe: nome, iniciais, cor |
| `hub/demands.py` | Demandas, quadro, ordem, atrasadas, cartão da TV, e o cartão de cada rotina (calculado, vira demanda na primeira ação, pastas e espera) |
| `hub/rotinas.py` | Cadastro das rotinas, quando cada uma vale, as rotinas sugeridas e os avisos da TV |
| `hub/presence.py` | Presença e a virada do dia |
| `hub/backup.py` | Cópia de segurança diária (14 dias) |
| `hub/winsys.py` | Abrir com o Windows, não dormir, TV em tela cheia |
| `hub/web/` | Rotas, páginas, o JavaScript da TV (`static/tv.js` e uma tela por arquivo em `static/tv-telas/`) e o do tema do app (`static/tema.js`) |
| `tools/` | Teste de rede, dados de demonstração, as planilhas de exemplo dos painéis (`tools/exemplos/`, geradas por `tools/gerar_exemplos.py`) e o gerador do som do aviso (`tools/gerar_som.py`, que grava `hub/web/static/aviso.wav`) |
| `tests/` | Testes automáticos (pytest) |
