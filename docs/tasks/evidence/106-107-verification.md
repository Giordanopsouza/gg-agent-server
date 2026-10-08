# Provas 106–107 — 2026-10-08

Worktree `091-sqlite-modal`, reutilizada a pedido do usuário. Checkout principal
preservado. Sem commit local ou merge.

## Implementação e aceite

106: GET de eventos mantém lista Pydantic e ordem seq. `after` exclusivo
(default 0) e `limit` positivo opcional são propagados ao EventLog; filtro e
LIMIT ocorrem no SQLite, sem carregar o histórico antes de cortar a página.
Sem parâmetros continua retornando o histórico inteiro. Erros de query retornam
400, conforme o handler de validação já existente do sandbox. WebSocket e SDK
não mudaram. Teste HTTP concatena páginas e compara com a leitura completa.

107: migração SQLite 10 cria watermark por `(task_id, source_id)`. Supervisão
consulta páginas de até 200, começando no watermark persistido. Página,
identidades, contadores públicos e watermark usam uma transação BEGIN IMMEDIATE.
Rollback descarta tudo; retry deduplica identidades preexistentes. Watermark não
regride e conversas novas têm cursor independente. Eventos inseridos são
notificados depois do commit; eventos deduplicados não são notificados.

A política de truncamento existente é aplicada dentro da transação usando a
contagem de bytes persistidos e acumulando os bytes da página. O cursor de
origem continua avançando após truncar. Notificações usam o mesmo evento
truncado que a evidência persistida. A política preserva stubs mínimos mesmo
após o teto de payload; não promete teto absoluto que exclua esse overhead.

Testes: falha SQL na segunda inserção reverte página/cursor/revision; retry
preserva cursor público monotônico; troca de conversa independente. História de
450 eventos falha após a primeira página, fecha/reabre SQLite e retoma em 200:
requests `(0,200), (200,200)[falha], (200,200), (400,200)`; evidência final igual
à origem. Nova sincronização consulta somente after=450. Filas notificam 200 e
250 inserções, sem duplicar no retry. Truncamento de 201 eventos também avança
até 201 e a fila corresponde à evidência armazenada.

A suíte de integração de supervisão foi migrada para SQLite temporário. O fake
conta execuções novas em vez de tentativas HTTP idempotentes; o teste de
continuação usa driver explícito de execução/finalização para não disputar com
o loop de supervisão. A manutenção é disparada explicitamente após avançar a
data fixture, preservando o intervalo de produção de 60 segundos.

## Comandos e resultados

```sh
uv sync --no-editable --reinstall-package gg-backend --reinstall-package gg-sandbox
uv run --no-editable pytest sandboxes/tests/test_event_routes.py \
  sandboxes/tests/test_event_websocket.py packages/gg-sdk/tests/test_sdk_importable.py \
  backend/tests/test_incremental_event_sync.py \
  backend/tests/test_task_supervision_integration.py backend/tests/test_modal_image.py
```

32 passed. QA em ordem: `make format-fix`, `make lint-fix`,
`make format-check`, `make lint-check`, `make pre-commit`, `make unit-tests`.
Resultado: **357 passed, 78 skipped, 2 deselected**. Skips são suites legadas
Postgres e testes opt-in, sem alegar sua validação. `make build` aprova os três
pacotes. `git diff --check` aprovado. Logs `/tmp/gg-106-108-*.log`.

A paginação também foi provada na imagem publicada com o smoke Modal opt-in:
**1 passed**, sem PostgreSQL. Ver [demo 108](../../../tasks/evidence/108-sandbox-demo.md).
