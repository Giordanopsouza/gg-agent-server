# Root delegator. Component commands live in their folders.
.DEFAULT_GOAL := help

.PHONY: help install test unit-tests integration-tests lint-check lint-fix
.PHONY: format-check format-fix pre-commit build ci run run-runtime docker-build
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

.PHONY: modal-init modal-migrate modal-backup modal-restore modal-deploy modal-rollover modal-stop modal-verify

modal-init:
	$(MAKE) -C backend $@

modal-migrate:
	$(MAKE) -C backend $@

modal-backup:
	$(MAKE) -C backend $@

modal-restore:
	$(MAKE) -C backend $@

modal-deploy:
	$(MAKE) -C backend $@

modal-rollover:
	$(MAKE) -C backend $@

modal-stop:
	$(MAKE) -C backend $@

modal-verify:
	$(MAKE) -C backend $@
