# Segurança e dados

## Quem vê o quê

| O quê | TV da sala | App (analistas) |
|---|---|---|
| Presença e "desde quando" | Sim | Sim |
| Demandas normais (título, pasta, quem pediu, prazo) | Sim | Sim |
| Demanda **reservada** | Só "Demanda reservada", a cor e as iniciais do dono e o prazo | Tudo para o dono, quem criou, o gestor e os administradores. Os demais veem como na TV e não abrem, movem nem excluem |
| Visão do gestor (resumo do dia e todas as demandas) | Não | Só o gestor e os administradores |
| Prazos da semana (tela da TV) | Sim, com a reservada mascarada como no Quadro | Não se aplica |
| Painéis de vendas (metas, positivação, produtos foco) | **Só porcentagens e gráficos**, nunca valores, quantidades ou nomes | Página Painéis: só a situação das planilhas (lida, quantas linhas, quando). Enviar planilha: só administradores |
| Histórico | Não | Sim |
| PIN | Não | Ninguém (só um resumo fica guardado) |

Os painéis seguem a regra do gestor: muita gente passa pela sala, então a TV mostra metas só em porcentagem. Isso também é feito **no servidor**: o endereço da TV recebe apenas percentuais e as letras das pastas, e um teste automático confere que nenhum valor, quantidade ou nome das planilhas vai junto.

A demanda reservada é mascarada **no servidor**: a página da TV nunca recebe o título, então nem quem inspecionar a página consegue ver. No app vale o mesmo para quem não pode ver: o quadro, o histórico e a página da demanda chegam sem o título.

## Presença

Marcada **sempre pela própria pessoa**. O Hub não detecta nada sozinho: não olha login, câmera, Wi-Fi nem atividade do computador. À meia-noite todos voltam para "Fora da empresa", para ninguém aparecer na sala sem estar.

## Onde ficam os dados

| O quê | Onde | Vai para o GitHub? |
|---|---|---|
| Código, documentação, testes | pasta do projeto | Sim |
| Equipe, demandas, presença, histórico | `%LOCALAPPDATA%\Hub\hub.db` no PC reserva | **Não** |
| Planilhas dos painéis (metas, vendas da 8081 etc.) | pasta dos painéis (padrão `%LOCALAPPDATA%\Hub\Painéis`, ou a pasta de rede escolhida) | **Não**. No repositório só há exemplos com dados fictícios (`tools/exemplos/`) |
| Cópias diárias (14 dias) | `%LOCALAPPDATA%\Hub\copias` | **Não** |
| Dados de demonstração | criados na hora por `tools/seed_demo.py`, com nomes **fictícios** | O script sim; os dados não |

Nada sai da rede da empresa: sem nuvem, sem telemetria, sem terceiros.

## Acesso

- **Nome + PIN (desde a fase 2).** Cada pessoa cria um PIN de 4 a 6 números no primeiro acesso. O Hub guarda só um resumo do PIN, com sal, e ninguém consegue ver o PIN de ninguém. A entrada vale até a meia-noite. Cinco PINs errados seguidos bloqueiam aquele nome por 5 minutos.
- **Papéis:** analista ou gestor, mais a marcação de administrador. Só administradores gerenciam Pessoas, mudam papéis e redefinem PINs. Toda mudança de acesso fica no histórico, com quem fez.
- **A TV continua sem login,** porque só mostra o que já é público, e o endereço da TV não lê nada de PIN, papel ou sessão.
- Formulários enviados a partir de **outro site** são recusados (verificação de mesma origem).
- O Hub fica acessível a quem estiver na rede da empresa e souber o endereço, mas só entra quem tem o PIN de alguém da equipe.
