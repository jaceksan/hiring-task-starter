## Backend type checking with Astral “ty”

### Goal

Adopt `ty` as a backend type checker, run it locally/CI, and fix issues it finds.

### Notes

- Decide scope first:
  - “core only” (engine + api paths) vs “entire backend”
  - allow a small ignore list initially, but drive it to zero
- Integrate into:
  - `make types-backend`
  - CI (if present)

