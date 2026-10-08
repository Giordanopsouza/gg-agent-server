---
id: 114-sqlite-api-test-imports
feature: sqlite-modal
status: pending
depends_on: ["113-sqlite-test-fixtures"]
---

# Task 114: Fixtures SQLite nos testes de API

**Descrição:** Atualizar consumidores de ledger para o helper SQLite e validar API/SDK sem serviços externos.

**Critérios de aceitação:**

- [ ] Imports usam test_support.sqlite_ledger; nenhuma URL/skip Postgres nesses casos.
- [ ] Cobrir criar/listar/ler tarefa, idempotência e isolamento HTTP/SDK com arquivo temporário.
- [ ] Reabertura mantém o mesmo DB do teste; preservar assertions existentes.

**Verificação:**

- [ ] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_task_api.py backend/tests/test_runtime_control_api.py backend/tests/test_task_ledger.py backend/tests/test_task_ownership.py packages/gg-sdk/tests/test_task_client_integration.py`.
- [ ] Demo/check operacional: Executar sem GG_RUNTIME_DATABASE_URL e conferir contratos preservados.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [113-sqlite-test-fixtures](113-sqlite-test-fixtures.md).

**Arquivos prováveis:**

- `backend/tests/test_task_api.py`
- `backend/tests/test_runtime_control_api.py`
- `backend/tests/test_task_ledger.py`
- `backend/tests/test_task_ownership.py`
- `packages/gg-sdk/tests/test_task_client_integration.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
