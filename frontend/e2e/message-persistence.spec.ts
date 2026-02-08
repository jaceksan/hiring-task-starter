import { expect, test } from "@playwright/test";

async function disableAutoMinimizeChat(page: any) {
  const toggle = page.getByLabel(/auto-minimize chat/i);
  if ((await toggle.count()) > 0) {
    await toggle.setChecked(false);
  }
}

async function selectPragueTransport(page: any) {
  const scenario = page.getByTitle("Select scenario pack");
  if ((await scenario.count()) > 0) {
    await scenario.selectOption("prague_transport");
  }
  const engine = page.getByTitle("Select backend engine");
  if ((await engine.count()) > 0) {
    await engine.selectOption("in_memory");
  }
}

async function openChatDrawer(page: any) {
  // Chat UI lives in the collapsible bottom drawer.
  const input = page.getByPlaceholder("Ask PangeAI...");
  if ((await input.count()) > 0) {
    await expect(input).toBeVisible();
    return;
  }

  const chatButton = page.getByRole("button", { name: /^chat$/i });
  await expect(chatButton).toBeVisible();
  await chatButton.click();

  await expect(input).toBeVisible();
}

test("AI answer persists after commit (no disappearing message)", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueTransport(page);

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  await openChatDrawer(page);
  const input = page.getByPlaceholder("Ask PangeAI...");
  await input.fill("how many pubs are flooded?");
  await input.press("Enter");

  // Wait for the final answer to appear in the thread history.
  const answer = page.getByText(/I found \d+ pubs in flood extent/i);
  await expect(answer).toBeVisible();

  // Regression guard: it must still be visible shortly after commit/refetch.
  await page.waitForTimeout(1000);
  await expect(answer).toBeVisible();
});

test("dry pubs near metro works and persists", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueTransport(page);

  await page.getByRole("button", { name: /start new thread/i }).click();
  await page.waitForURL(/\/thread\/\d+$/);

  await openChatDrawer(page);
  const input = page.getByPlaceholder("Ask PangeAI...");
  await input.fill("find 20 dry pubs near metro");
  await input.press("Enter");

  const answer = page.getByText(/My 20 recommendations:/i);
  await expect(answer).toBeVisible();

  // Regression guard: it must still be visible shortly after commit/refetch.
  await page.waitForTimeout(1000);
  await expect(answer).toBeVisible();
});

test("zoomed out view uses clusters (LOD)", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueTransport(page);

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
  await expect(page.getByText("Beer POIs (pub/biergarten/brewery) (clusters)")).toBeVisible();
});

test("highlighted response can render clusters at low zoom", async ({ page }) => {
  await page.goto("/");
  await disableAutoMinimizeChat(page);
  await selectPragueTransport(page);

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
  const input = page.getByPlaceholder("Ask PangeAI...");
  await input.fill("find 20 dry pubs near metro");
  await input.press("Enter");

  await expect(page.getByText(/My 20 recommendations:/i)).toBeVisible();
  await expect(page.getByText("Beer POIs (pub/biergarten/brewery) (clusters)")).toBeVisible();
});

