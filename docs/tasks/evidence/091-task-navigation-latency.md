# Worktree 091: latência de navegação e atualização — 2026-10-09

Correções entregues na branch `091-sqlite-modal`, sem deploy nem alteração de
configuração de produção por este agente. O usuário cadastrou o callback local
5173 e a prova real foi retomada com sucesso; veja a atualização ao final. Referência anterior às alterações:
`74255c89d300efc772532c05912efa4a564ca25e`.

## Mudanças e invariantes

- `LocalSessions.user()` consulta validade/revogação antes de esperar persistência.
  Sessões existentes não dependem das escritas globais posteriores. A criação
  de sessão e alterações do perfil mantêm uma barreira por identidade. O mapa
  de revisões pendentes usa somente hashes, descarta inserts revertidos e
  remove revisões já confirmadas. Instâncias restauradas preservam a barreira
  da revisão inicial. Depois de uma espera, validade e revogação são consultadas
  novamente. Criação e revogação continuam aguardando seu checkpoint antes de
  retornar sucesso; uma revogação local rejeita autenticação mesmo se seu
  checkpoint falhar.
- Foi encontrada uma segunda dependência global em `app.py`: o middleware
  esperava checkpoint antes e depois de todas as requisições. Apenas leituras
  de `/auth/session`, `/tasks`, `/tasks/{uuid}`, `/events` e `/result` foram
  dispensadas dessas esperas. O bloqueio durante recuperação continua ativo.
  Mutações, callbacks OAuth (inclusive GET), operações administrativas e
  barreiras anteriores aos efeitos externos continuam protegidos. Leituras
  podem mostrar atividade local ainda pendente de snapshot; não reconhecem
  sucesso de uma mutação nem confirmam durabilidade dessa atividade.
- `ensure_durable(revision)` revalida a revisão depois de obter o lock e
  compartilha commits que já satisfizeram a espera. Um `checkpoint()` explícito
  continua publicando, mesmo sem revisão nova. Escritas durante o commit
  permanecem pendentes, falhas não confirmam revisão, e cancelamento não libera
  o lock enquanto o commit protegido estiver em andamento.
- O ledger compara provider ID, estado e detalhe com SQL que trata NULL
  corretamente. Observações idênticas de `_reconnect()` não mudam `updated_at`
  nem revisão. Transições, descoberta/alteração de identidade e novos erros
  continuam gravados. A opção de transação sem avanço para DML sem alterações
  é usada somente nessa atualização; o comportamento padrão de `SQLiteDB.write`
  foi preservado, inclusive para DDL.
- A interface mantém task, resultado, histórico e cursor em memória por task,
  dentro do escopo da sessão. O cache é invalidado sincronicamente e limpo no
  logout/401; respostas e frames tardios não podem preenchê-lo novamente.
  Navegar de volta mostra o histórico carregado enquanto revalida. Criação
  alimenta a lista e o cache imediatamente; follow-up dispara atualização.
- Task, eventos e resultado são consultados independentemente, sem a cascata
  task→resultado. Polling usa cadência fixa, com uma requisição por tipo em voo
  e revalidação pendente agrupada. Listas lentas não apagam uma criação recente
  ou sobrescrevem um registro mais novo já recebido.
- WebSocket usa a mesma origem/cookie, replay por cursor, reconexão com espera
  crescente até 15 s e polling de recuperação a cada 2,5 s. HTTP carrega o
  histórico inicial; o socket depois solicita replay a partir do cursor.
  O backend registra a assinatura **antes** de enviar o replay. Eventos são
  deduplicados e ordenados por cursor; o cursor confirmado pelo frontend só
  avança sobre uma sequência contígua, permitindo recuperar frames perdidos
  por fila cheia. Callbacks de um socket antigo não afetam sua substituição.

SQLite/WAL, snapshots validados no Volume, escritor único, isolamento por UUID
Google e os contratos HTTP/WebSocket entre pacotes foram preservados. Nenhuma
migração, dependência de frontend ou import entre SDK e servidor foi adicionada.

## Comparação controlada e reprodução

