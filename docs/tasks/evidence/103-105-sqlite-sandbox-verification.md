# Provas 103–105 — 2026-10-08

Worktree: `091-sqlite-modal`, branch homônima. Mudanças anteriores 094–102
preservadas. Nenhum commit, deploy de produção ou mudança nos serviços locais
preexistentes foi realizado.

## Implementação

- **103:** migração SQLite 9 com índices de fila FIFO, reservas, expiração e
  settlement. Scheduler consulta contagem da fila e páginas de até 200
  workspaces vencidos, ordenadas por seq. Preserva manutenção a cada 60 segundos,
  expiração de sete dias e limites de capacidade. Supervisão já consulta somente
  reservas; esse caminho foi mantido. Sem `ledger.list()` no ciclo/status.
  Reconcile descarta respostas de uma reserva encerrada ou substituída enquanto
  aguardava o provider, impedindo que um snapshot antigo sobrescreva uma retomada
  queued. Regressão cobre encerramento com e sem uma nova reserva.
- **104:** `SandboxState` abre conexões por operação com journal DELETE,
  synchronous FULL, foreign_keys ON e busy_timeout de 10 segundos. Schema inicial
  e user_version são transacionais. Metadados/base state são gravados juntos;
  eventos e recibos ficam no SQLite. O catálogo consulta o banco em vez de
  procurar meta.json. O banco normal fica em `conversations_dir/sandbox.db`;
  diretórios de workspace e arquivos nativos Pi não são migrados.
- **105:** supervisor compartilha esse banco com conversas. start_key UNIQUE e
  execution_id são inseridos numa única transação BEGIN IMMEDIATE. Replay mantém
  identidade e rejeita conflito de tarefa, repositório, branch, base ou modelo.
  Manifests ficam no banco; `manifest_path` mantém o contrato string com referência
  `sqlite:<db>#manifest/<execution_id>`, consumida pelo store, sem arquivo JSON.
  Schema 2 guarda também a identidade da conversa em sandbox_metadata; o arquivo
  task-supervisor/conversation-id foi removido. Writers concorrentes reutilizam
  uma única identidade. Startup preserva um manifest salvo antes da fase terminal e falha execuções
  admitidas que perderam o processo, sem iniciar outro agente.
- Helper independente Pi usa `--state-db` no lugar de `--intent-path`. A intenção
  é chaveada pelo marcador; valida identidade dentro da transação, preserva o SHA
  em retries e continua a reconciliar PR por head/base/marker após timeout. A
  instrução cita argumentos com shlex e usa caminho absoluto para o banco.

Sem importação de JSON legado, conforme a especificação de banco novo. JSON em
colunas SQLite é serialização dos modelos Pydantic, sem uma fonte em arquivo
paralela. Protocolos HTTP/WebSocket e fronteiras SDK/runtime/sandbox preservados.

## Provas automatizadas

Comando focado obrigatório combinado:

```sh
uv run --no-editable pytest backend/tests/test_scheduler.py \
  backend/tests/test_scheduler_recovery.py sandboxes/tests/test_event_log.py \
  sandboxes/tests/test_local_conversation.py sandboxes/tests/test_task_supervisor.py \
  sandboxes/tests/test_pi_publication.py
```

58 testes passam. Cobertura inclui:

- FIFO/capacidade, adoção após resposta perdida, manutenção em páginas e ciclo que
  falha/recomeça. A suíte scheduler agora usa SQLite temporário em vez de pular
  por ausência do harness Postgres; doubles de latência foram adaptados.
- Metadados, base state, eventos e recibos reabertos; arquivos nativos Pi
  preservados; JSON legado ignorado. Um processo termina com os._exit dentro de
  DELETE não confirmado e a conexão seguinte recupera os eventos já confirmados.
- 24 admissões por oito writers/stores independentes criam uma execução; conflito
  de identidade é rejeitado. Crash entre admissão/início não duplica execução.
  Crash após salvar manifest preserva o resultado; recibos/message_id e controles
  HTTP/WebSocket são exercitados pelas suítes existentes.
- Git real para um origin bare **local** e GitHub controlado: intenção persistida
  antes da criação, conflito sem efeito, timeout de criação reconciliado em uma
  PR. Dois processos reais da CLI reabrem o mesmo SQLite (caminho com espaços),
  fazem push para o origin local e reutilizam uma PR no serviço gh de teste.
  Nenhuma chamada GitHub ou OpenRouter real nesses testes.

Pacotes foram reinstalados explicitamente com `uv sync --no-editable
--reinstall-package gg-backend --reinstall-package gg-sandbox` para testar as
fontes atuais, pois a instalação anterior em site-packages estava desatualizada.

Sequência QA final, na ordem: `make format-fix`, `make lint-fix`,
`make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`.
Resultado Python: **349 passed, 82 skipped, 2 deselected**. Os skips ainda usam o
harness Postgres legado, cuja remoção/migração pertence às tarefas 113–118.
`make frontend-test`: 15 testes Vitest e 5 testes do servidor passam.
`make frontend-build`, `make build` (três pacotes Python) e `git diff --check`
aprovados. Logs em `/tmp/gg-103-105-{focused,pre-commit,unit-tests,frontend-test,frontend-build,build}.log`.

## Histórico sintético e planos SQL

Executável com:

```sh
uv run --no-editable pytest backend/tests/test_scheduler.py -k large_history -s
```

