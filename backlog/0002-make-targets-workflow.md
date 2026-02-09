## Make targets: fix vs lint vs types

### Problem

We sometimes run:

- `make fix-frontend && make types-frontend && make lint-frontend`

This is usually redundant because:

- `fix-frontend` already applies Biome autofixes (format + lint) via `biome check --write`
- `lint-frontend` should primarily be a verification step (no writes), ideally using the same `biome check` baseline

### Desired semantics

- `fix-*`: applies autofixes (writes)
- `lint-*`: verifies (no writes) and should be “strict enough” to catch formatting + lint issues
- `types-*`: typechecks

### Plan

- Make `lint-frontend` run `biome check` (not `biome lint`) so it also verifies formatting.
- Make `lint-backend` actually lint (ruff check + format --check) instead of only `compileall`.
- Update Cursor workflow rule to recommend:
  - `make fix-all && make types-all` for day-to-day
  - `make lint-all` when you specifically want verification (e.g. before pushing)

