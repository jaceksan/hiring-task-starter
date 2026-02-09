## Refactor Cursor rules + backlog workflow

### Goals

- Keep `.cursor/rules/` **small and focused** (frontend/backend/workflow/backlog).
- Make backlog management **explicit and consistent**: always start from `BACKLOG.md` order.
- Optionally adopt “Project AIDA” (private GoodData MCP server) when available to improve developer workflow.

### Proposed split

- `general.mdc`: minimal global principles (MVP bias, file size caps).
- `workflow.mdc`: how to validate changes; make-target guidance; when to run E2E/build.
- `frontend.mdc`: UI rules + Playwright determinism notes + shadcn install command.
- `backend.mdc`: backend safety/validation rules; restart guidance only when truly necessary.
- `backlog.mdc`: how to add/update backlog items and when to create a detail file under `backlog/`.

### AIDA adoption (future)

When “Project AIDA” is available as an MCP server:

- add a short rule snippet describing what AIDA is used for (issue/PR hygiene, routine checklists, release notes, etc.)
- keep it optional, since it’s private and might not be present in all environments

