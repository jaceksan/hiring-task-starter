# Frontend

Simple React app using Tanstack Router to expose 2 routes:

- `src/routes/index.tsx` → `/`
  - Homepage, list of threads, create thread button
- `src/routes/thread.$threadId.tsx` → `/thread/{id}`
  - Chat + map interface, [backend](../backend/README.md) integration

## How to run

You need `node` installed (you can use **nvm** with `nvm install` command).

```bash
npm install # installs the dependencies
npm run dev # starts the app on port 3000
```

## E2E tests (Playwright)

```bash
npm run e2e:install  # installs Chromium for Playwright
npm run e2e          # runs E2E tests (will start/reuse frontend+backend)
```

For faster iteration (no production build), use:

```bash
npm run typecheck
npm run e2e
```

If you want to run tests against already-running servers only:

```bash
E2E_REUSE_ONLY=1 npm run e2e
```