Comando, a partir da raiz da worktree:

```sh
uv sync --no-editable --reinstall-package gg-backend
uv run --no-editable python backend/benchmarks/read_latency.py \
  74255c89d300efc772532c05912efa4a564ca25e
```

O script carrega coordinator, sessões e app daquele commit e da implementação
atual, usando o mesmo restante do código. Cada versão recebe banco novo,
mesmos dados, autenticação já confirmada, uma escrita não relacionada antes
cada cenário sujo e um commit artificial de **50 ms**. HTTP utiliza os endpoints
reais via ASGITransport, sem rede/TCP, OAuth remoto ou Modal. Números abaixo são
uma amostra final, não uma distribuição estatística ou previsão de produção.

| Fronteira/cenário | Antes | Depois | Commits antes→depois |
| --- | ---: | ---: | ---: |
| Autenticação: quatro leituras simultâneas de sessão | 232,23 ms | 2,93 ms | 4→0 |
| Persistência: quatro esperas simultâneas da mesma revisão | 224,07 ms | 58,41 ms | 4→1 |
| HTTP: quatro `GET /tasks` simultâneos após escrita não relacionada | 252,66 ms | 10,98 ms | 4→0 |
| HTTP: `GET /tasks` com cookie inválido após escrita não relacionada | 60,49 ms | 1,38 ms | 1→0 |
| Dados: task/eventos/resultado em paralelo, estado já confirmado | 31,63 ms | 8,50 ms | 0→0 |

O último cenário inclui autenticação, serialização e encaminhamento ASGI;
não é um cronômetro isolado de SQL e sua diferença não é evidência de melhoria
no sandbox. Os commits e a ausência de espera global são a evidência estrutural.
Saída completa: `/private/tmp/gg-091-latency-benchmark.log`.

As medições de produção fornecidas no diagnóstico (11,76–14,56 s em `/tasks`
com cookie inválido; 275–419 ms em `/health`) foram mantidas como contexto.
Não se comparam diretamente com o ensaio de commit artificial acima. A versão
corrigida não foi publicada, portanto não existe medição de produção depois.

**runtime→tela:** testes React/jsdom comprovam que um frame recebido aparece
na mesma atualização React, sem avançar o relógio virtual até o próximo poll;
cache aparece mesmo com GET pendente, e follow-up inicia GET imediatamente.
Replay, lacunas, duplicatas, reconexão, fallback e troca de task são exercitados.
Não foi cronometrada a entrega completa em navegador autenticado de produção.

**sandbox→runtime:** a tentativa inicial foi bloqueada antes da criação de um
sandbox. A retomada real mediu 13 eventos; resultados e limites constam abaixo.

## QA

Sequência final executada em ordem e com sucesso:

1. `make format-fix`
2. `make lint-fix`
3. `make format-check`
4. `make lint-check`
5. `make pre-commit` — 435 passed, 2 deselected
6. `make unit-tests` — 435 passed, 2 deselected

`make frontend-test`: 21 passed. `make frontend-build`: TypeScript e Vite
passaram. `git diff --check`: passou. Os testes adicionais cobrem concorrência,
escrita durante commit, falha/retry, sessão pendente, rollback, revogação durante
espera, middleware de leitura versus mutação, provider sem mudanças, assinatura
antes do replay, navegação/cache, frames obsoletos, expiração e follow-up.

Os primeiros testes de regressão expuseram uma instalação antiga não editable;
o backend foi reinstalado explicitamente antes do QA final. A primeira passagem
do QA encontrou dois testes que colidiram com o lock do runtime local iniciado
para o ensaio. Só os processos criados neste trabalho foram encerrados e toda
sequência foi repetida com sucesso. Logs finais completos em
`/private/tmp/gg-091-latency-qa-final/`. Permanecem avisos de depreciação de
Starlette/FastAPI já existentes; não houve falha na passagem final.

## Skill local-stack: tentativa inicial e bloqueio posteriormente resolvido

