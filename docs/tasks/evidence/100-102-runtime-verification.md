# Provas 100–102 — 2026-10-08

Worktree: `091-sqlite-modal`. Alterações anteriores 094–099 foram preservadas.

## Implementação

- 100: migração 8, GitHub SQLite cifrado, identidade GitHub única, instalações
  por proprietário, state ligado à sessão local ativa, expiração, consumo único,
  HMAC e deduplicação persistida de webhook. As rotas aguardam checkpoint.
- 101: o candidato foi incorporado a `ledger.py`; `sqlite_ledger.py` e
  `web_sessions.py` foram removidos. Lifespan abre o banco existente (ou restaura
  snapshot validado em caminho novo), compartilha banco/coordenador entre stores,
  configura Google direto e reconcilia antes de admissão. Barreiras HTTP cobrem
  mutações e respostas de replay; SQLite retorna 503 sanitizado. GET individual
  preserva `agent_outcome` do manifest como a listagem. HTTP/WebSocket isolam
  proprietários, e rotas administrativas exigem a chave de operador.
- 102: confirmação antes de provisionar, iniciar execução, entregar continuação,
  entregar token de escrita/publicação, push/PR, cancelamento e limpeza.
  Checkpoint periódico de dois segundos para atividade; falhas suspendem novos
  efeitos e aparecem na readiness. Recuperação usa nome/tags, start_key, message_id
  e marker de PR preservados.

## Verificação automatizada

Sequência final, na ordem: `make format-fix`, `make lint-fix`,
`make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`.
Resultado Python: **328 passed, 92 skipped, 2 deselected**. Os 92 skips ainda
exigem o harness Postgres legado; sua migração está nas tarefas 113–118. Isso
não é uma prova completa desses casos legados.

Comando focado:

```sh
uv run --no-editable pytest backend/tests/test_github_connection.py   backend/tests/test_repository_authorization.py   backend/tests/test_sqlite_runtime_api.py backend/tests/test_durable_effects.py
```

**20 passed** (7 GitHub/autorização, 5 API integrada, 8 barreiras/recuperação).
Inclui OAuth Google com RSA controlada, sessão de dois usuários, callback
GitHub forjado/repetido, cifra/constraints, webhook assinado/repetido, HTTP e
WebSocket de outro proprietário rejeitados, revisão no snapshot, falha de
commit com 503/readiness e retomada idempotente. Falhas antes do efeito mantêm
zero chamadas; respostas perdidas mantêm um sandbox, uma execução por chave,
um recibo por mensagem e um PR. Teste de queda após criação restaura a última
intenção confirmada e descobre o provider existente.

`make frontend-test`: **15 testes Vitest e 5 testes do servidor aprovados**.
`make frontend-build` e `make build`: aprovados (React e três pacotes Python).
`git diff --check`: aprovado.

## Prova operacional local com Modal real

Runtime em `http://127.0.0.1:8001`, Vite em `http://127.0.0.1:5173`, proxy
explicitamente local. Banco inicializado por `gg.runtime.db_cli init`, isolado
em `/tmp/gg-100-102-live.g5arl2`, capacidade 1, dispatch habilitado e nenhuma
tarefa preexistente. Health, frontend e proxy autenticado: 200; readiness ready.

Task `a333010c-1206-4594-81ff-3cefe41e53e4`, submetida pela API administrativa:

1. O Pi criou `sqlite-barrier-proof.txt` com `SQLITE_MODAL_100_102_OK`, executou
   `cat sqlite-barrier-proof.txt` e retornou exatamente esse conteúdo. Arquivados
   10 eventos, manifest com `agent_outcome=succeeded`, evidence_complete=true.
2. Runtime reiniciado e mesmas identidades reconciliadas: provider
   `sb-8fPchRqRE0IonH0bSY2wUU`, nome
   `gg-gg-production-0264cfb13bf919e750ac`.
3. POST de continuação `100-102-restart-message` repetido duas vezes gerou um
   único recibo (`delivered_to_pi`). Nova execução
   `6af75519f1077333f1fe19e9809b772e`, mesmo sandbox, 18 eventos acumulados,
   `agent_outcome=succeeded`. A resposta releu o arquivo sem modificá-lo e
   confirmou `SQLITE_MODAL_100_102_OK` após restart.
4. Após parar o runtime, o ciclo normal `_sleep_workspace` sincronizou e
   suspendeu o workspace de teste. Provider stopped, task sleeping, resultado
   sucedido preservado. GET `/tasks/dispatch/status` confirmou `reserved=0`,
   `pending=0`; consulta do resultado após reabrir o banco conservou o manifest.
   A execução terminou; o workspace fica sleeping pelo contrato de continuação.

`check_outcome=not_run`: nenhum check formal foi solicitado; o comando `cat`
e a observação estão nos eventos e provam o pedido. O endpoint de cancelamento
retorna 409 para workspace idle pelo contrato atual; a limpeza usou o ciclo de
suspensão, sem alterar esse comportamento.

Logs e respostas brutos desta prova estão em `/tmp/gg-100-102-live.g5arl2`
(`events.json`, `result.json`, `events-after-restart.json`,
`result-after-restart.json`, `cleanup.json`, `http-cleanup.json`). Processos
runtime/Vite iniciados nesta prova foram encerrados; o sandbox foi parado.

## Limite do aceite

**Primeiro pré-requisito ausente:** `GG_GOOGLE_CLIENT_ID`; também faltam
`GG_GOOGLE_CLIENT_SECRET`, origem/cifra web e configuração GitHub App no
ambiente local. A UI abriu a tela de login e `/auth/session` retornou 503 de
configuração. A demonstração com login humano de duas contas e conexões
individuais da tarefa 101 permanece pendente; por isso ela está in-progress,
com implementação e testes concluídos.

A prova real cobriu Vite/proxy → API administrativa → SQLite/checkpoint local
→ Modal/Pi → eventos/resultado → restart/mensagem idempotente → suspensão e
liberação da reserva. O caminho com cookies Google/GitHub e duas contas foi
verificado com provedores controlados nos testes, não com contas humanas.
Volume.commit e publicação de PR real permanecem provas posteriores: os
checkpoints desta execução usam fsync local; o servidor central publicado no
Modal é a tarefa 111. Injeção de falhas de commit/provider/PR foi automatizada.
