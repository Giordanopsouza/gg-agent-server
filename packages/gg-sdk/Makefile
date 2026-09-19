.DEFAULT_GOAL := help

REPO_ROOT := ../..
UV_RUN := uv --directory $(REPO_ROOT) run --no-editable
PACKAGE := gg-sdk
TESTS := packages/gg-sdk/tests
SOURCES := packages/gg-sdk/gg packages/gg-sdk/tests

.PHONY: help install test unit-tests integration-tests lint-check lint-fix \
	format-check format-fix pre-commit build demo-pi demo-docker-pr

help:
	@printf '%s\n' \
		'gg-sdk targets:' \
		'  install            sync workspace dependencies' \
		'  test               run the full package suite' \
		'  unit-tests          run non-live tests' \
		'  integration-tests   run Docker/Pi-marked tests' \
		'  lint-check|lint-fix run Ruff linting' \
		'  format-check|format-fix run Ruff formatting' \
		'  pre-commit          run format, lint, and unit checks' \
		'  build               build the package distributions' \
		'  demo-pi             run the local Pi notes demo' \
		'  demo-docker-pr      run the Docker/GitHub PR demo'

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

demo-pi:
	$(UV_RUN) python -m gg.sdk.demo.pi_notes

demo-docker-pr:
	$(UV_RUN) python -m gg.sdk.demo.docker_pi_github_pr
