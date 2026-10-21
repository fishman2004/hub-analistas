# Hub dos Analistas (API) — Versão 1 — Documento de Design

**Data:** 18/10/2026 · **Autor:** Kayo Ibiapino (analista de dados, Polybalas) · **Status:** aguardando aprovação

> Legenda: o que o Kayo decidiu está escrito como decisão. O que foi escolha técnica está marcado com **[escolha técnica]** e pode ser contestado.
> Levantamento completo da equipe e das rotinas (para revisar com os analistas): documento "Hub dos Analistas: equipe e rotinas".

---

## 1. Por que existe

Na sala dos analistas, ninguém sabe de relance quem está onde nem o que cada um está fazendo. Quem chega (o Rafael, um gerente, outro setor) precisa perguntar. As demandas de cada analista ficam espalhadas entre e-mails, mensagens e a cabeça de cada um.

O Hub coloca isso **numa TV da sala**: quem está na sala, em reunião ou fora, e o quadro de demandas da equipe (**A fazer → Fazendo → Concluído hoje**). Cada analista lança e move as próprias demandas pelo computador dele.

Esta é a **versão 1** de um projeto maior, o hub "API (Analistas da Polybalas Integrados)": rotinas com aviso sonoro, prioridades do mês, banco de horas e integração com o Pombo vêm depois (seção 11). Assim como o Pombo, o projeto também é **vitrine**: deve impressionar a empresa e servir de portfólio, com documentação que faz parte do produto.

## 2. Objetivos, não-objetivos e anti-objetivos

### Objetivos (versão 1)
- **TV da sala**, sem ninguém tocar nela: faixa de presença no topo + quadro de demandas em três colunas, atualizados sozinhos, legíveis de longe.
- **App do analista** (no navegador do próprio PC): marcar presença, lançar demandas e movê-las entre as colunas.
- **Histórico** do que foi feito e de quando cada um mudou de status.

### Não-objetivos (ficam para depois, mas o desenho não impede)
- Avisos sonoros e rotinas com horário (15h/17h, comparativo de rotas), prioridades do início do mês.
- Banco de horas.
- Visão especial do Rafael.
- Integração com o Pombo.
- Login com senha, acesso de fora da empresa, celular.

### Anti-objetivos (se acontecer, falhou mesmo "funcionando")
- **A TV ficar ilegível de longe** ou poluída demais para ler de relance.
- **Precisar de alguém mexendo na TV** (fazer login, recarregar, fechar janela).
- **Perder demandas** lançadas.
- **Sensação de vigilância:** a presença é sempre marcada pela própria pessoa. Nada é detectado automaticamente.
- Exigir dinheiro, servidor na nuvem ou trabalho da TI além do mínimo (seção 3).

## 3. Restrições

| Restrição | Consequência |
|---|---|
| Sem dinheiro | Ferramentas gratuitas e de código aberto. |
| **PC reserva da sala** ligado na TV, sempre ligado (decisão do Kayo) | Ele roda o Hub e mostra a tela da TV. |
| Analistas usam os próprios PCs na rede da empresa | Abrem o app pelo navegador no endereço do PC reserva. Não instalam nada. |
| Sem administrador nos PCs | Instalação no PC reserva "só para o usuário", como no Pombo. **Risco:** o Firewall do Windows pode exigir admin para aceitar conexões de outros PCs (seção 10). |
| Desenvolvimento no PC pessoal, execução na empresa | Repositório no GitHub com dados fictícios; dados reais só no PC reserva. |
| O Kayo está aprendendo | Mesmas tecnologias do Pombo; código simples e em etapas. |

## 4. Como funciona

```
 PCs dos analistas (navegador)                   PC reserva da sala (sempre ligado)
 ┌───────────────────────────┐                   ┌────────────────────────────────────────┐
 │ App do analista           │   rede da empresa │  Servidor do Hub (Python)              │
 │ - marcar presença         │ ────────────────► │   - guarda tudo num banco SQLite       │
 │ - lançar / mover demandas │                   │   - serve o app e a tela da TV         │
 └───────────────────────────┘                   │                                        │
                                                 │  Navegador em tela cheia ──► TV        │
                                                 └────────────────────────────────────────┘
```

