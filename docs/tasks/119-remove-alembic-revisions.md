---
id: 119-remove-alembic-revisions
feature: sqlite-modal
status: done
depends_on: ["118-remove-postgres-dependencies"]
---

# Task 119: Retirar revisões Alembic ativas

**Descrição:** Remover quatro revisões antigas e env Alembic após schema SQLite e testes substitutos; manter história no Git.

**Critérios de aceitação:**

- [x] Remover 0001–0004/env.py sem código runtime dependente.
- [x] Schema SQLite cobre constraints necessárias sem copiar dados antigos.
- [x] Migrações SQLite não importam SQLAlchemy/Alembic; ADRs guardam contexto histórico.

**Verificação:**

- [x] Teste/comando focado: `uv run --no-editable pytest backend/tests/test_sqlite_db.py backend/tests/test_sqlite_configuration.py; git diff --check`.
- [x] Demo/check operacional: Verificar migrações SQLite/user_version como única autoridade ativa.

**Dependências:** [118-remove-postgres-dependencies](118-remove-postgres-dependencies.md).

**Arquivos prováveis:**

- `backend/alembic/versions/0001_application_baseline.py (remover)`
- `backend/alembic/versions/0002_task_model.py (remover)`
- `backend/alembic/versions/0003_github_connection.py (remover)`
- `backend/alembic/versions/0004_resumable_workspaces.py (remover)`
- `backend/alembic/env.py (remover)`

**Escopo estimado:** Médio (3–5 arquivos). Inventariar arquivos reais, incluindo remoções/imports/testes; subdividir antes de implementação se exceder cinco arquivos relevantes ou uma sessão focada.

**Resultado (2026-10-08):** Revisões/env Alembic removidos; `sqlite_migrations.py` usa `PRAGMA user_version` e os testes focados de migração/configuração passaram. Ver [provas 118–120](evidence/118-120-verification.md).
