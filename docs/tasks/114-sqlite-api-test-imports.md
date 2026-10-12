---
id: 114-sqlite-api-test-imports
feature: sqlite-modal
status: done
depends_on: ["113-sqlite-test-fixtures"]
---

# Task 114: Fixtures SQLite nos testes de API

**Descrição:** Atualizar consumidores de ledger para o helper SQLite e validar API/SDK sem serviços externos.

**Critérios de aceitação:**

- [x] Imports usam test_support.sqlite_ledger; nenhuma URL/skip Postgres nesses casos.
- [x] Cobrir criar/listar/ler tarefa, idempotência e isolamento HTTP/SDK com arquivo temporário.
- [x] Reabertura mantém o mesmo DB do teste; preservar assertions existentes.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_task_api.py backend/tests/test_runtime_control_api.py backend/tests/test_task_ledger.py backend/tests/test_task_ownership.py packages/gg-sdk/tests/test_task_client_integration.py`.
- [x] Demo/check operacional: Executar sem GG_RUNTIME_DATABASE_URL e conferir contratos preservados.

**Dependências:** [113-sqlite-test-fixtures](113-sqlite-test-fixtures.md).

**Arquivos prováveis:**

- `backend/tests/test_task_api.py`
- `backend/tests/test_runtime_control_api.py`
- `backend/tests/test_task_ledger.py`
- `backend/tests/test_task_ownership.py`
- `packages/gg-sdk/tests/test_task_client_integration.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Resultado (2026-10-08):** Testes focados 113–114: 54 passed, zero skips,
sem GG_RUNTIME_DATABASE_URL. QA agregado: 456 passed, 3 skips legados,
2 deselected; builds Python/React e 15 testes frontend aprovados.
Ver [evidência 112–114](evidence/112-114-verification.md).
