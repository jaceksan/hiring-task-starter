import { expect, test } from "@playwright/test";

async function disableAutoMinimizeChat(page: any) {
	const toggle = page.getByLabel(/auto-minimize chat/i);
	if ((await toggle.count()) > 0) {
		await toggle.setChecked(false);
	}
}

async function selectPragueGeoParquetScenario(page: any) {
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

async function getTraceLonCount(page: any, traceName: string): Promise<number> {
	return await page.evaluate((name: string) => {
		const el = document.querySelector(".js-plotly-plot") as any;
		const data = Array.isArray(el?.data) ? el.data : [];
		const t = data.find((x: any) => String(x?.name ?? "") === String(name));
		const lon = t?.lon;
		return Array.isArray(lon) ? lon.filter((v: any) => v !== null).length : 0;
	}, traceName);
}

async function getTraceFeatureCount(page: any, traceName: string): Promise<number> {
	return await page.evaluate((name: string) => {
		const el = document.querySelector(".js-plotly-plot") as any;
		const data = Array.isArray(el?.data) ? el.data : [];
		const t = data.find((x: any) => String(x?.name ?? "") === String(name));
		const lon = Array.isArray(t?.lon) ? (t.lon as Array<number | null>) : [];
		let inSeg = false;
		let segs = 0;
		for (const v of lon) {
			if (v === null) {
				inSeg = false;
				continue;
			}
			if (!inSeg) {
				segs += 1;
				inSeg = true;
			}
		}
		return segs;
	}, traceName);
}

async function zoomMapboxBy(page: any, delta: number) {
	await page.evaluate(async (d: number) => {
		const el = document.querySelector(".js-plotly-plot") as any;
		const plotly = (globalThis as any)?.Plotly;
		const current =
			typeof el?._fullLayout?.mapbox?.zoom === "number"
				? (el._fullLayout.mapbox.zoom as number)
				: null;

		// Deterministic: relayout emits plotly_relayout, which triggers /plot refresh.
		if (el && plotly?.relayout && typeof current === "number") {
			await plotly.relayout(el, { "mapbox.zoom": current + d });
			return;
		}

		// Fallback: direct map zoom (may not always trigger plot refresh).
		const map = el?._fullLayout?.mapbox?._subplot?.map;
		if (!map?.getZoom || !map?.setZoom) return;
		map.setZoom(map.getZoom() + d);
	}, delta);
}

test("highlight motorways renders and persists across /plot refresh", async ({
	page,
}) => {
	await page.goto("/");
	await disableAutoMinimizeChat(page);
	await selectPragueGeoParquetScenario(page);

	let seenInvokeBody: any = null;
	await page.route("**/invoke", async (route) => {
		const raw = route.request().postData();
		if (raw) {
			try {
				seenInvokeBody = JSON.parse(raw);
			} catch {
				seenInvokeBody = null;
			}
		}
		await route.continue();
	});

	await page.getByRole("button", { name: /start new thread/i }).click();
	await page.waitForURL(/\/thread\/\d+$/);

	await openChatDrawer(page);

	// Zoom in enough so GeoParquet roads geometry is decoded for highlight.
	await zoomMapboxBy(page, 1.75);
	const expectedZoom = await page.evaluate(() => {
		const el = document.querySelector(".js-plotly-plot") as any;
		const map = el?._fullLayout?.mapbox?._subplot?.map;
		const z = map?.getZoom?.();
		return typeof z === "number" ? z : null;
	});
	expect(expectedZoom).not.toBeNull();

	const input = page.getByPlaceholder("Ask PangeAI...");
	await input.fill("highlight motorways");

	const invokeResp = page.waitForResponse(
		(r: any) => r.url().includes("/invoke") && r.status() === 200,
	);
	await input.press("Enter");
	await invokeResp;

	// Wait for the chat message.
	const msg = page.getByText(/Highlighted \d+ Roads \(lines\)/i);
	await expect(msg).toBeVisible();

	// Regression guard: invoke payload should reflect the actual current map zoom.
	expect(seenInvokeBody?.map?.view?.zoom).toBeDefined();
	expect(Number(seenInvokeBody.map.view.zoom)).toBeGreaterThanOrEqual(
		(expectedZoom as number) - 0.1,
	);

	// The highlight trace should not be empty.
	await expect
		.poll(async () => await getTraceLonCount(page, "Motorways"), {
			timeout: 20_000,
		})
		.toBeGreaterThan(2);

	// Stronger guard: we should usually get multiple highlighted features, not just one long line.
	await expect
		.poll(async () => await getTraceFeatureCount(page, "Motorways"), {
			timeout: 20_000,
		})
		.toBeGreaterThanOrEqual(2);

	// Trigger a /plot refresh by zooming out a bit.
	const plotResp = page.waitForResponse(
		(r: any) => r.url().includes("/plot") && r.status() === 200,
	);
	await zoomMapboxBy(page, -1.25);
	await plotResp;

	// Highlight should still be present after the refresh.
	await expect
		.poll(async () => await getTraceLonCount(page, "Motorways"), {
			timeout: 20_000,
		})
		.toBeGreaterThan(2);

	await expect
		.poll(async () => await getTraceFeatureCount(page, "Motorways"), {
			timeout: 20_000,
		})
		.toBeGreaterThanOrEqual(1);
});