Foi lida `.agents/skills/local-stack/SKILL.md` da própria worktree, junto com
AGENTS da raiz, backend e frontend, ADR 0008 e runbook SQLite. Skills Modal e
React foram lidas no catálogo porque não há cópias delas nesta worktree.

Não havia processos saudáveis em 8001/5173. Foram inicializados explicitamente
SQLite e snapshot novos fora do repositório, geradas chaves locais de cookie e
vault e iniciado `GG_TASK_DISPATCH_ENABLED=true make run-runtime`. O estado era
novo e vazio, sem tasks de terceiros. Vite foi iniciado com
`VITE_DEV_API_PROXY=http://127.0.0.1:8001 make frontend-dev`. O navegador carregou
React, consultou a sessão através do proxy e iniciou o login Google real.

**Primeiro pré-requisito ausente:** Google rejeitou o callback
`http://127.0.0.1:5173/auth/google/callback` com **400 redirect_uri_mismatch**.
Nenhuma configuração de OAuth, Secret, Volume ou deploy foi alterada para
contornar esse bloqueio. Não se criou uma sessão humana local nem uma task real.
Logo, cumprimento do prompt, manifest final e liberação de uma reserva real
**não foram comprovados** neste ensaio.

Fronteira validada: navegador→Vite→gg.runtime→início de OAuth Google; banco e
snapshot local inicializados e runtime com dispatch habilitado. Também foram
observados HTTP 401 através de Vite para `/auth/session` sem sessão (6,95 ms)
e `/tasks` com cookie inválido (5,15 ms), em estado local já confirmado. Esses
smokes não provam desempenho com commit Modal nem equivalem ao benchmark sujo.
Os dois processos locais criados para o ensaio foram encerrados.


## Retomada real após o cadastro do callback 5173

O usuário informou que cadastrou também o callback 5173. O agente retomou o
stack nessa porta, sem modificar configuração externa. Novo SQLite/snapshot
isolado, chaves locais e lock de dispatch próprio; nenhum banco de produção
foi usado. Google autenticou no navegador. O usuário forneceu a credencial
OpenRouter e ela foi salva na sessão local, pelo formulário normal e com a
verificação da API; a credencial não consta destes artefatos.

Foram criadas duas tasks reais em **Blank workspace**, sem repositório nem
operações GitHub:

- Task 1: cálculo 17 × 23. A tela recebeu a explicação correta e o marcador
  `PROVA-091-391`. Follow-up pediu 6 × 7 e recebeu `PROVA-091-FOLLOWUP-42`.
- Task 2: cálculo 9 × 9. A tela recebeu `PROVA-091-TASK2-81`.
- Os dois sandboxes executaram no Modal. Foram copiados 9 e 4 eventos,
  respectivamente; conversas e respostas corretas apareceram na UI. As duas
  execuções finais têm manifest `agent_outcome=succeeded`,
  `check_outcome=not_run`, `evidence_complete=1`. Sem código a testar, nenhum
  resultado de testes de repositório foi alegado.
- A troca Task 2→Task 1 pelo histórico mostrou os 9 eventos e o follow-up
  correto. O intervalo clique→observação acessível foi 221 ms, **incluindo
  automação/observação**; não é um cronômetro isolado de pintura React.
- O produto mantém tasks finalizadas em `idle` com workspace disponível por
  45 minutos. Para testar a liberação sem aguardar esse prazo, **somente os
  timestamps de inatividade das duas tasks locais foram envelhecidos em 46
  minutos**, numa transação revisionada. O runtime executou seu fluxo normal
  de sync/terminate. Ambas passaram a `sleeping`, os providers a `stopped` e
  `/tasks/dispatch/status` respondeu 200, `reserved=0`, `pending=0`, sem erros.
  A tabela de reservas também ficou vazia. Não houve liberação manual de
  reservas nem substituição do provider por mock.
- Logout real removeu a conta e a conversa da tela e revogou a sessão. Ao fim,
  `/ready` respondeu 200 com revisão local e confirmada iguais (661).

