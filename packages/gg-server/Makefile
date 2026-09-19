.DEFAULT_GOAL := help

REPO_ROOT := ../..
UV_RUN := uv --directory $(REPO_ROOT) run --no-editable
PACKAGE := gg-server
TESTS := packages/gg-server/tests tests
SOURCES := packages/gg-server/gg packages/gg-server/tests tests

.PHONY: help install test unit-tests integration-tests lint-check lint-fix \
	format-check format-fix pre-commit build run docker-build

help:
	@printf '%s\n' \
		'gg-server targets:' \
		'  install            sync workspace dependencies' \
		'  test               run server and root boundary tests' \
		'  unit-tests          run non-live tests' \
		'  integration-tests   run Docker/Pi-marked tests' \
		'  lint-check|lint-fix run Ruff linting' \
		'  format-check|format-fix run Ruff formatting' \
		'  pre-commit          run format, lint, and unit checks' \
		'  build               build the package distributions' \
		'  run                 start the local agent server' \
		'  docker-build        build gg-agent-server:dev'

install:
	uv --directory $(REPO_ROOT) sync --no-editable --package $(PACKAGE)

test:
	$(UV_RUN) pytest $(TESTS)

unit-tests:
	$(UV_RUN) pytest $(TESTS) -m "not docker and not pi"

integration-tests:
	$(UV_RUN) pytest $(TESTS) -m "docker or pi"

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
	docker build -t gg-agent-server:dev $(REPO_ROOT)
