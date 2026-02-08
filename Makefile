.PHONY: help \
	lint-all lint-backend lint-frontend \
	types-all types-backend types-frontend \
	test-all test-backend test-frontend \
	test-integration-all test-integration-backend test-integration-frontend \
	test-e2e-frontend \
	fix-backend fix-frontend fix-all

help:
	@printf "%s\n" \
		"Targets:" \
		"  lint-all                 Lint backend + frontend" \
		"  lint-backend             Lint backend" \
		"  lint-frontend            Lint frontend" \
		"  types-all                Run typechecks (where available)" \
		"  types-frontend           Run frontend typechecks" \
		"  types-backend            Run backend typechecks (currently no-op)" \
		"  test-all                 Run tests (where available)" \
		"  test-backend             Run backend unit tests" \
		"  test-frontend            Run frontend tests (currently no-op)" \
		"  test-integration-all     Run integration tests (where available)" \
		"  test-integration-backend Run backend integration tests" \
		"  test-integration-frontend Run frontend integration tests (Playwright e2e)" \
		"  test-e2e-frontend        Run frontend Playwright e2e" \
		"  fix-backend      Auto-fix backend (ruff format)" \
		"  fix-frontend     Auto-fix frontend (biome --write)" \
		"  fix-all          Auto-fix backend + frontend" \
		""

lint-all: lint-backend lint-frontend

lint-backend:
	@cd backend && uv run python -m compileall -q .

lint-frontend:
	@cd frontend && npm run -s lint

types-all: types-backend types-frontend

types-backend:
	@:

types-frontend:
	@cd frontend && npm run -s typecheck

test-all: test-backend test-frontend

test-backend:
	@cd backend && uv run pytest -q

test-frontend:
	@:

test-integration-all: test-integration-backend test-integration-frontend

test-integration-backend:
	@cd backend && uv run pytest -q -m integration

test-integration-frontend:
	@$(MAKE) test-e2e-frontend

test-e2e-frontend:
	@cd frontend && E2E_FAST=1 npm run -s e2e

fix-backend:
	@cd backend && uv run ruff format .

fix-frontend:
	@cd frontend && npm run -s check -- --write

fix-all: fix-backend fix-frontend
