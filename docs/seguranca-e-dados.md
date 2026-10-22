# Segurança e dados

## Quem vê o quê

| O quê | TV da sala | App (analistas) |
|---|---|---|
| Presença e "desde quando" | Sim | Sim |
| Demandas normais (título, pasta, quem pediu, prazo) | Sim | Sim |
| Demanda **reservada** | Só "Demanda reservada", a cor e as iniciais do dono e o prazo | Tudo para o dono, quem criou, o gestor e os administradores. Os demais veem como na TV e não abrem, movem nem excluem |
| Visão do gestor (resumo do dia e todas as demandas) | Não | Só o gestor e os administradores |
| Prazos da semana (tela da TV) | Sim, com a reservada mascarada como no Quadro | Não se aplica |
| Prioridades do mês | O item, a pasta, o prazo e, nos feitos, só as iniciais e a cor de quem fez | Todos veem a lista, quem fez e quando. Qualquer pessoa marca como feita; remover, só quem acrescentou ou um administrador |
| Painéis de vendas (metas, positivação, produtos foco) | **Só porcentagens e gráficos**, nunca valores, quantidades ou nomes | Página Painéis: só a situação das planilhas (lida, quantas linhas, quando). Enviar planilha: só administradores |
| Banco de horas (saldo e entrada/saída de cada dia) | **Nunca** (o endereço da TV nem consulta essas tabelas) | Só a própria pessoa e o gestor. Administrador sozinho não vê |
| Rotinas (nome, dias, horário, prazo, responsável, pastas) | O cartão de cada rotina no Quadro, com horário, prazo e pastas marcadas, e o aviso no horário (nome e horário). Cartão de rotina marcado como reservado: mascarado como qualquer reservada, e o aviso dele não vai | Página Rotinas: todos veem; cadastrar e mudar, só o gestor e os administradores. Marcar pasta: qualquer pessoa, com o nome no histórico |
| Envios do Pombo (tela Envios do dia) | Horário, nome do envio, analista, canal, situação e "N de M enviados". **Nunca** destinatários, motivo das falhas nem nomes de arquivo | Página Envios: tudo isso mais os destinatários, o motivo de cada falha e a situação de cada arquivo |
| Pausa da TV (fase 10) | O selo "Pausada", com as iniciais de quem pausou pelo app | Página **TV da sala**: qual tela está na TV, quem pausou e até quando; pausar, trocar e retomar com PIN, tudo no histórico. "Abrir no meu PC" mostra o mesmo que a TV |
| Descrição e arquivos das demandas (fase 11) | **Nunca** (nem o 📎; o endereço da TV nem consulta a tabela dos anexos) | Quem vê a demanda lê a descrição, anexa e baixa; reservada, só o dono, quem criou, o gestor e os administradores. Remover: quem anexou, o dono, gestor e administradores. Lixeira e pasta: administradores |
| Calendário (fase 13) | Tela Agenda: título, horário, tipo e iniciais dos compromissos **da equipe** (reservado como "Compromisso reservado"), feriados e quem está ausente ("Ausente até dd/mm"). **Nunca** a descrição, o local, os compromissos "só eu" nem o motivo da ausência | Compromisso da equipe: todos veem; reservado, só os participantes, quem criou, o gestor e os administradores. "Só eu": só quem criou (nem o histórico registra). Motivo da ausência: só a pessoa e o gestor; o histórico grava só as datas |
| Notas pessoais (fase 12) | **Nunca** | **Só a dona**: nem o gestor, nem os administradores. Não entram no histórico. Para quem saiu da equipe, o administrador vê só a quantidade e pode apagar de vez |
| Modos da TV (fase 14) | O nome do modo no topo (o Padrão não aparece). No modo com títulos escondidos (Visita), o servidor manda só "Demanda" com a cor e as iniciais, e tira os textos das outras telas | Trocar o modo: qualquer pessoa com PIN, no histórico. Criar, editar, apagar e as regras: gestor e administradores. Pré-visualizar: qualquer pessoa, só no próprio PC |
| Prioridades por pasta (fase 16) | As letras das pastas de cada item, acesas (concluída) ou apagadas (falta), e a tabela das Metas do mês com ✓/✕ por etapa e pasta. Nunca quem marcou, nomes nem horários | Marcar a pasta: quem cuida dela, o gestor e os administradores; no histórico. Ligar as pessoas às pastas e o papel Assistente: administradores |
| Exportar em PDF (fase 15) | O PDF é a TV: os mesmos dados do `/api/tv` (painéis só em %, reservadas mascaradas, modo com títulos escondidos vale também), com o rodapé "gerado em … por (iniciais)" | Qualquer pessoa com PIN exporta; fica no histórico quem exportou qual tela e quando, porque o PDF sai da sala |
| Histórico | Não | Sim (as linhas do banco de horas só para a própria pessoa e o gestor) |
| PIN | Não | Ninguém (só um resumo fica guardado) |

