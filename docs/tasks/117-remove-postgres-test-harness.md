---
id: 117-remove-postgres-test-harness
feature: sqlite-modal
status: pending
depends_on: ["114-sqlite-api-test-imports","115-sqlite-scheduler-test-imports","116-sqlite-auth-supervision-tests"]
---

# Task 117: Retirar harness de testes Postgres

**Descrição:** Substituir testes exclusivos do engine antigo por provas SQLite e remover o reexport temporário.

**Critérios de aceitação:**

- [ ] Mapear invariantes de test_runtime_postgres.py/test_postgres_ledger_integration.py para provas SQLite antes de removê-los.
- [ ] Nenhum import test_support.postgres_ledger restante; remover reexport.
- [ ] Configuração/integração SQLite provam locks, rollback, restore e versão futura sem rede.

**Verificação:**

- [ ] Teste/comando focado: `make unit-tests`.
- [ ] Demo/check operacional: Comparar passes/skips e conferir importabilidade dos três pacotes.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [114-sqlite-api-test-imports](114-sqlite-api-test-imports.md), [115-sqlite-scheduler-test-imports](115-sqlite-scheduler-test-imports.md), [116-sqlite-auth-supervision-tests](116-sqlite-auth-supervision-tests.md).

**Arquivos prováveis:**

- `backend/tests/test_runtime_postgres.py (remover)`
- `backend/tests/test_postgres_ledger_integration.py (remover)`
- `backend/tests/test_sqlite_configuration.py (novo)`
- `backend/tests/test_sqlite_ledger_integration.py (novo)`
- `test_support/postgres_ledger.py (remover)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
