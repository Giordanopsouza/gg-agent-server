# Root delegator. Component commands live in their folders.
.DEFAULT_GOAL := help

.PHONY: help install test unit-tests integration-tests lint-check lint-fix
.PHONY: format-check format-fix pre-commit build ci run run-runtime docker-build
.PHONY: supabase-local-start supabase-local-reset supabase-integration-tests postgres-tests alembic-tests
.PHONY: db-upgrade db-current db-check
.PHONY: frontend-install frontend-test frontend-build frontend-dev

help:
	@$(MAKE) -C packages/gg-sdk help
	@$(MAKE) -C backend help
	@$(MAKE) -C sandboxes help
	@$(MAKE) -C frontend help
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
	uv run --no-editable ruff check packages/gg-sdk backend sandboxes conftest.py

lint-fix:
	uv run --no-editable ruff check --fix packages/gg-sdk backend sandboxes conftest.py

format-check:
	uv run --no-editable ruff format --check packages/gg-sdk backend sandboxes conftest.py

format-fix:
	uv run --no-editable ruff format packages/gg-sdk backend sandboxes conftest.py

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

frontend-install:
	$(MAKE) -C frontend install

frontend-test:
	$(MAKE) -C frontend test

frontend-build:
	$(MAKE) -C frontend build

frontend-dev:
	$(MAKE) -C frontend dev

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