Fixture: três tarefas queued, 205 workspaces sleeping vencidos e 10 mil tarefas
completed com payloads grandes. A primeira página permanece idêntica antes e
depois de inserir histórico (200 registros); a segunda retorna cinco. O ciclo
processa os 205 candidatos e a página seguinte retorna zero; fila permanece com
três. O teste falha se `ledger.list()` for chamado pelo ciclo ou pelo status.

EXPLAIN QUERY PLAN observado:

| Consulta | Plano |
| --- | --- |
| FIFO | SEARCH tasks USING INDEX tasks_state_seq (state=?) |
| Reservas | SCAN task_reservations USING INDEX reservations_order |
| Expiração | SEARCH tasks USING INDEX tasks_sleeping_expiry (expr < cutoff); TEMP B-TREE para ordenar os candidatos por seq |
| Settlement | SEARCH tasks USING INDEX tasks_settlement (outcome_detail=?) |

A consulta de expiração seleciona explicitamente o índice parcial: sem isso o
planner preferiu tasks_state_seq e poderia visitar workspaces ainda recentes.
A ordenação temporária contém somente candidatos vencidos. Não se afirma ganho
percentual de latência ou uma medida de performance no Modal.

## Aceite operacional real

A autorização explícita do usuário para enviar o código ao Modal e os dados do
demo ao OpenRouter resolveu o bloqueio inicial da revisão automática. A imagem
`gg-agent-sqlite-103-105-test` foi publicada com as fontes finais. Skills
local-stack e Modal orientaram o demo; o ledger central usou SQLite e checkpoint
local com fsync, conforme a especificação atual, em vez do Postgres descrito na
skill antiga. Frontend Vite em 5174 e runtime em 8002, com dispatch habilitado;
serviços preexistentes em 8001 e 5173 preservados.

Tarefa real: `f2de3599-ff92-4fac-913f-650fe75c505f`. O Pi via OpenRouter criou
`proof.txt`, leu pelo shell e respondeu exatamente `SQLITE_103_105_OK` nas duas
execuções. Eventos action/observation e a resposta final foram inspecionados;
`check_outcome=not_run` porque nenhum check formal foi pedido. Não se usa somente
o rótulo succeeded como prova.

- Execução inicial: `2f7173b4f3f66d0bb26cf1776ed5860d`, provider
  `sb-H82RaIukyrCgVT1LDRQNgl`, 14 eventos.
- Reinício do runtime mantendo o sandbox: mesmo provider e manifest recuperados.
- Sleep normal sincronizou o workspace, encerrou o sandbox e liberou a reserva.
  A continuação com message_id `103-105-after-restart`, enviada duas vezes,
  iniciou somente uma execução nova: `e4076506df108dd92a94a8b00abdd0b1` no
  provider `sb-g6fIAJk3iViYCHkHvPTUXf`, reabrindo o mesmo Volume. Total: 22 eventos.
- Metadados/identidade, eventos, arquivo, sessão nativa Pi JSONL e recibo
  `103-105-live-steer` sobreviveram. O steer usou a API de controle da conversa;
  a API runtime de mensagens agenda uma continuação. Replay de start_key retornou
  a execução original e os dois manifests permaneceram no banco.
- CLI do helper na imagem real expõe --state-db. Uma intenção sintética
  `103-105-fixture` foi gravada e relida; retry sem SHA preservou `fixture-sha`.
  Outro container (`sb-TY9OyFsXBJJp5VQl7p9eKC`) reabriu o mesmo Volume e confirmou
  a intenção e os PRAGMAs DELETE/FULL/FK/busy_timeout.
- Nesse container, um processo admitiu a execução fixture
  `13b311597f0858303e37b1e1993a1973` e encerrou antes de iniciá-la. Um segundo
  processo abriu o supervisor real: phase failed, agent_outcome not_run, replay
  created=false. Nenhum agente novo iniciou. Essa fixture acrescentou uma execução
  falhada aos dois resultados reais bem-sucedidos do banco de teste.

Uma tentativa de sleep/wake revelou a corrida de reconcile descrita acima; ela
foi corrigida e o demo completo repetido com sucesso. Ao final, a tarefa ficou
sleeping com resultado sucedido preservado, **reserved=0 e pending=0**. Os
sandboxes de teste foram encerrados e os serviços próprios em 8002/5174 parados.

Evidência bruta local:
`/var/folders/np/k6zjxvqx6hj930xjq_kq9pnr0000gn/T/gg-103-105-modal.9qrq04vl`,
incluindo `volume-recovery.json`. Logs adicionais:
`/tmp/gg-103-105-{modal-build,live,volume-recovery}.log`.

**Boundary verificado:** frontend → runtime SQLite/dispatch → Modal/Pi/OpenRouter
→ eventos, recibos e manifests SQLite → restart central → sleep/recriação do
sandbox com o mesmo Volume → cumprimento do prompt e liberação de reserva;
helper independente e recuperação após admissão também na imagem real.

Não foi criada PR GitHub real: timeout/reconciliação e uma única PR foram
comprovados com Git real local e gh controlado nos testes de processos descritos
acima. Login Google humano e checkpoint central via Modal Volume.commit não
foram exercitados; o checkpoint central deste demo foi local. A persistência do
Volume do sandbox foi exercitada por encerramento e reabertura reais. Esses
limites não são alegados como entregues pelas tarefas 103–105.
