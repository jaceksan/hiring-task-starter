.PHONY: help \
	lint types test test-integration test-all \
	fix fix-backend fix-frontend fix-all \
	backend-lint backend-test backend-test-integration \
	frontend-lint frontend-types

help:
	@printf "%s\n" \
		"Targets:" \
		"  lint             Run backend lint/sanity (fast)" \
		"  types            Run typechecks (frontend)" \
		"  test             Run fast tests (backend unit)" \
		"  test-integration Run integration tests (backend -m integration)" \
		"  test-all         Run fast backend tests + frontend types" \
		"  fix              Auto-fix backend (fast)" \
		"  fix-backend      Auto-fix backend (ruff format)" \
		"  fix-frontend     Auto-fix frontend (biome --write)" \
		"  fix-all          Auto-fix backend + frontend" \
		"" \
		"Lower-level targets:" \
		"  backend-lint" \
		"  backend-test" \
		"  backend-test-integration" \
		"  frontend-lint" \
		"  frontend-types"

lint: backend-lint

types: frontend-types

test: backend-test

test-integration: backend-test-integration

test-all: backend-test frontend-types

fix: fix-backend

fix-backend:
	@cd backend && uv run ruff format .

fix-frontend:
	@cd frontend && npm run -s check -- --write

fix-all: fix-backend fix-frontend

backend-lint:
	@cd backend && uv run python -m compileall -q .

backend-test:
	@cd backend && uv run pytest -q

backend-test-integration:
	@cd backend && uv run pytest -q -m integration

frontend-lint:
	@cd frontend && npm run -s lint

frontend-types:
	@cd frontend && npm run -s typecheck

