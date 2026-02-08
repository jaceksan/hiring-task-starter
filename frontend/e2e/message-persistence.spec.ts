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

test("zoomed out view uses clusters (LOD)", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  // Deterministic: force low zoom on the invoke request so backend returns clustered points.
  await page.route("**/invoke", async (route) => {
    const req = route.request();
    const raw = req.postData();
    if (!raw) return route.continue();
    try {
      const body = JSON.parse(raw);
      body.map = body.map ?? {};
      body.map.view = body.map.view ?? {};
      body.map.view.zoom = 3;
      body.map.view.center = body.map.view.center ?? { lat: 50.0755, lon: 14.4378 };
      body.map.bbox = { minLon: -20, minLat: 30, maxLon: 40, maxLat: 70 };
      await route.continue({ postData: JSON.stringify(body) });
    } catch {
      await route.continue();
    }
  });

  await page.getByRole("button", { name: "show layers" }).click();
  await expect(page.getByText("Beer POIs (clusters)")).toBeVisible();
});

test("highlighted response can render clusters at low zoom", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  await page.route("**/invoke", async (route) => {
    const req = route.request();
    const raw = req.postData();
    if (!raw) return route.continue();
    try {
      const body = JSON.parse(raw);
      body.map = body.map ?? {};
      body.map.view = body.map.view ?? {};
      body.map.view.zoom = 3;
      body.map.view.center = body.map.view.center ?? { lat: 50.0755, lon: 14.4378 };
      body.map.bbox = { minLon: -20, minLat: 30, maxLon: 40, maxLat: 70 };
      await route.continue({ postData: JSON.stringify(body) });
    } catch {
      await route.continue();
    }
  });

  const input = page.getByPlaceholder("Ask PangeAI...");
  await input.fill("find 20 dry pubs near metro");
  await input.press("Enter");

  await expect(page.getByText(/dry beer places closest to the metro/i)).toBeVisible();
  await expect(page.getByText("Beer POIs (clusters)")).toBeVisible();
});