### 4.1 Escolhas de tecnologia **[escolha técnica]**
- **Python 3.12+ + FastAPI + Jinja2**, como no Pombo. O Kayo já conhece a estrutura e o hub "API" de verdade terá uma API web.
- **SQLite** num arquivo no PC reserva. Diferente do Pombo (CSV), aqui várias pessoas escrevem ao mesmo tempo e só um programa acessa o arquivo, então um banco de verdade é mais simples e seguro. Vem com o Python, sem instalar nada.
- **Atualização ao vivo:** a TV e o app consultam o servidor a cada poucos segundos (*polling*). É mais simples e robusto que WebSocket. Atraso de alguns segundos é aceitável.
- **TV:** Edge ou Chrome em **modo quiosque** (tela cheia, sem barras), aberto sozinho quando o Windows inicia, sem precisar de admin.
- Framework de interface, biblioteca de componentes e estilo visual ficam com o construtor, respeitando: sem etapa de build de JavaScript, legível de longe, em português.

### 4.2 Quem é quem **[escolha técnica]**
- Sem senha: na primeira vez, o analista escolhe o próprio nome numa lista, e o navegador lembra. É uma equipe pequena, numa rede interna, e senha seria atrito sem ganho real na v1.
- **Todos podem lançar e mover qualquer demanda** (ex.: o Kayo lança uma para a Elisa). O histórico registra **quem** fez cada mudança.
- A lista de pessoas, com nome, iniciais e cor, é cadastrada numa tela simples de configuração.

## 5. Comportamento

### 5.1 Demanda (cartão)
Campos (decididos pelo Kayo):
- **Título** (obrigatório)
- **Dono** (obrigatório): o analista responsável
- **Pasta** (opcional): A, B, C, D, E, F, G (Canal Farma)
- **Pedido por** (opcional, texto livre), ex.: "Rafael"
- **Prazo** (opcional, data). Depois do prazo e fora de "Concluído", o cartão aparece **atrasado** na TV.
- **Reservada** (opcional, marcar ou não; decisão do Kayo). Para demandas sensíveis, como comissões, desempenho de vendedores ou pedidos da diretoria. Na TV, o cartão de uma demanda reservada mostra só **"Demanda reservada"**, com a cor e as iniciais do dono. Título, pasta e "pedido por" ficam visíveis apenas no app. O prazo e o "atrasado" continuam aparecendo.

Situação: **A fazer → Fazendo → Concluído**. Pode voltar uma coluna, por exemplo de Fazendo para A fazer. Excluir pede confirmação e fica no histórico.

### 5.2 O que a TV mostra
- **Topo:** data e hora; uma faixa com cada pessoa, sua cor, o status e **desde quando** (ex.: "Em reunião · desde 10:15").
- **Três colunas:** A fazer, Fazendo, Concluído hoje. Cada cartão mostra as iniciais e a cor do dono, o título e, se houver, a pasta, quem pediu e o prazo. Uma demanda **reservada** mostra só "Demanda reservada" (seção 5.1). A TV **nunca recebe** o título dela: o servidor nem envia esse texto para a página da TV.
- **Ordem nas colunas** **[escolha técnica]**: atrasados primeiro, depois por prazo e depois pelos mais antigos. Em "Concluído hoje", os mais recentes primeiro.
- **Excesso de cartões** **[escolha técnica]**: a coluna mostra o que cabe na tela e termina com "+ N demandas". A TV **nunca rola nem diminui a letra** para caber tudo.
- **Concluído hoje** zera à meia-noite. Concluídos antigos saem da TV e ficam no histórico do app.
- **Legibilidade:** projetada para TV Full HD vista a ~4 m: título do cartão ≥ 28 px, nomes da faixa ≥ 32 px, contraste alto. O tema escuro é o padrão da TV **[escolha técnica]**.
- **Sem conexão:** se o servidor parar, a TV mantém a última tela e mostra um aviso discreto "sem atualização desde HH:MM". Ela volta sozinha quando o servidor voltar.

### 5.3 Presença
- Status (decididos pelo Kayo): **Na sala**, **Em reunião**, **Pausa** (banheiro, café), **Fora da empresa**.
- Marcada **só pela própria pessoa** no app, com um toque.
- **Todo dia, à meia-noite, todos voltam para "Fora da empresa"** **[escolha técnica]**. Assim, quem não veio não aparece "Na sala" por engano. Ao chegar, a pessoa marca "Na sala".

### 5.4 App do analista
- **Minha presença:** quatro botões grandes.
- **Quadro:** as mesmas três colunas da TV. Cada cartão pode ser movido por botões ("Começar", "Concluir", "Voltar"). Arrastar e soltar fica para depois, se a equipe pedir.
- **Filtro "Só as minhas"**, ligado por padrão.
- **Nova demanda:** formulário com os cinco campos.
- **Histórico:** concluídos e mudanças, filtráveis por pessoa e por período.