**Sincronização sandbox→runtime:** foram comparados `event.created_at` do
sandbox e `task_event_copies.created_at` do runtime. Nos 13 eventos, os atrasos
observados variaram entre **149,81 ms e 2041,87 ms**. Para mensagens do agente:
181,15 ms na resposta inicial, 1257,40 ms no follow-up e 1476,18 ms na Task 2.
Esses intervalos incluem captura/sincronização e usam relógios de máquinas
separadas sem calibração; não são latência pura de rede. Não há amostra real
anterior equivalente que permita atribuir uma redução a esse trecho.

**runtime→tela:** entrega real e navegação foram observadas no navegador;
WebSocket e fallback foram usados pela versão corrigida. Não foi instalado
um cronômetro de frames/pintura, portanto esse trecho ainda não tem medição
isolada. Os testes determinísticos de cursor, replay e atualização React e o
benchmark HTTP acima continuam sendo provas separadas. Na validação local acima ainda não havia deploy; a publicação posterior está
registrada abaixo, com amostras HTTP de produção e suas limitações.

Evidências persistidas:

- [Conversa real e follow-up](091-live-task.jpg)
- [Estados, manifests, revisões e tempos dos 13 eventos](091-real-validation.json)

Os dois processos locais criados pelo agente foram encerrados após a prova.
O bloqueio anterior de OAuth foi resolvido e **a prova de execução real,
cumprimento do prompt, resultado arquivado e reserva liberada está concluída**.


## Deploy autorizado no Modal — 2026-10-09

O usuário autorizou a publicação e esclareceu que Railway estava fora do
escopo. Nenhum deploy ou alteração de configuração foi feito no Railway.

- Ambiente existente: `sqlite-111-proof`, App `gg-runtime`, deployment **v5**.
- URL: https://giordanowrk-sqlite-111-proof--gg-runtime-runtime.us-east.modal.direct/
- Código da imagem confirmado por `/ready`: `4d132b582ebff922`. O deploy
  inclui as alterações da worktree 091; histórico Modal registra HEAD
  `74255c8*`, com mudanças locais, sem commit novo.
- Procedimento oficial `gg.runtime.modal_operations`: backup antes da troca,
  lease exclusiva `state-writer` e estratégia `recreate`. Não houve init,
  migração, restore manual nem mudança do Secret.
- Backup privado anterior: `/private/tmp/gg-091-predeploy.snapshot`, revisão
  **37726**, permissão 0600, `integrity_check=ok`. Backup posterior validado:
  `/private/tmp/gg-091-postdeploy.snapshot`, revisão **37751**. Não são
  artefatos públicos e não foram adicionados ao Git.
- Verificação do deploy: health/ready aprovados; versão esperada; revisão
  local e confirmada **37736** naquele instante, dispatch reconciliado, sem
  erro de persistência ou scheduler. Leituras posteriores podem mostrar uma
  nova revisão em curso; o backup posterior confirmou a revisão 37751.
- Frontend servido: `/assets/index-NumISpUY.js`, HTTP 200, 251776 bytes,
  correspondente ao build validado.
- Comparação dos snapshots anterior/posterior preservou os totais: 5 tasks,
  1 usuário, 2 sessões, 1 credencial OpenRouter, 69 eventos e 4 resultados.
  Nenhum conteúdo privado ou segredo foi incluído nas evidências.

**Amostra HTTP de produção:** mesmo cliente httpx local, mesma URL e cookie
`gg_session` inválido, requisições sequenciais com conexão reutilizada; todas
responderam 401. Antes: 3768,71 / 153,35 / 148,86 ms. Depois: 104,36 /
103,20 / 109,41 / 112,35 / 115,68 / 103,40 ms. A primeira chamada anterior
foi muito mais lenta. Não houve controle da carga, atividade de sandbox ou
estado térmico do container; portanto essas amostras não provam uma redução
de 11–14 segundos em condições equivalentes, nem medem histórico autenticado
ou sandbox→runtime→tela. O benchmark controlado e a prova real local acima
continuam sendo as evidências específicas desses caminhos. Não foi criada
nova task de usuário em produção durante este deploy.

[Verificação sanitizada do deploy](091-modal-deploy-verification.json).
