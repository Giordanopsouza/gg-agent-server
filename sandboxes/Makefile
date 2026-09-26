# Component targets for sandboxes.
.DEFAULT_GOAL := help
REPO_ROOT := ..
UV_RUN := uv --directory $(REPO_ROOT) run --no-editable
PACKAGE := gg-sandbox
TESTS := sandboxes/tests
SOURCES := sandboxes/gg sandboxes/tests

.PHONY: help install test unit-tests integration-tests lint-check lint-fix
.PHONY: format-check format-fix pre-commit build run docker-build production-smoke-tests

help:
	@printf '%s\n' 'sandboxes: install test unit-tests lint-check format-check build run'

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
	$(UV_RUN) python -m gg.server --host 127.0.0.1 --port 8000

docker-build:
	docker build -f sandboxes/Dockerfile -t gg-agent-server:dev $(REPO_ROOT)
