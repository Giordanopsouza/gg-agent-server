# Provas das tasks 118–120 — 2026-10-08

- Worktree: `.agents/worktrees/091-sqlite-modal`, branch `091-sqlite-modal`.
- `uv lock` removeu Alembic, SQLAlchemy, Psycopg e suas dependências exclusivas; `uv sync --no-editable` desinstalou essas bibliotecas do ambiente.
- Testes focados de GitHub, scheduler, cofre, auth e migrações SQLite: 38 passed.
- Sequência root `make format-fix lint-fix format-check lint-check pre-commit unit-tests`: passou, com 446 passed e 2 deselected.
- `make help build frontend-build`: passou; builds dos três pacotes Python e do React/Vite.
- Importação de `gg.runtime.app` e `gg.runtime.sqlite_migrations` no ambiente sincronizado passou; inspeção do wheel `gg_backend` confirmou ausência de `postgres.py`, `db_models.py` e certificado. As três bibliotecas removidas também ficaram ausentes do ambiente.
- `git diff --check` passou. Migrações ativas estão em `backend/gg/runtime/sqlite_migrations.py`, sequenciadas por `PRAGMA user_version` (versão 10); o ADR 0006 permanece como histórico.
- O inventário confirmou que `scripts/` e `supabase/` já não existiam na worktree; targets que os referenciavam foram removidos.

Não houve deploy nem alteração de estado remoto nestas tasks de limpeza. Os testes de login humano dependentes de OAuth e o corte de produção pertencem às tasks posteriores.
