## Root delegator; component logic lives in packages/*/Makefile.
.DEFAULT_GOAL := help

.PHONY: help install test unit-tests integration-tests lint-check lint-fix \
        format-check format-fix pre-commit build ci run docker-build \
        help-gg-sdk help-gg-server install-gg-sdk install-gg-server \
        test-gg-sdk test-gg-server unit-tests-gg-sdk unit-tests-gg-server \
        integration-tests-gg-sdk integration-tests-gg-server lint-check-gg-sdk \
        lint-check-gg-server lint-fix-gg-sdk lint-fix-gg-server \
        format-check-gg-sdk format-check-gg-server format-fix-gg-sdk \
        format-fix-gg-server pre-commit-gg-sdk pre-commit-gg-server build-gg-sdk \
        build-gg-server run-gg-server docker-build-gg-server

help: help-gg-sdk help-gg-server
install: install-gg-sdk install-gg-server
test: test-gg-sdk test-gg-server
unit-tests: unit-tests-gg-sdk unit-tests-gg-server
integration-tests: integration-tests-gg-sdk integration-tests-gg-server
lint-check: lint-check-gg-sdk lint-check-gg-server
lint-fix: lint-fix-gg-sdk lint-fix-gg-server
format-check: format-check-gg-sdk format-check-gg-server
format-fix: format-fix-gg-sdk format-fix-gg-server
pre-commit: pre-commit-gg-sdk pre-commit-gg-server
build: build-gg-sdk build-gg-server
ci: install test lint-check format-check pre-commit build
run: run-gg-server
docker-build: docker-build-gg-server

help-gg-sdk:
	$(MAKE) -C packages/gg-sdk help
help-gg-server:
	$(MAKE) -C packages/gg-server help
install-gg-sdk:
	$(MAKE) -C packages/gg-sdk install
install-gg-server:
	$(MAKE) -C packages/gg-server install
test-gg-sdk:
	$(MAKE) -C packages/gg-sdk test
test-gg-server:
	$(MAKE) -C packages/gg-server test
unit-tests-gg-sdk:
	$(MAKE) -C packages/gg-sdk unit-tests
unit-tests-gg-server:
	$(MAKE) -C packages/gg-server unit-tests
integration-tests-gg-sdk:
	$(MAKE) -C packages/gg-sdk integration-tests
integration-tests-gg-server:
	$(MAKE) -C packages/gg-server integration-tests
lint-check-gg-sdk:
	$(MAKE) -C packages/gg-sdk lint-check
lint-check-gg-server:
	$(MAKE) -C packages/gg-server lint-check
lint-fix-gg-sdk:
	$(MAKE) -C packages/gg-sdk lint-fix
lint-fix-gg-server:
	$(MAKE) -C packages/gg-server lint-fix
format-check-gg-sdk:
	$(MAKE) -C packages/gg-sdk format-check
format-check-gg-server:
	$(MAKE) -C packages/gg-server format-check
format-fix-gg-sdk:
	$(MAKE) -C packages/gg-sdk format-fix
format-fix-gg-server:
	$(MAKE) -C packages/gg-server format-fix
pre-commit-gg-sdk:
	$(MAKE) -C packages/gg-sdk pre-commit
pre-commit-gg-server:
	$(MAKE) -C packages/gg-server pre-commit
build-gg-sdk:
	$(MAKE) -C packages/gg-sdk build
build-gg-server:
	$(MAKE) -C packages/gg-server build
run-gg-server:
	$(MAKE) -C packages/gg-server run
docker-build-gg-server:
	$(MAKE) -C packages/gg-server docker-build
