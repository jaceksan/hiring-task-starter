.PHONY: help \
	run-all run-backend run-frontend \
	lint-all lint-backend lint-frontend \
	types-all types-backend types-frontend \
	test-all test-backend test-frontend \
	test-integration-all test-integration-backend test-integration-frontend \
	test-e2e-frontend \
	fix-backend fix-frontend fix-all

help:
	@printf "%s\n" \
		"Targets:" \
		"  run-backend              Start backend dev server (FastAPI on :8000)" \
		"  run-frontend             Start frontend dev server (Vite on :3000)" \
		"  run-all                  Show commands to run backend+frontend together" \
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

run-backend:
	@cd backend && uv run fastapi dev main.py

run-frontend:
	@$(MAKE) frontend-deps
	@cd frontend && npm run -s dev

run-all:
	@printf "%s\n" \
		"Run in two terminals:" \
		"  make run-backend" \
		"  make run-frontend"

lint-all: lint-backend lint-frontend

lint-backend:
	@cd backend && uv run python -m compileall -q .
	@cd backend && uv run ruff format --check .
	@cd backend && uv run ruff check .

frontend-deps:
	@cd frontend && (test -x node_modules/.bin/biome && test -x node_modules/.bin/tsc) || npm ci

lint-frontend:
	@$(MAKE) frontend-deps
	@cd frontend && npm run -s check

types-all: types-backend types-frontend

types-backend:
	@:

types-frontend:
	@$(MAKE) frontend-deps
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
	@$(MAKE) frontend-deps
	@cd frontend && E2E_FAST=1 npm run -s e2e

fix-backend:
	@cd backend && uv run ruff format .
	@cd backend && uv run ruff check --fix .

fix-frontend:
	@$(MAKE) frontend-deps
	@cd frontend && npm run -s check -- --write

fix-all: fix-backend fix-frontend
