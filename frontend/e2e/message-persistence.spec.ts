import { expect, test } from "@playwright/test";

async function expectPlotlyTraceName(page: any, pattern: RegExp) {
  await expect
    .poll(
      async () => {
        return await page.evaluate(() => {
          const el = document.querySelector(".js-plotly-plot") as any;
          const data = el?.data;
          const names = Array.isArray(data)
            ? data.map((t: any) => String(t?.name ?? "")).filter(Boolean)
            : [];
          return names;
        });
      },
      { timeout: 15_000 }
    )
    .toEqual(expect.arrayContaining([expect.stringMatching(pattern)]));
}

async function disableAutoMinimizeChat(page: any) {
  const toggle = page.getByLabel(/auto-minimize chat/i);
  if ((await toggle.count()) > 0) {
    await toggle.setChecked(false);
  }
}

async function selectPragueScenario(page: any) {
  const scenario = page.getByTitle("Select scenario pack");
  if ((await scenario.count()) > 0) {
    await scenario.selectOption("prague_population_infrastructure_small");
  }
  const engine = page.getByTitle("Select backend engine");
  if ((await engine.count()) > 0) {
    await engine.selectOption("duckdb");
  }
}

async function openChatDrawer(page: any) {
  // Chat UI lives in the collapsible bottom drawer.
  const input = page.locator('textarea[placeholder="Ask PangeAI..."]');
  if ((await input.count()) > 0 && (await input.first().isVisible())) {
    return;
  }

  const chatButton = page.getByTitle(/expand chat/i);
  await expect(chatButton).toBeVisible();
  await chatButton.click();

  await expect(input).toBeVisible();
}

test("AI answer persists after commit (no disappearing message)", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueScenario(page);

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  await openChatDrawer(page);
  const input = page.locator('textarea[placeholder="Ask PangeAI..."]');
  await input.fill("how many places are flooded?");
  await input.press("Enter");

  // Wait for the final answer to appear in the thread history.
  const answer = page.getByText(/I found \d+ places in flood zones/i);
  await expect(answer).toBeVisible({ timeout: 30_000 });

  // Regression guard: it must still be visible shortly after commit/refetch.
  await page.waitForTimeout(1000);
  await expect(answer).toBeVisible();
});

test("safest places with reachable roads works and persists", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueScenario(page);

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  await openChatDrawer(page);
  const input = page.locator('textarea[placeholder="Ask PangeAI..."]');
  await input.fill(
    "show safest nearby places outside selected flood risk with reachable roads",
  );
  await input.press("Enter");

  const answer = page.getByText(
    /Safest nearby places with reachable roads:|Couldn’t find nearby places with reachable roads/i,
  );
  await expect(answer).toBeVisible({ timeout: 30_000 });

  // Regression guard: it must still be visible shortly after commit/refetch.
  await page.waitForTimeout(1000);
  await expect(answer).toBeVisible();
});

test("zoomed out view uses clusters (LOD)", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueScenario(page);

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

  await openChatDrawer(page);
  await page.getByRole("button", { name: "show layers" }).click();
  // Assert on the actual Plotly trace names (legend may not be visible in the DOM).
  await expectPlotlyTraceName(page, /\(clusters\)$/);
});

test("highlighted response can render clusters at low zoom", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueScenario(page);

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

  await openChatDrawer(page);
  const input = page.locator('textarea[placeholder="Ask PangeAI..."]');
  await input.fill(
    "show safest nearby places outside selected flood risk with reachable roads",
  );
  await input.press("Enter");

  await expect(
    page.getByText(
      /Safest nearby places with reachable roads:|Couldn’t find nearby places with reachable roads/i,
    ),
  ).toBeVisible({ timeout: 30_000 });
  await expectPlotlyTraceName(page, /\(clusters\)$/);
});

