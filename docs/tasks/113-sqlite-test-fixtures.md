---
id: 113-sqlite-test-fixtures
feature: sqlite-modal
status: done
depends_on: ["101-sqlite-runtime-wiring","107-incremental-event-sync"]
---

# Task 113: Testes unitários sem Postgres

**Descrição:** Criar fixtures SQLite temporárias e adaptar limpeza/reabertura. Manter o módulo antigo como reexport mínimo para consumidores ainda não portados; removê-lo na 117.

**Critérios de aceitação:**

- [x] Fixture cria DB isolado por caso sem rede, URL Postgres, Docker ou skip; todas as conexões usam o mesmo arquivo.
- [x] Reabertura e concorrência preservam estado entre instâncias do caso; cleanup não toca produção.
- [x] Autouse Postgres é substituído; reexport temporário aponta só para SQLite, sem cliente/engine Postgres.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_db.py backend/tests/test_sqlite_task_admission.py backend/tests/test_sqlite_task_evidence.py`.
- [x] Demo/check operacional: Executar sem serviços externos; adaptar consumidores nas 114–116 e remover reexport na 117.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [101-sqlite-runtime-wiring](101-sqlite-runtime-wiring.md), [107-incremental-event-sync](107-incremental-event-sync.md).

**Arquivos prováveis:**

- `test_support/sqlite_ledger.py (novo)`
- `test_support/postgres_ledger.py (reexport temporário)`
- `conftest.py`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

**Resultado (2026-10-08):** Testes focados 113–114: 54 passed, zero skips,
sem GG_RUNTIME_DATABASE_URL. QA agregado: 456 passed, 3 skips legados,
2 deselected; builds Python/React e 15 testes frontend aprovados.
Ver [evidência 112–114](evidence/112-114-verification.md).
