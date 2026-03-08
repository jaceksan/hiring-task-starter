## Backend type checking with Astral “ty”

### Status

Completed.

### Outcome note

- Added `ty` to backend dev dependencies and configured `make types-backend` to run `uv run ty check .`.
- Fixed all initial backend/test diagnostics reported by `ty`; `make types-backend` now passes cleanly.
- AIDA validation already routes backend/repo checks through `types_backend`/`types_all`, so type checks now run automatically via existing AIDA validation flows.

### Goal

Adopt `ty` as a backend type checker, run it locally/CI, and fix issues it finds.

### Notes

- Decide scope first:
  - “core only” (engine + api paths) vs “entire backend”
  - allow a small ignore list initially, but drive it to zero
- Integrate into:
  - `make types-backend`
  - CI (if present)

