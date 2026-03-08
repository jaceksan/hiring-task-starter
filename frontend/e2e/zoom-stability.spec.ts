import { expect, test } from "@playwright/test";

const TEST_SCENARIO_ID = "prague_population_infrastructure_test";

async function disableAutoMinimizeChat(page: any) {
	const toggle = page.getByLabel(/auto-minimize chat/i);
	if ((await toggle.count()) > 0) {
		await toggle.setChecked(false);
	}
}

async function primePragueTestScenario(page: any) {
	await page.addInitScript((scenarioId: string) => {
		window.localStorage.setItem("pange_scenario", scenarioId);
		window.localStorage.setItem("pange_engine", "duckdb");
	}, TEST_SCENARIO_ID);
}

async function getMapboxZoom(page: any): Promise<number | null> {
	return await page.evaluate(() => {
		const el = document.querySelector(".js-plotly-plot") as any;
		const map = el?._fullLayout?.mapbox?._subplot?.map;
		const z = map?.getZoom?.();
		return typeof z === "number" ? z : null;
	});
}

test("plot refresh with different zoom does not snap back the map @smoke", async ({
	page,
}) => {
	await primePragueTestScenario(page);
	await page.goto("/");
	await disableAutoMinimizeChat(page);

	await page.getByRole("button", { name: /start new thread/i }).click();
	await page.waitForURL(/\/thread\/\d+$/);

	await expect(page.locator(".js-plotly-plot")).toBeVisible();

	// Let initial map state settle.
	await page.waitForTimeout(500);

	const initialZoom = await getMapboxZoom(page);
	expect(initialZoom).not.toBeNull();

	// Now intercept /plot responses and inject a drastically different zoom.
	// If the frontend incorrectly applies the response zoom, the map will snap.
	await page.route("**/plot", async (route: any) => {
		let handled = false;
		try {
			const response = await route.fetch();
			const body = await response.json();
			body.layout = body.layout ?? {};
			body.layout.mapbox = body.layout.mapbox ?? {};
			body.layout.mapbox.zoom = 3;
			body.layout.mapbox.center = { lat: 0, lon: 0 };
			await route.fulfill({
				response,
				body: JSON.stringify(body),
			});
			handled = true;
		} catch {
			// Ignore and fall through.
		}
		if (!handled) {
			try {
				await route.continue();
			} catch {
				// route may already be handled/closed on teardown
			}
		}
	});

	// Trigger a /plot refresh by resizing the viewport (the ResizeObserver fires).
	const prevSize = page.viewportSize();
	await page.setViewportSize({
		width: (prevSize?.width ?? 1280) - 100,
		height: (prevSize?.height ?? 720) - 50,
	});

	// Wait for the intercepted /plot response to be processed.
	await page.waitForTimeout(1500);

	// The map zoom must NOT have snapped to 3 (the injected response zoom).
	const afterZoom = await getMapboxZoom(page);
	expect(afterZoom).not.toBeNull();
	expect(afterZoom as number).toBeGreaterThanOrEqual(
		(initialZoom as number) - 1,
	);
	await page.unroute("**/plot");
});
