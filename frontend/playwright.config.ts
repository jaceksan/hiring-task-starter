import { defineConfig, devices } from "@playwright/test";

const isFast = process.env.E2E_FAST === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: isFast ? 25_000 : 60_000,
  expect: { timeout: isFast ? 5_000 : 15_000 },
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  globalSetup: "./e2e/global-setup",
  globalTeardown: "./e2e/global-teardown",
});