Os painéis seguem a regra do gestor: muita gente passa pela sala, então a TV mostra metas só em porcentagem. Isso também é feito **no servidor**: o endereço da TV recebe apenas percentuais e as letras das pastas, e um teste automático confere que nenhum valor, quantidade ou nome das planilhas vai junto. Os nomes de vendedor e supervisor da 8081 só são lidos para tirar a letra da pasta (ou ver se é Televendas), e não ficam guardados.

O histórico do Pombo é só **lido**: o Hub nunca escreve na pasta do Pombo. Do CSV, a TV recebe apenas o horário, o nome do envio, quem enviou, o canal e a situação, e um teste automático confere que destinatários, detalhes dos erros e nomes de arquivo não vão junto (o motivo de uma falha pode trazer um endereço de e-mail ou o nome de um grupo). O nome do envio aparece na TV: evite nomes sensíveis no Pombo ou desligue a tela em Configurações.

A demanda reservada é mascarada **no servidor**: a página da TV nunca recebe o título, então nem quem inspecionar a página consegue ver. No app vale o mesmo para quem não pode ver: o quadro, o histórico e a página da demanda chegam sem o título.

## Presença

Marcada **sempre pela própria pessoa**. O Hub não detecta nada sozinho: não olha login, câmera, Wi-Fi nem atividade do computador. À meia-noite todos voltam para "Fora da empresa", para ninguém aparecer na sala sem estar.

## Onde ficam os dados

| O quê | Onde | Vai para o GitHub? |
|---|---|---|
| Código, documentação, testes | pasta do projeto | Sim |
| Equipe, demandas, presença, histórico | `%LOCALAPPDATA%\Hub\hub.db` no PC reserva | **Não** |
| Planilhas dos painéis (metas, vendas da 8081 etc.) | pasta dos painéis (padrão `%LOCALAPPDATA%\Hub\Painéis`, ou a pasta de rede escolhida) | **Não**. No repositório só há exemplos com dados fictícios (`tools/exemplos/`) |
| Anexos das demandas | pasta Anexos (padrão `%LOCALAPPDATA%\Hub\Anexos`, ou a pasta de rede escolhida), com nomes aleatórios; o nome original fica no `hub.db` | **Não** |
| Banco de horas | dentro do `hub.db` (a planilha do RH é lida e descartada, não fica guardada) | **Não** |
| Histórico de envios do Pombo | a pasta do histórico de cada Pombo (em geral na rede). O Hub só lê e guarda na memória o mês atual | **Não** |
| Cópias diárias (14 dias) | `%LOCALAPPDATA%\Hub\copias` | **Não** |
| Dados de demonstração (inclusive um histórico do Pombo) | criados na hora por `tools/seed_demo.py`, com nomes **fictícios** | O script sim; os dados não |

Nada sai da rede da empresa: sem nuvem, sem telemetria, sem terceiros.

## Acesso

- **Nome + PIN (desde a fase 2).** Cada pessoa cria um PIN de 4 a 6 números no primeiro acesso. O Hub guarda só um resumo do PIN, com sal, e ninguém consegue ver o PIN de ninguém. A entrada vale até a meia-noite. Cinco PINs errados seguidos bloqueiam aquele nome por 5 minutos.
- **Entrar digitando o nome (fase 17).** A tela Entrar não lista mais a equipe: a pessoa digita o nome (sem diferença de acento e maiúscula) e o PIN. Além do bloqueio por nome, **um mesmo aparelho** que errar 10 vezes em 15 minutos, em qualquer nome, espera até o erro mais antigo sair da conta. Nome que não existe também conta como erro.
- **Pedido de cadastro (fase 17).** Quem não está no Hub pede o cadastro pela tela Entrar, já criando o PIN (guardado só como resumo, como os outros). A pessoa **só entra depois que um administrador aprova** em Pessoas, como analista ou assistente; gestor e administrador só se dão depois, em Pessoas. No máximo 5 pedidos esperando, 3 por aparelho por hora, nome repetido recusado, e o pedido some em 7 dias. Pedir, aprovar e recusar ficam no histórico. Só num Hub vazio (instalação nova) o primeiro cadastro entra direto, já como administrador.
- **No celular (fase 18):** só pela Wi-Fi da empresa, com o mesmo nome + PIN do PC. O Hub não abre túnel nem vai para a internet; o QR Code da página **No celular** leva só o endereço da rede e a tela Entrar, sem chave nem PIN. Para usar de fora da empresa, o caminho é a VPN da empresa (TI).
- **Papéis:** analista, assistente ou gestor, mais a marcação de administrador. Só administradores gerenciam Pessoas, mudam papéis e redefinem PINs. Toda mudança de acesso fica no histórico, com quem fez.
- **A TV continua sem login,** porque só mostra o que já é público, e o endereço da TV não lê nada de PIN, papel ou sessão.
- Formulários enviados a partir de **outro site** são recusados (verificação de mesma origem).
- O Hub fica acessível a quem estiver na rede da empresa e souber o endereço, mas só entra quem tem o PIN de alguém da equipe.
