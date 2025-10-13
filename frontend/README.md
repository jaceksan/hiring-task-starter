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
