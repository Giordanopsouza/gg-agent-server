# Root delegator. Component commands live in their folders.
.DEFAULT_GOAL := help

.PHONY: help install test unit-tests integration-tests lint-check lint-fix
.PHONY: format-check format-fix pre-commit build ci run run-runtime docker-build
.PHONY: supabase-local-start supabase-local-reset supabase-integration-tests postgres-tests alembic-tests
.PHONY: db-upgrade db-current db-check

help:
	@$(MAKE) -C packages/gg-sdk help
	@$(MAKE) -C backend help
	@$(MAKE) -C sandboxes help
	@printf '%s\n' 'root: run-runtime starts the control plane on port 8001'

install:
	uv sync --no-editable

test:
	uv run --no-editable pytest

unit-tests:
	uv run --no-editable pytest -m "not docker and not pi and not modal and not github"

integration-tests:
	uv run --no-editable pytest -m "modal or github"

lint-check:
	uv run --no-editable ruff check packages/gg-sdk backend sandboxes tests scripts test_support conftest.py

lint-fix:
	uv run --no-editable ruff check --fix packages/gg-sdk backend sandboxes tests scripts test_support conftest.py

format-check:
	uv run --no-editable ruff format --check packages/gg-sdk backend sandboxes tests scripts test_support conftest.py

format-fix:
	uv run --no-editable ruff format packages/gg-sdk backend sandboxes tests scripts test_support conftest.py

pre-commit: format-check lint-check unit-tests

postgres-tests:
	uv run --no-editable python scripts/runtime_postgres_tests.py -m "not docker and not pi and not modal and not github"
	uv run --no-editable python scripts/alembic_postgres_tests.py

alembic-tests:
	uv run --no-editable python scripts/alembic_postgres_tests.py

build:
	uv build --package gg-sdk
	uv build --package gg-backend
	uv build --package gg-sandbox

ci: install test lint-check format-check build

run:
	$(MAKE) -C sandboxes run

run-runtime:
	$(MAKE) -C backend run

docker-build:
	$(MAKE) -C sandboxes docker-build

SUPABASE_LOCAL_WORKDIR ?= .
LOCAL_MIGRATION_DATABASE_URL ?= postgresql://postgres:postgres@127.0.0.1:54322/postgres?sslmode=disable
ALEMBIC := uv run --no-editable alembic -c backend/alembic.ini

db-upgrade:
	@test -n "$(GG_MIGRATION_DATABASE_URL)" || { echo "Set GG_MIGRATION_DATABASE_URL to the migrator Postgres URL"; exit 1; }
	GG_MIGRATION_DATABASE_URL='$(GG_MIGRATION_DATABASE_URL)' $(ALEMBIC) upgrade head

db-current:
	@test -n "$(GG_MIGRATION_DATABASE_URL)" || { echo "Set GG_MIGRATION_DATABASE_URL to the migrator Postgres URL"; exit 1; }
	GG_MIGRATION_DATABASE_URL='$(GG_MIGRATION_DATABASE_URL)' $(ALEMBIC) current

db-check:
	@test -n "$(GG_MIGRATION_DATABASE_URL)" || { echo "Set GG_MIGRATION_DATABASE_URL to the migrator Postgres URL"; exit 1; }
	GG_MIGRATION_DATABASE_URL='$(GG_MIGRATION_DATABASE_URL)' $(ALEMBIC) check

# The only destructive database target is deliberately local-only. Never pass a
# linked project or --db-url to this target.
supabase-local-start:
	@test -x node_modules/.bin/supabase || { echo "Run npm ci first"; exit 1; }
	./node_modules/.bin/supabase --workdir $(SUPABASE_LOCAL_WORKDIR) start

supabase-local-reset:
	@test "$(SUPABASE_RESET_TARGET)" = "gg-agent-server" || { echo "Set SUPABASE_RESET_TARGET=gg-agent-server for the local Docker project"; exit 1; }
	./node_modules/.bin/supabase --workdir $(SUPABASE_LOCAL_WORKDIR) db reset --local --no-seed
	GG_MIGRATION_DATABASE_URL='$(LOCAL_MIGRATION_DATABASE_URL)' $(ALEMBIC) upgrade head

supabase-integration-tests:
	@test "$(SUPABASE_RESET_TARGET)" = "gg-agent-server" || { echo "Integration resets local data; set SUPABASE_RESET_TARGET=gg-agent-server"; exit 1; }
	./node_modules/.bin/supabase --workdir $(SUPABASE_LOCAL_WORKDIR) test db --local
	SUPABASE_LOCAL_WORKDIR=$(SUPABASE_LOCAL_WORKDIR) uv run --no-editable python scripts/supabase_auth_smoke.py
	SUPABASE_LOCAL_WORKDIR=$(SUPABASE_LOCAL_WORKDIR) PYTHONPATH=backend uv run --no-editable python scripts/supabase_pool_smoke.py
	SUPABASE_LOCAL_WORKDIR=$(SUPABASE_LOCAL_WORKDIR) SUPABASE_RESET_TARGET=$(SUPABASE_RESET_TARGET) uv run --no-editable python scripts/supabase_auth_smoke.py --upgrade
	GG_MIGRATION_DATABASE_URL='$(LOCAL_MIGRATION_DATABASE_URL)' $(ALEMBIC) check
	./node_modules/.bin/supabase --workdir $(SUPABASE_LOCAL_WORKDIR) test db --local
	./node_modules/.bin/supabase --workdir $(SUPABASE_LOCAL_WORKDIR) db advisors --local --type security --fail-on error