### 5.5 Histórico
Toda mudança é registrada: demanda criada, editada, movida, concluída, excluída e mudança de presença, com **quem**, **quando** e **o quê**. Ele serve à tela de histórico, às fases futuras (banco de horas, visão do Rafael) e a eventuais consultas sobre "quem mexeu nisso".

## 6. Dados

| O quê | Onde | Vai para o GitHub? |
|---|---|---|
| Código, documentação, testes | pasta do projeto | Sim |
| Banco (pessoas, demandas, presença, histórico) | PC reserva, pasta de dados do usuário (`%LOCALAPPDATA%\Hub`) | Não |
| Cópia de segurança diária do banco **[escolha técnica]** | mesma pasta, últimos 14 dias; opcionalmente uma pasta de rede | Não |
| Dados de exemplo (pessoas e demandas fictícias) | `exemplos/` | Sim |

Os nomes reais da equipe ficam só no banco do PC reserva, nunca no repositório.

## 7. Instalação (PC reserva)

1. Python "só para mim" (igual ao Pombo).
2. Baixar o projeto, rodar `instalar.bat`.
3. `iniciar.bat` sobe o servidor e abre a TV em modo quiosque.
4. Configuração: cadastrar as pessoas (nome, iniciais, cor) e marcar **"Abrir com o Windows"**.
5. Nos PCs dos analistas: salvar o endereço do Hub (ex.: `http://NOME-DO-PC-RESERVA:8800`) nos favoritos.

## 8. Documentação (parte do produto)

Como no Pombo: README com prints e GIF da TV; instalação; arquitetura; segurança e dados (presença marcada pela própria pessoa, nada automático); limitações; roadmap (seção 11). O levantamento da equipe continua no documento separado.

## 9. Testes
- Testes automáticos (pytest) para regras: mover entre colunas, "Concluído hoje" zerando à meia-noite, ordem dos cartões (atrasados primeiro), presença voltando a "Fora" à meia-noite, histórico registrando quem fez, validação do formulário e **demanda reservada sem título, pasta nem "pedido por" em nenhuma resposta da TV**.
- Teste visual da TV em 1920×1080 (print), conferindo a legibilidade e o "+ N".
- Teste de ponta a ponta na empresa: dois PCs alterando ao mesmo tempo e a TV refletindo em poucos segundos.

## 10. Riscos

| Risco | Redução |
|---|---|
| **Firewall do Windows bloqueia conexões de outros PCs ao PC reserva** sem admin | **Etapa 1 da construção:** teste de 5 minutos na empresa (um servidor mínimo no PC reserva, aberto de outro PC). Se bloquear: (a) pedir à TI **uma única regra** liberando a porta do Hub; (b) plano B sem servidor, com uma pasta compartilhada como no Pombo (mais trabalho, decidido só se necessário). |
| PC reserva desligado ou reiniciado | Abre com o Windows; impede suspensão; a TV volta sozinha. |
| Queda de energia corrompe o banco | SQLite em modo WAL + cópia diária. |
| Equipe não adota (esquece de marcar) | Status com um toque; app leve; reset diário para "Fora", o que incentiva marcar "Na sala" ao chegar. |
| O nome "API" confunde com o termo técnico | Usar "Hub dos Analistas" na interface; "API" como nome do projeto. A decisão final é do Kayo. |

## 11. Roadmap (aparece na documentação)

1. **v1:** quadro de demandas + presença na TV (este documento).
2. **Rotinas com horário e aviso sonoro na TV:** transferências do Reppos às 15h e 17h (pastas B, C e F, com liberação da Elisa depois das três), positivações diárias e comparativo de rotas às terças e quintas. Rotinas viram demandas criadas sozinhas.
3. **Prioridades do início do mês** (meta, fechamentos, novos acompanhamentos por pasta, apuração de campanhas).
4. **Banco de horas:** planilha base + lançamento manual de entrada e saída do dia anterior; visível só para o próprio analista e o Rafael, nunca na TV.
5. **Visão do Rafael.**
6. **Integração com o Pombo:** envios do dia lidos do histórico CSV na pasta de rede.

## 12. Fica a critério do construtor
- Estrutura de pastas, nomes de rotas e tabelas, intervalo exato do *polling* (entre 3 e 10 s).
- Visual, dentro da seção 5.2 e do rascunho escolhido (opção B), com cores distintas e legíveis para cada pessoa.
- Como abrir o navegador em modo quiosque com o Windows, sem admin.
- Porta do servidor (sugestão: 8800, diferente do Pombo, 8765).
