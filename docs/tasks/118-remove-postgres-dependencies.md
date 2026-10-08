---
id: 118-remove-postgres-dependencies
feature: sqlite-modal
status: done
depends_on: ["100-sqlite-github-connections","101-sqlite-runtime-wiring","117-remove-postgres-test-harness"]
---

# Task 118: Remover dependências Postgres

**Descrição:** Após portar consumidores/testes antigos, remover dependências SQLAlchemy/Psycopg/Alembic, engine, schema ORM e certificado. Retirar ferramentas legadas nas 119–120.

**Critérios de aceitação:**

- [x] Stores/runtime ativos usam sqlite3; remover postgres.py/db_models.py/certificado sem imports restantes.
- [x] backend/pyproject.toml e uv.lock deixam de depender de SQLAlchemy/Psycopg/Alembic.
- [x] uv sync --no-editable, make build e unit tests funcionam sem engine legado.

**Verificação:**

- [x] Teste/comando focado: `uv sync --no-editable; make build; make unit-tests`.
- [x] Demo/check operacional: Inspecionar pacote construído e importá-lo em ambiente limpo; subdividir remoções se o diff exceder uma sessão.
- [x] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [100-sqlite-github-connections](100-sqlite-github-connections.md), [101-sqlite-runtime-wiring](101-sqlite-runtime-wiring.md), [117-remove-postgres-test-harness](117-remove-postgres-test-harness.md).

**Arquivos prováveis:**

- `backend/pyproject.toml`
- `uv.lock`
- `backend/gg/runtime/postgres.py (remover)`
- `backend/gg/runtime/db_models.py (remover)`
- `backend/gg/runtime/certs/supabase-prod-ca-2021.crt (remover)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.

**Resultado (2026-10-08):** Dependências e imports legados removidos; `uv sync --no-editable`, build e 446 testes unitários aprovados. Wheel importável no ambiente sincronizado sem SQLAlchemy/Psycopg/Alembic. Ver [provas 118–120](evidence/118-120-verification.md).
