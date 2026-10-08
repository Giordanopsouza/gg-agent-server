---
id: 117-remove-postgres-test-harness
feature: sqlite-modal
status: done
depends_on: ["114-sqlite-api-test-imports","115-sqlite-scheduler-test-imports","116-sqlite-auth-supervision-tests"]
---

# Task 117: Retirar harness de testes Postgres

**Descrição:** Substituir testes exclusivos do engine antigo por provas SQLite e remover o reexport temporário.

**Critérios de aceitação:**

- [x] Mapear invariantes de test_runtime_postgres.py/test_postgres_ledger_integration.py para provas SQLite antes de removê-los.
- [x] Nenhum import test_support.postgres_ledger restante; remover reexport.
- [x] Configuração/integração SQLite provam locks, rollback, restore e versão futura sem rede.

**Verificação:**

- [x] Teste/comando focado: `make unit-tests`.
- [x] Demo/check operacional: Comparar passes/skips e conferir importabilidade dos três pacotes.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [114-sqlite-api-test-imports](114-sqlite-api-test-imports.md), [115-sqlite-scheduler-test-imports](115-sqlite-scheduler-test-imports.md), [116-sqlite-auth-supervision-tests](116-sqlite-auth-supervision-tests.md).

**Arquivos prováveis:**

- `backend/tests/test_runtime_postgres.py (remover)`
- `backend/tests/test_postgres_ledger_integration.py (remover)`
- `backend/tests/test_sqlite_configuration.py (novo)`
- `backend/tests/test_sqlite_ledger_integration.py (novo)`
- `test_support/postgres_ledger.py (remover)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

**Resultado (2026-10-08):** Harness Postgres e reexport removidos. QA:
446 passed, zero skips, 2 deselected; os três pacotes importam. Ver
[evidência 115–117](evidence/115-117-verification.md).
