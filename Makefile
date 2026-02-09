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
		"  lint-all                 Verify backend + frontend (no writes; format + lint)" \
		"  lint-backend             Verify backend (no writes; syntax + format --check)" \
		"  lint-frontend            Verify frontend (no writes; biome check)" \
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
		"  fix-backend      Auto-fix backend (ruff format + ruff check --fix)" \
		"  fix-frontend     Auto-fix frontend (biome check --write)" \
		"  fix-all          Auto-fix backend + frontend" \
		""

lint-all: lint-backend lint-frontend

lint-backend:
	@cd backend && uv run python -m compileall -q .
	@cd backend && uv run ruff format --check .
	@cd backend && uv run ruff check .

lint-frontend:
	@cd frontend && npm run -s check

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
	@cd backend && (uv run pytest -q -m integration; status=$$?; if [ $$status -eq 5 ]; then exit 0; else exit $$status; fi)

test-integration-frontend:
	@$(MAKE) test-e2e-frontend

test-e2e-frontend:
	@cd frontend && E2E_FAST=1 npm run -s e2e

fix-backend:
	@cd backend && uv run ruff format .
	@cd backend && uv run ruff check --fix .

fix-frontend:
	@cd frontend && npm run -s check -- --write

fix-all: fix-backend fix-frontend
