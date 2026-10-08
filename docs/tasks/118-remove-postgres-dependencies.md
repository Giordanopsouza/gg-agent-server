---
id: 118-remove-postgres-dependencies
feature: sqlite-modal
status: pending
depends_on: ["100-sqlite-github-connections","101-sqlite-runtime-wiring","117-remove-postgres-test-harness"]
---

# Task 118: Remover dependências Postgres

**Descrição:** Após portar consumidores/testes antigos, remover dependências SQLAlchemy/Psycopg/Alembic, engine, schema ORM e certificado. Retirar ferramentas legadas nas 119–120.

**Critérios de aceitação:**

- [ ] Stores/runtime ativos usam sqlite3; remover postgres.py/db_models.py/certificado sem imports restantes.
- [ ] backend/pyproject.toml e uv.lock deixam de depender de SQLAlchemy/Psycopg/Alembic.
- [ ] uv sync --no-editable, make build e unit tests funcionam sem engine legado.

**Verificação:**

- [ ] Teste/comando focado: `uv sync --no-editable; make build; make unit-tests`.
- [ ] Demo/check operacional: Inspecionar pacote construído e importá-lo em ambiente limpo; subdividir remoções se o diff exceder uma sessão.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [100-sqlite-github-connections](100-sqlite-github-connections.md), [101-sqlite-runtime-wiring](101-sqlite-runtime-wiring.md), [117-remove-postgres-test-harness](117-remove-postgres-test-harness.md).

**Arquivos prováveis:**

- `backend/pyproject.toml`
- `uv.lock`
- `backend/gg/runtime/postgres.py (remover)`
- `backend/gg/runtime/db_models.py (remover)`
- `backend/gg/runtime/certs/supabase-prod-ca-2021.crt (remover)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
