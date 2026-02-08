import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import Plotly from "react-plotly.js";
import { useAppUi } from "@/components/layout/AppUiContext";

export const Route = createFileRoute("/")({
	component: App,
});

function App() {
	const { scenarioId } = useAppUi();
	const [view, setView] = useState<{ lat: number; lon: number; zoom: number }>({
		lat: 50.0755,
		lon: 14.4378,
		zoom: 10.5,
	});

	useEffect(() => {
		let cancelled = false;
		(async () => {
			try {
				const resp = await fetch("http://localhost:8000/scenarios");
				if (!resp.ok) return;
				const raw = (await resp.json()) as unknown;
				const list = Array.isArray(raw) ? raw : [];
				const match = list.find((s) => {
					if (!s || typeof s !== "object") return false;
					return (s as { id?: unknown }).id === scenarioId;
				});
				const dv =
					match && typeof match === "object"
						? (match as { defaultView?: unknown }).defaultView
						: undefined;
				const c =
					dv && typeof dv === "object"
						? (dv as { center?: unknown }).center
						: undefined;
				const z =
					dv && typeof dv === "object"
						? (dv as { zoom?: unknown }).zoom
						: undefined;
				if (
					c &&
					typeof (c as { lat?: unknown }).lat === "number" &&
					typeof (c as { lon?: unknown }).lon === "number" &&
					typeof z === "number" &&
					!cancelled
				) {
					setView({
						lat: (c as { lat: number }).lat,
						lon: (c as { lon: number }).lon,
						zoom: z,
					});
				}
			} catch {
				// ignore
			}
		})();
		return () => {
			cancelled = true;
		};
	}, [scenarioId]);

	return (
		<div className="w-full h-full bg-accent relative">
			<Plotly
				data={[
					{
						type: "scattermapbox",
					},
				]}
				layout={{
					mapbox: {
						center: { lat: view.lat, lon: view.lon },
						zoom: view.zoom,
						style: "carto-positron",
					},
					showlegend: false,
					margin: { l: 0, r: 0, t: 0, b: 0 },
				}}
				config={{ scrollZoom: true, displayModeBar: false }}
				useResizeHandler={true}
				style={{ width: "100%", height: "100%" }}
				className="w-full h-full overflow-hidden"
			/>
			<div className="absolute top-3 left-3 z-10 rounded-md border border-border bg-background/90 px-3 py-2 text-sm max-w-[420px]">
				<div className="font-semibold mb-1">Map-first view</div>
				<div className="text-muted-foreground">
					Pick a thread in the left sidebar (or create a new one) to start
					chatting.
				</div>
			</div>
		</div>
	);
}
