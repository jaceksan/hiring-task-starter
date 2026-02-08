import { expect, test } from "@playwright/test";

test("AI answer persists after commit (no disappearing message)", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  const input = page.getByPlaceholder("Ask PangeAI...");
  await input.fill("how many pubs are flooded?");
  await input.press("Enter");

  // Wait for the final answer to appear in the thread history.
  const answer = page.getByText(/I found \d+ beer places/i);
  await expect(answer).toBeVisible();

  // Regression guard: it must still be visible shortly after commit/refetch.
  await page.waitForTimeout(1000);
  await expect(answer).toBeVisible();
});

test("dry pubs near metro works and persists", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  const input = page.getByPlaceholder("Ask PangeAI...");
  await input.fill("find 20 dry pubs near metro");
  await input.press("Enter");

  const answer = page.getByText(/dry beer places closest to the metro/i);
  await expect(answer).toBeVisible();

  // Regression guard: it must still be visible shortly after commit/refetch.
  await page.waitForTimeout(1000);
  await expect(answer).toBeVisible();
});

