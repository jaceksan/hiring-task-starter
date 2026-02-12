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

test("road control highlights motorways and persists across /plot refresh", async ({
	page,
}) => {
	await page.goto("/");
	await disableAutoMinimizeChat(page);
	await selectPragueGeoParquetScenario(page);

	await page.getByRole("button", { name: /start new thread/i }).click();
	await page.waitForURL(/\/thread\/\d+$/);

	// Zoom in enough so GeoParquet roads geometry is decoded for highlight.
	await zoomMapboxBy(page, 2.5);

	const motorway = page.getByLabel("Motorway (+link)");
	await expect(motorway).toBeVisible();
	if (!(await motorway.isChecked())) {
		await motorway.check();
	}

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

