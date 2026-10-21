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
        D --> DB[(SQLite · hub/db.py<br>pessoas, demandas, presença, histórico)]
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
  - "atrasada" = prazo antes de hoje e fora de Concluído (`demands.is_overdue`).
  Se o PC passou a noite desligado, nada fica para trás.
- **Demanda reservada é mascarada no servidor** (`demands.tv_card`): a resposta da TV não contém o título, a pasta nem quem pediu. Não é só a tela escondendo.
- **Histórico de tudo** (`db.log_event`): cada mudança grava quem, quando e o quê. Ele alimenta a tela de histórico e as próximas versões (banco de horas, visão do gerente).
- **SQLite em modo WAL**, uma conexão por operação, com espera de até 5 s: dois PCs mexendo no mesmo cartão ao mesmo tempo não dão erro, e vale a última mudança (as duas ficam no histórico).
- **A TV nunca rola:** `tv.js` acrescenta cartões enquanto cabem e troca o que sobra por "+ N demandas". O tamanho das letras acompanha a largura da tela (`html { font-size: 100vw / 120 }`), então funciona em qualquer TV.
- **Tema do app no navegador, não no servidor** (`static/tema.js`): cada pessoa escolhe automático, claro ou escuro, e a escolha fica no `localStorage` daquele navegador. As cores são variáveis CSS em `app.css`; `data-tema` no `<html>` força claro ou escuro, e sem ele vale o modo do Windows. O script carrega no `<head>` para a página já nascer no tema certo. A TV usa `tv.css` e não carrega esse script, então não muda com a escolha de ninguém.
- **Entrar com nome + PIN** (`hub/access.py`, fase 2): o PIN é guardado só como resumo PBKDF2 com sal próprio. Ao acertar, o servidor cria uma sessão (tabela `sessions`, com o resumo do token) que acaba à meia-noite; o cookie `hub_sessao` só carrega o token. Cinco PINs errados seguidos bloqueiam aquele nome por 5 minutos. A TV e o `/api/tv` continuam sem login e não leem nada disso.
- **Papéis:** cada pessoa é `analista` ou `gestor` (coluna `role`) e pode ter a marcação `is_admin`. Só administrador abre Pessoas, muda papéis e redefine PIN. Sempre sobra pelo menos um administrador; sem nenhum (instalação nova ou logo depois de atualizar da v1), quem cria o primeiro PIN vira administrador.
- **Migrações automáticas** (`db.MIGRATIONS`): cada mudança no banco depois da v1 tem um número, guardado no `PRAGMA user_version`. Ao iniciar, o Hub copia o banco para `copias/antes-da-vN-....db` e aplica as que faltam, cada uma inteira ou nada. Elas só acrescentam colunas e tabelas.
- Formulários vindos de outro site são recusados (mesma origem).

## Onde está cada coisa

| Arquivo | Responsabilidade |
|---|---|
| `hub/__main__.py` | Sobe o servidor (porta 8800, uma cópia só), cópia diária, abre a TV em quiosque |
| `hub/db.py` | Banco, esquema, migrações e histórico |
| `hub/access.py` | PIN, bloqueio, sessões do dia, papéis e administradores |
| `hub/people.py` | Equipe: nome, iniciais, cor |
| `hub/demands.py` | Demandas, quadro, ordem, atrasadas, cartão da TV |
| `hub/presence.py` | Presença e a virada do dia |
| `hub/backup.py` | Cópia de segurança diária (14 dias) |
| `hub/winsys.py` | Abrir com o Windows, não dormir, TV em tela cheia |
| `hub/web/` | Rotas, páginas, o JavaScript da TV e o do tema do app (`static/tema.js`) |
| `tools/` | Teste de rede e dados de demonstração |
| `tests/` | Testes automáticos (pytest) |
