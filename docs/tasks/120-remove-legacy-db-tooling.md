---
id: 120-remove-legacy-db-tooling
feature: sqlite-modal
status: pending
depends_on: ["119-remove-alembic-revisions","112-modal-state-operations"]
---

# Task 120: Retirar ferramentas de banco antigas

**Descrição:** Remover templates/config Alembic, CLI Supabase da raiz e targets root obsoletos.

**Critérios de aceitação:**

- [ ] Excluir script.py.mako/alembic.ini e raiz package.json/package-lock.json usados só para Supabase.
- [ ] Root Makefile remove verbs/scripts Supabase/Postgres/Alembic e mantém comandos SQLite/Modal.
- [ ] Frontend npm permanece; builds dos pacotes e frontend continuam disponíveis.

**Verificação:**

- [ ] Teste/comando focado: `make help; make build; make frontend-build; git diff --check`.
- [ ] Demo/check operacional: Inventariar scripts/supabase presentes e remover referências quebradas sem recriar arquivos ausentes.
- [ ] Para código, cumprir sequência QA/build aplicável do [plano](../../tasks/plan.md#definition-of-done-e-provas); documentar resultados e limitações.

**Dependências:** [119-remove-alembic-revisions](119-remove-alembic-revisions.md), [112-modal-state-operations](112-modal-state-operations.md).

**Arquivos prováveis:**

- `backend/alembic/script.py.mako (remover)`
- `backend/alembic.ini (remover)`
- `package.json (remover)`
- `package-lock.json (remover)`
- `Makefile`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Contexto:** [plano](../../tasks/plan.md), [especificação](../../tasks/spec.md). Usar worktree dedicado `091-sqlite-modal`; não implementar no checkout principal.
