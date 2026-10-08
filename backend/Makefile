# Component targets for backend.
.DEFAULT_GOAL := help
REPO_ROOT := ..
UV_RUN := uv --directory $(REPO_ROOT) run --no-editable
PACKAGE := gg-backend
TESTS := backend/tests
SOURCES := backend/gg backend/tests

.PHONY: help install test unit-tests integration-tests lint-check lint-fix
.PHONY: format-check format-fix pre-commit build run docker-build production-smoke-tests

help:
	@printf '%s\n' 'backend: install test unit-tests lint-check format-check build run'
	@printf '%s\n' 'backend: modal-init modal-migrate modal-backup modal-restore modal-deploy modal-rollover modal-stop modal-verify' '  Set MODAL_ENVIRONMENT; MODAL_URL for backup/rollover/verify; MODAL_SNAPSHOT for backup/restore; GG_RUNTIME_API_KEY for online operations' '  Runbook: docs/modal-state-operations.md'

install:
	uv --directory $(REPO_ROOT) sync --no-editable --package $(PACKAGE)

test:
	$(UV_RUN) pytest $(TESTS)

unit-tests:
	$(UV_RUN) pytest $(TESTS) -m "not docker and not pi and not modal and not github"

integration-tests:
	$(UV_RUN) pytest $(TESTS) -m "modal or github"

lint-check:
	$(UV_RUN) ruff check $(SOURCES)

lint-fix:
	$(UV_RUN) ruff check --fix $(SOURCES)

format-check:
	$(UV_RUN) ruff format --check $(SOURCES)

format-fix:
	$(UV_RUN) ruff format $(SOURCES)

pre-commit: format-check lint-check unit-tests

build:
	uv --directory $(REPO_ROOT) build --package $(PACKAGE)

run:
	$(UV_RUN) python -m gg.runtime --host 127.0.0.1 --port 8001

production-smoke-tests:
	$(UV_RUN) python scripts/runtime_postgres_tests.py backend/tests/test_production_operations.py

.PHONY: modal-init modal-migrate modal-backup modal-restore modal-deploy modal-rollover modal-stop modal-verify

MODAL_ENVIRONMENT ?=
MODAL_URL ?=
MODAL_SNAPSHOT ?=
MODAL_OPS := $(UV_RUN) python -m gg.runtime.modal_operations

modal-init:
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) init --environment "$(MODAL_ENVIRONMENT)"

modal-migrate:
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) migrate --environment "$(MODAL_ENVIRONMENT)"

modal-backup:
	@test -n "$(MODAL_SNAPSHOT)" || { echo "Set MODAL_SNAPSHOT explicitly"; exit 1; }
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) backup --environment "$(MODAL_ENVIRONMENT)" --url "$(MODAL_URL)" --snapshot "$(abspath $(MODAL_SNAPSHOT))"

modal-restore:
	@test -n "$(MODAL_SNAPSHOT)" || { echo "Set MODAL_SNAPSHOT explicitly"; exit 1; }
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) restore --environment "$(MODAL_ENVIRONMENT)" --snapshot "$(abspath $(MODAL_SNAPSHOT))"

modal-deploy:
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) deploy --environment "$(MODAL_ENVIRONMENT)"

modal-rollover:
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) rollover --environment "$(MODAL_ENVIRONMENT)" --url "$(MODAL_URL)"

modal-stop:
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) stop --environment "$(MODAL_ENVIRONMENT)"

modal-verify:
	@test -n "$(MODAL_ENVIRONMENT)" || { echo "Set MODAL_ENVIRONMENT explicitly"; exit 1; }
	$(MODAL_OPS) verify --environment "$(MODAL_ENVIRONMENT)" --url "$(MODAL_URL)"
